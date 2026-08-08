from __future__ import annotations

import re
from typing import Dict, List, Tuple

from extractor.layout_engine import clean_text, first_match, get_section, money_to_float, norm_rate
from rules.gst_rules import combine_rows


def detect_template(text: str) -> str:
    t = text.lower()
    if "stock transfer" in t and ("invoice id" in t or "invoice no" in t or "reference number" in t or "reference no" in t or "dc no" in t):
        return "flipkart_stock_transfer"
    if "tax invoice" in t and "invoice no" in t and "taxable amount" in t:
        return "sujal_tax_invoice"
    return "unknown"


def _gstins(section: str) -> List[str]:
    return re.findall(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b", section)


def parse_flipkart_stock_transfer(text: str, source_file: str, force_18_hsn: str = "73269099", ignore_zero_taxable: bool = True) -> Tuple[List[Dict], List[Dict]]:
    """Parse Flipkart Stock Transfer Invoice.

    Supports the cell-per-line eInvoice PDFs where HSN can be split like
    7117199 \n 0 and the old regex parser returned no rows.
    """
    text = clean_text(text)
    date = first_match(r"Invoice\s*Date\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})", text)
    if not date:
        date = first_match(r"DC\s*Date\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})", text)
    invoice_id = first_match(r"Invoice\s*(?:Id|No)\s*[:\-]\s*([A-Z0-9\-/]+)", text)
    if not invoice_id:
        invoice_id = first_match(r"DC\s*No\s*[:\-]\s*([A-Z0-9_\-/]+)", text)
    if not invoice_id:
        invoice_id = first_match(r"Reference\s*(?:Number|No)\s*[:\-]\s*([A-Z0-9_\-/]+)", text)

    # Extract GSTINs from full text. Supplier usually first, customer/ship-to second.
    gstins_all = _gstins(text)
    shipped_from_gstin = gstins_all[0] if len(gstins_all) >= 1 else ""
    ship_to_gstin = gstins_all[1] if len(gstins_all) >= 2 else (gstins_all[0] if gstins_all else "")

    # Customer trade name: in these invoices the second Name is usually ship/customer name.
    names = re.findall(r"Name\s*\n\s*:\s*([^\n]+)", text, flags=re.I)
    trade_name = names[1].strip() if len(names) > 1 else (names[0].strip() if names else "")

    raw_rows: List[Dict] = []
    item_rows: List[Dict] = []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    serial_re = re.compile(r"^\d+$")
    money_re = re.compile(r"^₹\s*[0-9,]+(?:\.\d+)?$")

    # Start after table header if possible.
    start_idx = 0
    for i, ln in enumerate(lines):
        if ln.lower().startswith("total value"):
            start_idx = i + 1
            break

    def _looks_like_item_values(ls, k):
        """After HSN we expect qty, unit, rate, taxable money."""
        if k + 3 >= len(ls):
            return False
        if money_to_float(ls[k]) <= 0:
            return False
        if not re.search(r"pcs|pc|nos|qty|-", ls[k + 1], re.I):
            return False
        if money_to_float(ls[k + 2]) < 0:
            return False
        if not re.search(r"₹|\d", ls[k + 3]):
            return False
        return True

    def read_hsn(ls, j):
        if j >= len(ls):
            return "", j
        a = re.sub(r"\D", "", ls[j])
        # Common split HSN: 7117199 + 0 / 7326909 + 9 / 3926101 + 9.
        if len(a) == 7 and j + 1 < len(ls):
            b = re.sub(r"\D", "", ls[j + 1])
            if len(b) == 1 and _looks_like_item_values(ls, j + 2):
                return a + b, j + 2
        # Full HSN/SAC. Keep short codes like 4819 only if following cells look valid.
        if 4 <= len(a) <= 10 and _looks_like_item_values(ls, j + 1):
            return a, j + 1
        return "", j

    i = start_idx
    while i < len(lines):
        if re.fullmatch(r"(?:TOTAL|Total)", lines[i]):
            break
        if not serial_re.match(lines[i]):
            i += 1
            continue
        serial = lines[i]
        j = i + 1
        desc_parts = []
        # description until HSN-like line
        while j < len(lines):
            hsn_try, hsn_next = read_hsn(lines, j)
            if hsn_try:
                break
            if re.fullmatch(r"(?:TOTAL|Total)", lines[j]):
                break
            desc_parts.append(lines[j])
            j += 1
        hsn, j = read_hsn(lines, j)
        if not hsn or j + 7 >= len(lines):
            i += 1
            continue

        qty = money_to_float(lines[j]); unit = lines[j + 1]
        unit_price = money_to_float(lines[j + 2])
        taxable = money_to_float(lines[j + 3])
        rate = norm_rate(lines[j + 4])
        cgst = money_to_float(lines[j + 5])
        sgst = money_to_float(lines[j + 6])
        igst = money_to_float(lines[j + 7])
        total = money_to_float(lines[j + 8]) if j + 8 < len(lines) else taxable + cgst + sgst + igst
        desc = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()

        if desc and qty and taxable:
            raw_rows.append({
                "DATE": date,
                "INVOICE NO(Invoice Id).": invoice_id,
                "GSTIN( from ship to )": ship_to_gstin,
                "TRADE NAME( from Ship To Shiv Jagdamba,)": trade_name,
                "RATE": rate,
                "TAXABLE": taxable,
                "HSN CODE": hsn,
                "QTY": qty,
                "Platform Name(Optional)": "Flipkart",
                "GSTIN of e-commerce operator ( from  shipped from )": shipped_from_gstin,
            })
            item_rows.append({
                "source_file": source_file,
                "invoice_id": invoice_id,
                "date": date,
                "trade_name": trade_name,
                "ship_to_gstin": ship_to_gstin,
                "shipped_from_gstin": shipped_from_gstin,
                "serial": serial,
                "description": desc,
                "hsn": hsn,
                "qty": qty,
                "unit": unit,
                "unit_price": unit_price,
                "taxable": taxable,
                "rate": rate,
                "cgst_amount": cgst,
                "sgst_amount": sgst,
                "igst_amount": igst,
                "total": total,
            })
        i = j + 9



    # Alternate Flipkart Stock Transfer Note format: Description / SKU / HSN blocks
    # with CGST + SGST columns instead of IGST.
    if not raw_rows:
        block_text = text
        m_start = re.search(r"Description\s+Qty", text, re.I)
        if m_start:
            block_text = text[m_start.start():]
        m_end = re.search(r"\n\s*TOTAL\s*\n", block_text, re.I)
        if m_end:
            block_text = block_text[:m_end.start()]
        sku_pattern = re.compile(
            r"(?P<desc>.*?)SKU\s*:\s*(?P<sku>[^\n]+)\s*\n\s*HSN\s*:\s*(?P<hsn>\d{4,10})\s*\n\s*"
            r"(?P<qty>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<unit_price>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<base>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<cgst_rate>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<cgst>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<sgst_rate>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<sgst>\d+(?:\.\d+)?)\s*\n\s*"
            r"(?P<total>\d+(?:\.\d+)?)",
            re.I | re.S,
        )
        for idx, m in enumerate(sku_pattern.finditer(block_text), start=1):
            desc = re.sub(r"\s+", " ", (m.group("desc") or "").strip())[-180:]
            desc = re.sub(r"^.*?Value\s*\+\s*Taxes\s*", "", desc, flags=re.I)
            qty = money_to_float(m.group("qty"))
            taxable = money_to_float(m.group("base"))
            rate_total = money_to_float(m.group("cgst_rate")) + money_to_float(m.group("sgst_rate"))
            rate = norm_rate(rate_total)
            hsn = m.group("hsn")
            if desc and qty and taxable:
                raw_rows.append({
                    "DATE": date,
                    "INVOICE NO(Invoice Id).": invoice_id,
                    "GSTIN( from ship to )": ship_to_gstin,
                    "TRADE NAME( from Ship To Shiv Jagdamba,)": trade_name,
                    "RATE": rate,
                    "TAXABLE": taxable,
                    "HSN CODE": hsn,
                    "QTY": qty,
                    "Platform Name(Optional)": "Flipkart",
                    "GSTIN of e-commerce operator ( from  shipped from )": shipped_from_gstin,
                })
                item_rows.append({
                    "source_file": source_file,
                    "invoice_id": invoice_id,
                    "date": date,
                    "trade_name": trade_name,
                    "ship_to_gstin": ship_to_gstin,
                    "shipped_from_gstin": shipped_from_gstin,
                    "serial": idx,
                    "description": desc,
                    "sku": (m.group("sku") or "").strip(),
                    "hsn": hsn,
                    "qty": qty,
                    "unit_price": money_to_float(m.group("unit_price")),
                    "taxable": taxable,
                    "rate": rate,
                    "cgst_amount": money_to_float(m.group("cgst")),
                    "sgst_amount": money_to_float(m.group("sgst")),
                    "igst_amount": 0,
                    "total": money_to_float(m.group("total")),
                })

    return combine_rows(raw_rows, force_18_hsn=force_18_hsn, ignore_zero_taxable=ignore_zero_taxable), item_rows

def parse_sujal_tax_invoice(text: str, source_file: str, force_18_hsn: str = "73269099", ignore_zero_taxable: bool = True) -> Tuple[List[Dict], List[Dict]]:
    """Parse Sujal Fashion Works tax invoice.

    Older version used only tax summary, so QTY became 0. This version reads
    the item table line-by-line and then combines by rate + HSN for GST output.
    """
    text = clean_text(text)
    invoice_no = first_match(r"Invoice\s*No\.\s*:\s*([0-9A-Z\-/]+)", text)
    date = first_match(r"Date\s*:\s*([0-9]{2}-[0-9]{2}-[0-9]{4})", text)

    bill_to = get_section(text, "Bill To", ["Ship To", "Invoice Details"])
    gstins = _gstins(bill_to)
    buyer_gstin = gstins[0] if gstins else first_match(r"GSTIN\s*:\s*([0-9A-Z]{15})", bill_to)
    trade_name = ""
    for line in bill_to.splitlines():
        line = line.strip()
        if line and not re.search(r"GSTIN|State|India|Contact|Phone|Address", line, re.I):
            trade_name = line
            break

    raw_rows: List[Dict] = []
    item_rows: List[Dict] = []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hsn_re = re.compile(r"^(\d{4,10})$")
    serial_re = re.compile(r"^\d+$")

    # Locate item table body. Text extraction gives each cell as a line.
    start_idx = 0
    for i, ln in enumerate(lines):
        if ln.lower() == "amount" and i > 0 and any("item name" in x.lower() for x in lines[max(0, i-8):i+1]):
            start_idx = i + 1
            break

    i = start_idx
    while i < len(lines):
        ln = lines[i]
        if re.fullmatch(r"total", ln, flags=re.I):
            break
        if not serial_re.match(ln):
            i += 1
            continue

        serial = ln
        j = i + 1
        desc_parts = []
        while j < len(lines) and not hsn_re.match(lines[j]):
            # Stop if malformed next section begins.
            if re.fullmatch(r"total", lines[j], flags=re.I):
                break
            desc_parts.append(lines[j])
            j += 1
        if j >= len(lines) or not hsn_re.match(lines[j]):
            i += 1
            continue

        hsn = lines[j]
        qty = money_to_float(lines[j + 1] if j + 1 < len(lines) else "")
        unit = lines[j + 2] if j + 2 < len(lines) else ""
        price = money_to_float(lines[j + 3] if j + 3 < len(lines) else "")
        gst_cell = lines[j + 4] if j + 4 < len(lines) else ""
        total_cell = lines[j + 5] if j + 5 < len(lines) else ""

        rate = first_match(r"\((\d+(?:\.\d+)?)%\)", gst_cell, flags=re.I)
        rate_n = norm_rate(rate)
        gst_amount = money_to_float(gst_cell.split("(")[0])
        line_total = money_to_float(total_cell)
        taxable = round(qty * price, 2) if qty and price else round(line_total - gst_amount, 2)
        desc = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()

        if desc and qty and (taxable or line_total):
            raw_rows.append({
                "DATE": date,
                "INVOICE NO(Invoice Id).": invoice_no,
                "GSTIN( from ship to )": buyer_gstin,
                "TRADE NAME( from Ship To Shiv Jagdamba,)": trade_name,
                "RATE": rate_n,
                "TAXABLE": taxable,
                "HSN CODE": hsn,
                "QTY": qty,
                "Platform Name(Optional)": "",
                "GSTIN of e-commerce operator ( from  shipped from )": "",
            })
            item_rows.append({
                "source_file": source_file,
                "invoice_id": invoice_no,
                "date": date,
                "buyer_name": trade_name,
                "buyer_gstin": buyer_gstin,
                "serial": serial,
                "description": desc,
                "hsn": hsn,
                "qty": qty,
                "unit": unit,
                "unit_price": price,
                "rate": rate_n,
                "taxable": taxable,
                "gst_amount": gst_amount,
                "total": line_total,
            })
        i = j + 6

    # If item parser failed, fallback to tax summary so old functionality still works.
    if not raw_rows:
        total_qty = money_to_float(first_match(r"\nTotal\s+(\d+(?:\.\d+)?)\s+₹", text))
        tax_summary = re.findall(r"IGST\s+₹\s*([0-9,]+(?:\.\d+)?)\s+([0-9]+(?:\.\d+)?)%\s+₹\s*([0-9,]+(?:\.\d+)?)", text, flags=re.I)
        for taxable, rate, tax in tax_summary:
            rate_n = norm_rate(rate)
            hsn = force_18_hsn if rate_n == "18" else ""
            raw_rows.append({
                "DATE": date,
                "INVOICE NO(Invoice Id).": invoice_no,
                "GSTIN( from ship to )": buyer_gstin,
                "TRADE NAME( from Ship To Shiv Jagdamba,)": trade_name,
                "RATE": rate_n,
                "TAXABLE": money_to_float(taxable),
                "HSN CODE": hsn,
                "QTY": total_qty if len(tax_summary) == 1 else 0,
                "Platform Name(Optional)": "",
                "GSTIN of e-commerce operator ( from  shipped from )": "",
            })
        item_rows.append({
            "source_file": source_file,
            "invoice_id": invoice_no,
            "date": date,
            "trade_name": trade_name,
            "buyer_gstin": buyer_gstin,
            "total_qty_seen": total_qty,
            "note": "Fallback tax summary parser used."
        })

    return combine_rows(raw_rows, force_18_hsn=force_18_hsn, ignore_zero_taxable=ignore_zero_taxable), item_rows

def parse_by_template(template: str, text: str, source_file: str, force_18_hsn: str = "73269099", ignore_zero_taxable: bool = True) -> Tuple[List[Dict], List[Dict]]:
    if template == "flipkart_stock_transfer":
        return parse_flipkart_stock_transfer(text, source_file, force_18_hsn, ignore_zero_taxable)
    if template == "sujal_tax_invoice":
        return parse_sujal_tax_invoice(text, source_file, force_18_hsn, ignore_zero_taxable)
    return [], []
