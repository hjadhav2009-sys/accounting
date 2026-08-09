from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from ..document_intelligence.fingerprint import create_format_fingerprint
from ..document_intelligence.legacy_adapter import normalize_legacy_pdf
from ..document_intelligence.native_pdf import ExtractionQualityAssessor, NativePdfExtractor
from ..services.legacy import LegacyPdfToExcelService


class LegacyReferenceEngine:
    """Read-only certification reference. Never injected into the V2-native engine."""

    def process(self, content: bytes, filename: str) -> dict[str, Any]:
        pages = NativePdfExtractor().extract(content)
        text = "\n".join(page.text for page in pages)
        template = LegacyPdfToExcelService().detect_template(text)
        if template == "unknown":
            return {"status": "MISSING_LEGACY", "engine": "Legacy Reference", "canonical": {}, "template": template}
        quality = ExtractionQualityAssessor().assess(pages)
        normalized = normalize_legacy_pdf(uuid4(), template, text, filename, pages, quality, create_format_fingerprint(pages))
        rows = [dict(row) for row in normalized.items]
        canonical = {"invoice_number": normalized.invoice_number, "date": normalized.invoice_date,
            "document_type": normalized.document_type, "supplier": normalized.supplier, "rows": rows,
            "row_count": len(rows), "quantity": sum((Decimal(str(row.get("quantity") or 0)) for row in rows), Decimal("0")),
            "taxable": sum((Decimal(str(row.get("taxable") or 0)) for row in rows), Decimal("0")),
            "tax_buckets": list(normalized.tax_buckets), "invoice_total": normalized.totals.get("invoice_total")}
        return {"status": "REFERENCE_READY", "engine": "Legacy Reference", "template": template, "canonical": canonical}
