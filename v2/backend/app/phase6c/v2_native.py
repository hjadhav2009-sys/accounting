from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..document_intelligence.fingerprint import create_format_fingerprint
from ..document_intelligence.models import ExtractionQuality, to_jsonable
from ..document_intelligence.native_pdf import ExtractionQualityAssessor, NativePdfExtractor
from ..document_intelligence.ocr import OcrService
from ..document_intelligence.security import ResourceLimits
from ..document_intelligence.validation import AccountingValidationEngine, RequiredFieldValidator
from ..template_studio.engine import TemplateRuleEngine


TemplateLookup = Callable[[str], dict[str, Any] | None]


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "").replace("%", "").strip())
    except InvalidOperation:
        return Decimal("0")


def _evidence(pages: tuple[Any, ...]) -> dict[str, Any]:
    serialized = to_jsonable(pages)
    fields: list[dict[str, Any]] = []
    for page in serialized:
        for block in page.get("text_blocks", []):
            for span in block.get("spans", []):
                fields.append({
                    "text": span.get("text", ""), "value": span.get("text", ""), "confidence": "1",
                    "source": {"page_number": page["page_number"], "bounding_box": span.get("bounding_box")},
                })
    return {"pages": serialized, "fields": fields}


def _canonical(extracted: dict[str, Any]) -> dict[str, Any]:
    fields = {str(item.get("field")): item.get("value") for item in extracted.get("fields", [])}
    rows = [dict(item.get("values", {})) for item in extracted.get("item_rows", [])]
    taxes = [dict(item.get("values", {})) for item in extracted.get("tax_buckets", [])]
    aliases = {
        "invoice_number": ("invoice_number", "invoice_no", "invoice_id"),
        "date": ("invoice_date", "date"), "document_type": ("document_type",),
        "supplier": ("supplier", "party", "party_name"), "subtotal": ("subtotal", "taxable"),
        "round_off": ("round_off", "rounding"), "invoice_total": ("invoice_total", "total", "grand_total"),
    }
    result: dict[str, Any] = {"rows": rows, "tax_buckets": taxes, "row_count": len(rows)}
    for target, names in aliases.items():
        result[target] = next((fields[name] for name in names if fields.get(name) not in (None, "")), None)
    result["quantity"] = sum((_decimal(row.get("quantity", row.get("qty"))) for row in rows), Decimal("0"))
    result["taxable"] = sum((_decimal(row.get("taxable")) for row in rows), Decimal("0"))
    result["tax_amount"] = sum((_decimal(row.get("tax_amount", row.get("gst_amount"))) for row in rows), Decimal("0"))
    return result


@dataclass
class V2NativeDocumentEngine:
    """Independent native/template path. Its dependency graph excludes all reference adapters."""

    template_lookup: TemplateLookup
    ocr: OcrService | None = None
    limits: ResourceLimits = ResourceLimits()

    def process(self, content: bytes, filename: str) -> dict[str, Any]:
        pages = NativePdfExtractor().extract(content, self.limits)
        quality = ExtractionQualityAssessor().assess(pages)
        used_ocr = False
        if quality.status is ExtractionQuality.OCR_REQUIRED and self.ocr and self.ocr.available:
            replacements = {page.page_number: self.ocr.extract_page(content, page.page_number)
                            for page in pages if ExtractionQualityAssessor().assess((page,)).status is ExtractionQuality.OCR_REQUIRED}
            if replacements:
                from dataclasses import replace
                pages = tuple(replace(page, text=replacements[page.page_number].text)
                              if page.page_number in replacements else page for page in pages)
                quality = ExtractionQualityAssessor().assess(pages)
                used_ocr = True
        fingerprint = create_format_fingerprint(pages)
        template = self.template_lookup(fingerprint.signature)
        if not template:
            return {"status": "BLOCKED", "reason": "NO_APPROVED_V2_TEMPLATE", "filename": filename,
                    "fingerprint": fingerprint.signature, "engine": "V2_NATIVE", "reference_calls": 0,
                    "used_ocr": used_ocr, "draft_required": True, "canonical": {}}
        if template.get("engine") != "VISUAL_RULES" or template.get("status") != "APPROVED":
            return {"status": "BLOCKED", "reason": "TEMPLATE_NOT_APPROVED_V2", "filename": filename,
                    "fingerprint": fingerprint.signature, "engine": "V2_NATIVE", "reference_calls": 0,
                    "used_ocr": used_ocr, "draft_required": True, "canonical": {}}
        extracted = TemplateRuleEngine().extract(template["definition"], _evidence(pages))
        canonical = _canonical(extracted)
        validation_payload = {"document_type": canonical.get("document_type"), "supplier": canonical.get("supplier"),
            "invoice_number": canonical.get("invoice_number"), "invoice_date": canonical.get("date"),
            "items": tuple(canonical.get("rows", [])), "tax_buckets": tuple(canonical.get("tax_buckets", [])),
            "invoice_total": canonical.get("invoice_total")}
        validation = AccountingValidationEngine((RequiredFieldValidator(
            ("document_type", "supplier", "invoice_number", "invoice_date")),
            *AccountingValidationEngine().validators)).validate(validation_payload)
        return {"status": validation.status, "reason": "APPROVED_V2_TEMPLATE", "filename": filename,
                "fingerprint": fingerprint.signature, "engine": "V2 Template", "reference_calls": 0,
                "used_ocr": used_ocr, "draft_required": False, "template_version_id": template["id"],
                "template_version": template["version"], "format_family": template["family_name"],
                "extraction": extracted, "validation": to_jsonable(validation), "canonical": to_jsonable(canonical)}
