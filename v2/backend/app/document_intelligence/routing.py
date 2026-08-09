from __future__ import annotations

from dataclasses import dataclass

from .models import ExtractionQuality, FormatFingerprint


@dataclass(frozen=True)
class FormatRoute:
    route: str
    known: bool
    reason: str
    measurable_score: float | None = None


class KnownFormatRouter:
    def route(self, text: str, filename: str, quality: ExtractionQuality, fingerprint: FormatFingerprint) -> FormatRoute:
        if quality is ExtractionQuality.OCR_REQUIRED:
            return FormatRoute("ocr_required", False, "Native extraction contained insufficient text")
        return FormatRoute("unknown_format", False, "No approved company-scoped V2 template matched this fingerprint")
