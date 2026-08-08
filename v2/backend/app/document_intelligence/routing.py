from __future__ import annotations

from dataclasses import dataclass

from apps.marketplace_pdf_to_tally.engine import detect_doc_type, detect_platform
from ..services.legacy import LegacyPdfToExcelService

from .models import ExtractionQuality, FormatFingerprint


@dataclass(frozen=True)
class FormatRoute:
    route: str
    known: bool
    reason: str
    measurable_score: float | None = None


class KnownFormatRouter:
    def route(self, text: str, filename: str, quality: ExtractionQuality, fingerprint: FormatFingerprint) -> FormatRoute:
        template = LegacyPdfToExcelService().detect_template(text)
        if template != "unknown":
            return FormatRoute(f"legacy_pdf:{template}", True, "Exact certified legacy template anchors matched", 1.0)
        platform = detect_platform(text, filename)
        document_type = detect_doc_type(text)
        if platform != "unknown" and document_type != "Unknown":
            return FormatRoute(f"legacy_marketplace:{platform}:{document_type}", True,
                               "Certified marketplace supplier and document-type anchors matched", 1.0)
        bank_signals = ("opening balance", "closing balance", "narration", "withdrawal", "deposit")
        matched = sum(signal in text.casefold() for signal in bank_signals)
        if matched >= 3:
            return FormatRoute("legacy_bank:statement", True, "At least three measurable bank-statement anchors matched", matched / len(bank_signals))
        if quality is ExtractionQuality.OCR_REQUIRED:
            return FormatRoute("ocr_required", False, "Native extraction contained insufficient text")
        return FormatRoute("unknown_format", False, "No approved deterministic format anchors matched")
