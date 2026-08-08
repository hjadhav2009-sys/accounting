from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from enum import StrEnum
import unicodedata

from .models import BoundingBox, ExtractionMethod, SourceReference


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: float
    source: SourceReference


@dataclass(frozen=True)
class OcrPageResult:
    page_number: int
    text: str
    tokens: tuple[OcrToken, ...]
    engine: str
    version: str
    duration_seconds: float


class OcrService(Protocol):
    @property
    def available(self) -> bool: ...
    def extract_page(self, pdf_content: bytes, page_number: int) -> OcrPageResult: ...


class OcrUnavailableError(RuntimeError):
    pass


class OcrProcessError(RuntimeError):
    pass


class OcrTimeoutError(RuntimeError):
    pass


class OcrEmptyError(RuntimeError):
    pass


class OcrConfidenceTier(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


class TesseractOcrService:
    """Local, page-at-a-time OCR. It never sends document content over a network."""

    def __init__(self, executable: str | Path | None = None, dpi: int = 200, timeout_seconds: int = 120) -> None:
        common = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        selected = str(executable) if executable else (shutil.which("tesseract") or (str(common) if common.exists() else ""))
        self.executable = selected
        self.dpi = max(100, min(300, dpi))
        self.timeout_seconds = max(10, min(600, timeout_seconds))

    @property
    def available(self) -> bool:
        return bool(self.executable and Path(self.executable).exists())

    @property
    def version(self) -> str:
        if not self.available:
            return "unavailable"
        result = subprocess.run([self.executable, "--version"], capture_output=True, text=True, timeout=10, check=False)
        return (result.stdout.splitlines() or ["unknown"])[0][:80]

    def extract_page(self, pdf_content: bytes, page_number: int) -> OcrPageResult:
        if not self.available:
            raise OcrUnavailableError("Tesseract is not installed")
        import pymupdf

        started = time.perf_counter()
        document = pymupdf.open(stream=pdf_content, filetype="pdf")
        try:
            if not 1 <= page_number <= document.page_count:
                raise IndexError(page_number)
            page = document[page_number - 1]
            scale = self.dpi / 72
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            width, height = float(pixmap.width), float(pixmap.height)
            with tempfile.TemporaryDirectory() as temp:
                image = Path(temp) / "page.png"
                pixmap.save(image)
                try:
                    result = subprocess.run([self.executable, str(image), "stdout", "-l", "eng", "tsv"], capture_output=True,
                                            text=True, timeout=self.timeout_seconds, check=False)
                except subprocess.TimeoutExpired as exc:
                    raise OcrTimeoutError(f"local OCR exceeded {self.timeout_seconds} seconds") from exc
                if result.returncode != 0:
                    raise OcrProcessError(f"local OCR failed with exit code {result.returncode}")
        finally:
            document.close()
        tokens: list[OcrToken] = []
        lines: dict[tuple[str, str, str, str], list[str]] = {}
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            confidence = max(0.0, min(100.0, float(row.get("conf") or 0))) / 100
            x, y = float(row["left"]), float(row["top"])
            box = BoundingBox(x, y, x + float(row["width"]), y + float(row["height"]), width, height)
            tokens.append(OcrToken(text, confidence, SourceReference(page_number, ExtractionMethod.LOCAL_OCR, box, original_token=text)))
            key = (str(row.get("block_num")), str(row.get("par_num")), str(row.get("line_num")), str(row.get("page_num")))
            lines.setdefault(key, []).append(text)
        if not tokens:
            raise OcrEmptyError("local OCR recognized no text")
        reconstructed = "\n".join(" ".join(words) for words in lines.values())
        return OcrPageResult(page_number, reconstructed, tuple(tokens),
                             "tesseract", self.version, time.perf_counter() - started)


OCR_CONFUSIONS = {"O": "0", "I": "1", "l": "1", "S": "5", "B": "8"}


def detect_digit_confusions(token: str) -> tuple[str, ...]:
    return tuple(f"{char}/{OCR_CONFUSIONS[char]}" for char in token if char in OCR_CONFUSIONS)


def normalize_ocr_token(token: str) -> str:
    """Apply safe formatting normalization without substituting ambiguous characters."""
    value = unicodedata.normalize("NFKC", str(token or "")).replace("\u2212", "-")
    value = " ".join(value.split())
    if value.startswith("₹"):
        value = value[1:].strip()
    if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?", value):
        value = value.replace(",", "")
    return value


def confidence_tier(confidence: float, critical_numeric: bool = False) -> OcrConfidenceTier:
    """Tiers calibrated from the committed synthetic numeric benchmark, not truth authority."""
    if confidence < 0:
        return OcrConfidenceTier.UNAVAILABLE
    # Correct numeric benchmark tokens ranged from 0.9079 to 0.9684. The 0.85
    # review floor leaves a measured margin below the weakest correct token;
    # VERIFIED still requires independent accounting reconciliation.
    high_floor = 0.95 if critical_numeric else 0.90
    medium_floor = 0.85 if critical_numeric else 0.70
    if confidence >= high_floor:
        return OcrConfidenceTier.HIGH
    if confidence >= medium_floor:
        return OcrConfidenceTier.MEDIUM
    return OcrConfidenceTier.LOW
