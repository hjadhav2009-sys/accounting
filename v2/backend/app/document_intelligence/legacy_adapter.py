from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ..services.legacy import LegacyPdfToExcelService

from .models import ExtractionMethod, NormalizedExtractionResult


def _date(value: Any):
    text = str(value or "").strip()
    for pattern in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def normalize_legacy_pdf(document_id: UUID, template: str, text: str, source_file: str,
                         pages: tuple[Any, ...], quality: Any, fingerprint: Any) -> NormalizedExtractionResult:
    """Adapter around the certified parser; it does not reproduce parser rules."""
    combined, items = LegacyPdfToExcelService().parse_text(template, text, source_file)
    invoice_number = ""
    invoice_date = None
    tax_buckets: list[dict[str, Any]] = []
    total_amount = Decimal("0")
    normalized_items: list[dict[str, Any]] = []
    for row in combined:
        invoice_number = invoice_number or str(row.get("INVOICE NO(Invoice Id).") or "")
        invoice_date = invoice_date or _date(row.get("DATE"))
    item_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in items:
        if row.get("description"):
            rate = str(row.get("rate") or "").replace("%", "")
            hsn = str(row.get("hsn") or "")
            bucket = item_buckets.setdefault((rate, hsn), {"tax_type": "GST", "rate": Decimal(rate or "0"),
                "taxable": Decimal("0"), "tax": Decimal("0"), "hsn_sac": hsn})
            bucket["taxable"] += Decimal(str(row.get("taxable") or 0))
            bucket["tax"] += Decimal(str(row.get("gst_amount") or 0))
            total_amount += Decimal(str(row.get("total") or 0))
            normalized_items.append({
                "description": row.get("description", ""), "hsn_sac": row.get("hsn", ""),
                "quantity": row.get("qty", 0), "unit": row.get("unit", ""),
                "unit_rate": row.get("unit_price", 0), "taxable": row.get("taxable", 0),
                "total": row.get("total", 0), "validate_line_formula": True,
            })
    if item_buckets:
        tax_buckets.extend(item_buckets.values())
    else:
        for row in combined:
            taxable = Decimal(str(row.get("TAXABLE") or 0))
            rate = Decimal(str(row.get("RATE") or 0).replace("%", "") or 0)
            tax = (taxable * rate / Decimal("100")).quantize(Decimal("0.01"))
            tax_buckets.append({"tax_type": "GST", "rate": rate, "taxable": taxable, "tax": tax,
                                "hsn_sac": str(row.get("HSN CODE") or "")})
            total_amount += taxable + tax
    return NormalizedExtractionResult(
        document_id=document_id, method=ExtractionMethod.LEGACY_PARSER, pages=pages,
        document_type="Tax Invoice" if template == "sujal_tax_invoice" else "Stock Transfer",
        supplier="Sujal" if template == "sujal_tax_invoice" else "Flipkart",
        invoice_number=invoice_number, invoice_date=invoice_date, items=tuple(normalized_items),
        tax_buckets=tuple(tax_buckets), totals={"invoice_total": total_amount},
        quality=quality, fingerprint=fingerprint,
        warnings=(() if combined else ("Certified legacy parser returned no accounting rows",)),
    )
