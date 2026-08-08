
from pathlib import Path
import re
from datetime import datetime
from xml.sax.saxutils import escape
import pandas as pd
from shared import database as db

HSN_RE = r"(?:99\d{4}|996\d{3}|998\d{3})"
TAX_HEADS = {"CGST", "SGST", "IGST"}

def clean(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\n", " ")).strip()

def safe_voucher_no(v):
    s = clean(v)
    s = re.sub(r"[^A-Za-z0-9_./-]+", "-", s)
    return s[:60] or "AUTO"

def normalize_desc(s):
    s = clean(s)
    s = re.sub(r"\s*_\s*", "_", s)
    s = re.sub(r"\s+-\s+", "-", s)
    # Myntra sometimes appends month suffix, e.g. Commission_2026- 02.
    s = re.sub(r"[_\s-]*(?:20\s*\d{2}|20\d{2})\s*-\s*\d{2}$", "", s)
    s = re.sub(r"[_\s-]+$", "", s)
    return s

def amount(x):
    s = str(x or "").replace(",", "").replace("₹", "").replace("INR", "").replace("Rs", "").replace(":", "").replace("%", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return abs(float(m.group(0))) if m else 0.0

def is_money(s):
    return bool(re.search(r"^-?\s*(?:INR|Rs)?\s*[\d,]+(?:\.\d+)?$", clean(s), re.I))

def is_number(s):
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", clean(s)))

def is_hsn(s):
    return bool(re.fullmatch(HSN_RE, clean(s)))

def is_serial(s):
    s = clean(s)
    if not re.fullmatch(r"\d+\.?", s):
        return False
    try:
        return int(s.rstrip(".")) > 0
    except Exception:
        return False

def tally_date(s):
    s = str(s or "")
    for pat in [r"(\d{2})/(\d{2})/(\d{4})", r"(\d{2})-(\d{2})-(\d{4})"]:
        m = re.search(pat, s)
        if m:
            return m.group(3) + m.group(2) + m.group(1)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return datetime.today().strftime("%Y%m%d")

def read_pdf_text(path):
    import fitz
    return "\n".join(p.get_text("text") for p in fitz.open(str(path)))

def lines(text):
    return [clean(x) for x in str(text).splitlines() if clean(x)]

def detect_platform(text, name=""):
    low = (text + " " + name).lower()
    base = Path(name).name.lower()

    # Supplier-specific detection must run before generic marketplace detection.
    if "valmo transportation private limited" in low or "vtpl" in base:
        return "valmo"
    if "meesho technologies private limited" in low or "mtpl" in base:
        return "meesho_technologies"
    # Meesho Limited / Fashnear/FTPL invoices must not get mixed with Meesho Technologies.
    if "meesho limited" in low or "fashnear technologies" in low or "ftpl" in base:
        return "meesho_limited"

    if "flipkart" in low or base.startswith(("fkc", "fkr")):
        return "flipkart"
    if "myntra" in low or "myntra" in base:
        return "myntra"
    if "meesho" in low or "messo" in base:
        return "meesho"
    if "amazon" in low or re.search(r"^[a-z]{2}(-c)?-\d{2,4}-", base) or base.startswith(("ads-", "ka-", "tn-", "wb-", "tg-", "mh-", "hr-")):
        return "amazon"
    return "unknown"

def detect_doc_type(text):
    low = text.lower()
    if "credit note" in low:
        return "Credit Note"
    if "debit note" in low:
        return "Debit Note"
    return "Tax Invoice"

def invoice_no(text, path, original_name=""):
    patterns = [
        r"Credit Note Number:\s*([A-Z0-9\-/]+)",
        r"Credit Note #:\s*([A-Z0-9\-/]+)",
        r"Credit Note\s*#\s*[:\s]*([A-Z0-9\-/]+)",
        r"Invoice Number:\s*([A-Z0-9\-/]+)",
        r"Invoice No\s*:\s*([A-Z0-9\-/]+)",
        r"Invoice #:\s*([A-Z0-9\-/]+)",
        r"Invoice #\s*([A-Z0-9\-/]+)",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(1).strip()
    ls = lines(text)
    for i, l in enumerate(ls[:-1]):
        if l.lower() in ["invoice #:", "invoice #", "credit note #:", "credit note #"]:
            return ls[i+1][:45]
    name = Path(original_name or path).name
    name = re.sub(r"\.pdf.*$", "", name, flags=re.I)
    return name[:45]

def invoice_date(text):
    patterns = [
        r"Credit Note Date:\s*(\d{2}/\d{2}/\d{4})",
        r"Credit Note Date:\s*(\d{2}-\d{2}-\d{4})",
        r"Invoice Date:\s*(\d{2}/\d{2}/\d{4})",
        r"Invoice Date\s*:\s*(\d{4}-\d{2}-\d{2})",
        r"Invoice Date:\s*(\d{2}-\d{2}-\d{4})",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return tally_date(m.group(1))
    return datetime.today().strftime("%Y%m%d")

def voucher_for(company, platform, doc):
    rule = db.voucher_rule(company, platform, doc)
    return rule.get("tally_voucher_type", "Purchase"), rule.get("sign_mode", "charge")

def total_issue(taxable, cgst, sgst, igst, total):
    calc = round(float(taxable) + float(cgst) + float(sgst) + float(igst), 2)
    if total and abs(calc - float(total)) > 1.0:
        return f"TOTAL_MISMATCH parsed={calc} pdf={round(float(total),2)}"
    return ""

def add_row(rows, company, source, platform, doc, inv, dt, desc, taxable, cgst=0, sgst=0, igst=0, total=0, issue=""):
    desc = normalize_desc(desc)
    if not desc or desc.lower() in ["total", "none"]:
        return
    if not total:
        total = float(taxable) + float(cgst) + float(sgst) + float(igst)

    vtype, _ = voucher_for(company, platform, doc)
    ledger, matched = db.map_ledger(company, "marketplace", platform, desc, doc)

    row_issue = issue or total_issue(taxable, cgst, sgst, igst, total)
    status = "OK"
    if matched == "UNMATCHED_TO_SUSPENSE":
        status = "REVIEW_LEDGER_TO_SUSPENSE"
    if row_issue:
        status = "REVIEW_" + row_issue

    rows.append({
        "Source PDF": source,
        "Company": company,
        "Platform": platform,
        "PDF Doc Type": doc,
        "Tally Voucher Type": vtype,
        "Invoice No": inv,
        "Date": dt,
        "Description": desc,
        "Mapped Ledger": ledger,
        "Matched By": matched,
        "Taxable": round(float(taxable), 2),
        "CGST": round(float(cgst), 2),
        "SGST": round(float(sgst), 2),
        "IGST": round(float(igst), 2),
        "Total": round(float(total), 2),
        "Status": status,
        "Issue": row_issue,
        "Import?": False if status.startswith("REVIEW_PARSE") else True,
    })

def parse_amazon(text, company, source, platform, doc, inv, dt):
    # Parse only the Amazon summary section, not daily Details of Fees.
    # Keeps each summary line separately to match manual Tally entries.
    summary = re.split(r"Details of Fees to the above", text, flags=re.I)[0]
    ls = lines(summary)
    rows = []

    def read_fee_amount(idx, limit=8):
        """Read the service fee amount after a service description."""
        j = idx
        while j < min(len(ls), idx + limit):
            l = ls[j]
            low = l.lower()
            if l.upper() in TAX_HEADS or is_hsn(l) or low.startswith(("total", "subtotal", "whether tax")):
                return 0.0, j
            # Case: "-INR" then next line "106.00"
            if re.fullmatch(r"-?\s*INR|-?\s*Rs", l, re.I) and j + 1 < len(ls):
                return amount(ls[j + 1]), j + 2
            # Case: "-INR 26.00" or "INR 7330.00"
            m = re.search(r"-?\s*(?:INR|Rs)\s*([\d,]+\.\d{2})", l, re.I)
            if m:
                return amount(m.group(1)), j + 1
            if is_money(l):
                return amount(l), j + 1
            j += 1
        return 0.0, idx

    def read_tax_amount(idx, limit=8):
        """Read tax amount after CGST/SGST/IGST.
        Handles:
          IGST
          18.00% INR 1319.40
        and
          IGST
          18.00%
          INR 1319.40
        and
          IGST
          18.00% -INR 19.08
        """
        j = idx
        while j < min(len(ls), idx + limit):
            l = ls[j]
            low = l.lower()
            up = l.upper()
            if is_hsn(l) or low.startswith(("total", "subtotal", "whether tax", "details of fees")):
                return 0.0, j
            if up in TAX_HEADS and j != idx:
                return 0.0, j
            # Most important: amount after INR/Rs anywhere in the line, ignore % rate.
            m = re.search(r"-?\s*(?:INR|Rs)\s*([\d,]+\.\d{2})", l, re.I)
            if m:
                return amount(m.group(1)), j + 1
            # Sometimes "-INR" on one line then amount next line.
            if re.fullmatch(r"-?\s*INR|-?\s*Rs", l, re.I) and j + 1 < len(ls):
                return amount(ls[j + 1]), j + 2
            j += 1
        return 0.0, idx

    i = 0
    while i < len(ls):
        if not is_hsn(ls[i]):
            i += 1
            continue

        j = i + 1
        desc_parts = []
        while j < len(ls):
            l = ls[j]
            lu = l.upper()
            low = l.lower()
            if re.fullmatch(r"-?\s*INR|-?\s*Rs", l, re.I) or re.search(r"-?\s*(?:INR|Rs)\s*[\d,]+\.\d{2}", l, re.I) or is_money(l):
                break
            if is_hsn(l) or low.startswith(("total", "subtotal", "whether tax")):
                break
            if not is_serial(l) and not re.search(r"\d{2}-\d{2}-\d{4}|\d{2}/\d{2}/\d{4}", l) and lu not in TAX_HEADS and not low.startswith(("si", "original invoice", "category", "description", "tax", "amount")):
                desc_parts.append(l)
            j += 1

        taxable, j = read_fee_amount(j, 8)
        if not taxable:
            i += 1
            continue

        cgst = sgst = igst = 0.0
        k = j
        while k < len(ls):
            l = ls[k]
            lu = l.upper()
            low = l.lower()
            if is_hsn(l) or low.startswith(("total:", "subtotal of fees", "subtotal for", "subtotal of gst", "total invoice", "details of fees")):
                break
            if lu in TAX_HEADS:
                val, new_k = read_tax_amount(k + 1, 8)
                if lu == "CGST":
                    cgst += val
                elif lu == "SGST":
                    sgst += val
                elif lu == "IGST":
                    igst += val
                k = max(new_k, k + 1)
                continue
            k += 1

        add_row(rows, company, source, platform, doc, inv, dt, " ".join(desc_parts), taxable, cgst, sgst, igst, taxable + cgst + sgst + igst)
        i = max(k, i + 1)

    return rows

def parse_flipkart(text, company, source, platform, doc, inv, dt):
    ls = lines(text)
    rows = []
    i = 0
    while i < len(ls):
        if not is_hsn(ls[i]):
            i += 1
            continue

        j = i + 1
        desc_parts = []
        while j < len(ls):
            l = ls[j]
            if is_money(l):
                break
            if is_hsn(l) or l.lower().startswith(("total", "credit note date", "invoice date", "billed to", "note", "payment is", "e.and")):
                break
            if not is_serial(l):
                desc_parts.append(l)
            j += 1

        if j >= len(ls) or not is_money(ls[j]):
            i += 1
            continue

        taxable = amount(ls[j])
        j += 1
        nums = []
        k = j
        while k < len(ls) and len(nums) < 8:
            l = ls[k]
            if is_hsn(l) or l.lower().startswith(("total", "credit note date", "invoice date", "billed to", "note", "payment is", "e.and")):
                break
            if is_money(l) or is_number(l):
                nums.append(amount(l))
            k += 1

        cgst = sgst = igst = total = 0.0
        # CGST/SGST format: 9.0, 9.0, CGST Amt, SGST Amt, Total
        if len(nums) >= 5 and abs(nums[0] - 9.0) < 0.01 and abs(nums[1] - 9.0) < 0.01:
            cgst, sgst, total = nums[2], nums[3], nums[4]
        # IGST format: 18.0, IGST Amt, Total
        elif len(nums) >= 3 and abs(nums[0] - 18.0) < 0.01:
            igst, total = nums[1], nums[2]
        elif len(nums) >= 1:
            # Fallback: last number is total; infer tax.
            total = nums[-1]
            tax = round(total - taxable, 2)
            if tax > 0:
                igst = tax

        add_row(rows, company, source, platform, doc, inv, dt, " ".join(desc_parts), taxable, cgst, sgst, igst, total)
        i = max(k, i + 1)
    return rows

def parse_myntra(text, company, source, platform, doc, inv, dt):
    ls = lines(text)
    rows = []
    i = 0
    while i < len(ls):
        if not is_hsn(ls[i]):
            i += 1
            continue

        j = i + 1
        desc_parts = []
        while j < len(ls) and not ls[j].startswith("Rs"):
            desc_parts.append(ls[j])
            j += 1

        # Before the first Rs, last numeric part is quantity; keep earlier numeric parts as part of description
        if desc_parts and is_number(desc_parts[-1]):
            desc = " ".join(desc_parts[:-1])
        else:
            desc = " ".join(desc_parts)

        money = []
        k = j
        while k < len(ls) and len(money) < 6:
            if is_hsn(ls[k]) or ls[k].lower().startswith(("total", "amount in words", "terms and conditions")):
                break
            if is_money(ls[k]):
                money.append(amount(ls[k]))
            k += 1

        # money = unit price, base price, IGST, CGST, SGST, total
        if len(money) >= 6:
            base, igst, cgst, sgst, total = money[1], money[2], money[3], money[4], money[5]
            add_row(rows, company, source, platform, doc, inv, dt, desc, base, cgst, sgst, igst, total)
        i = max(k, i + 1)
    return rows

def parse_meesho(text, company, source, platform, doc, inv, dt):
    ls = lines(text)
    rows = []
    i = 0
    while i < len(ls):
        if not is_serial(ls[i]):
            i += 1
            continue

        j = i + 1
        desc_parts = []
        while j < len(ls) and not is_hsn(ls[j]):
            if not ls[j].lower().startswith(("total", "tax is", "original for")):
                desc_parts.append(ls[j])
            j += 1
        if j >= len(ls) or not is_hsn(ls[j]):
            i += 1
            continue

        j += 1
        vals = []
        while j < len(ls) and len(vals) < 5:
            l = ls[j]
            if is_serial(l) and vals:
                break
            if l.startswith("@"):
                j += 1
                continue
            if is_money(l) or is_number(l):
                vals.append(amount(l))
            j += 1

        # Meesho order: taxable, sgst, cgst, igst, total
        if len(vals) >= 5:
            taxable, sgst, cgst, igst, total = vals[:5]
            if taxable > 0:
                add_row(rows, company, source, platform, doc, inv, dt, " ".join(desc_parts), taxable, cgst, sgst, igst, total)
        i = max(j, i + 1)
    return rows

def parse_marketplace_pdf(path, company, original_name=None):
    text = read_pdf_text(path)
    source = original_name or Path(path).name
    platform = detect_platform(text, source)
    doc = detect_doc_type(text)
    inv = invoice_no(text, path, source)
    dt = invoice_date(text)

    if platform == "amazon":
        rows = parse_amazon(text, company, source, platform, doc, inv, dt)
    elif platform == "flipkart":
        rows = parse_flipkart(text, company, source, platform, doc, inv, dt)
    elif platform == "myntra":
        rows = parse_myntra(text, company, source, platform, doc, inv, dt)
    elif platform in ["meesho", "meesho_limited", "meesho_technologies", "valmo"]:
        rows = parse_meesho(text, company, source, platform, doc, inv, dt)
    else:
        rows = []

    if not rows:
        comp = db.company(company)
        rows = [{
            "Source PDF": source,
            "Company": company,
            "Platform": platform,
            "PDF Doc Type": doc,
            "Tally Voucher Type": voucher_for(company, platform, doc)[0],
            "Invoice No": inv,
            "Date": dt,
            "Description": "NO ROWS PARSED - REVIEW PDF FORMAT",
            "Mapped Ledger": comp.get("suspense_ledger", "Suspense"),
            "Matched By": "NO_PARSE",
            "Taxable": 0.0,
            "CGST": 0.0,
            "SGST": 0.0,
            "IGST": 0.0,
            "Total": 0.0,
            "Status": "REVIEW_PARSE_FAILED",
            "Issue": "Parser could not read this PDF format",
            "Import?": False,
        }]
    return pd.DataFrame(rows)

def ledger_xml(ledger, amt, party=False):
    return f"""
<LEDGERENTRIES.LIST>
<LEDGERNAME>{escape(str(ledger))}</LEDGERNAME>
<ISDEEMEDPOSITIVE>{"Yes" if amt < 0 else "No"}</ISDEEMEDPOSITIVE>
<ISPARTYLEDGER>{"Yes" if party else "No"}</ISPARTYLEDGER>
<AMOUNT>{amt:.2f}</AMOUNT>
</LEDGERENTRIES.LIST>"""

def build_xml(df, company, export_review=True):
    comp = db.company(company)
    df = df[df["Import?"] == True].copy()
    if not export_review:
        df = df[df["Status"].astype(str).str.startswith("OK")]
    messages = []

    for keys, g in df.groupby(["Source PDF", "Platform", "PDF Doc Type", "Tally Voucher Type", "Invoice No", "Date"], dropna=False):
        src, platform, pdf_doc, vtype, inv, dt = keys
        rule = db.voucher_rule(company, platform, pdf_doc)
        reverse = rule.get("sign_mode") == "reverse" or str(vtype).lower() == "debit note"
        party = db.party_ledger(company, platform)
        if str(platform).lower() in ["amazon", "flipkart", "meesho", "myntra", "meesho_limited", "meesho_technologies", "valmo"] and str(party).strip().lower() == "suspense":
            # Do not silently create marketplace vouchers with Suspense as party.
            continue

        taxable = float(g["Taxable"].sum())
        cgst = float(g["CGST"].sum())
        sgst = float(g["SGST"].sum())
        igst = float(g["IGST"].sum())
        total = taxable + cgst + sgst + igst

        party_amt = -total if reverse else total
        line_sign = 1 if reverse else -1

        xml = f"""
<TALLYMESSAGE xmlns:UDF="TallyUDF">
<VOUCHER VCHTYPE="{escape(str(vtype))}" ACTION="Create" OBJVIEW="Invoice Voucher View">
<DATE>{escape(str(dt))}</DATE>
<REFERENCEDATE>{escape(str(dt))}</REFERENCEDATE>
<VOUCHERTYPENAME>{escape(str(vtype))}</VOUCHERTYPENAME>
<PARTYLEDGERNAME>{escape(str(party))}</PARTYLEDGERNAME>
<PARTYNAME>{escape(str(party))}</PARTYNAME>
<VOUCHERNUMBER>{escape(safe_voucher_no(inv))}</VOUCHERNUMBER>
<BASICVOUCHERNUMBER>{escape(safe_voucher_no(inv))}</BASICVOUCHERNUMBER>
<REFERENCE>{escape(str(inv))}</REFERENCE>
<BASICREFERENCE>{escape(str(inv))}</BASICREFERENCE>
<NUMBERINGSTYLE>Manual</NUMBERINGSTYLE>
<BASICBUYERNAME>{escape(comp.get("tally_company_name") or company)}</BASICBUYERNAME>
<CMPGSTIN>{escape(comp.get("gstin") or "")}</CMPGSTIN>
<PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>
<VCHENTRYMODE>Accounting Invoice</VCHENTRYMODE>
<ISINVOICE>Yes</ISINVOICE>
<NARRATION>{escape(str(platform).upper() + " " + str(pdf_doc) + " " + str(inv) + " " + str(src))}</NARRATION>
"""
        xml += ledger_xml(party, party_amt, True)
        for ledger, lg in g.groupby("Mapped Ledger", dropna=False):
            val = float(lg["Taxable"].sum())
            if val:
                xml += ledger_xml(ledger, line_sign * val, False)
        for ledger, val in [
            (comp.get("cgst_ledger", "INPUT CGST"), cgst),
            (comp.get("sgst_ledger", "INPUT SGST"), sgst),
            (comp.get("igst_ledger", "INPUT IGST"), igst),
        ]:
            if val:
                xml += ledger_xml(ledger, line_sign * val, False)
        xml += "\n</VOUCHER>\n</TALLYMESSAGE>\n"
        messages.append(xml)

    tally_company = comp.get("tally_company_name") or company
    return f"""<ENVELOPE>
<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
<BODY><IMPORTDATA>
<REQUESTDESC>
<REPORTNAME>Vouchers</REPORTNAME>
<STATICVARIABLES><SVCURRENTCOMPANY>{escape(str(tally_company))}</SVCURRENTCOMPANY></STATICVARIABLES>
</REQUESTDESC>
<REQUESTDATA>{''.join(messages)}</REQUESTDATA>
</IMPORTDATA></BODY>
</ENVELOPE>"""
