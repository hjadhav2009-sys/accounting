from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .models import ErrorCode


WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class DocumentSecurityError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ResourceLimits:
    maximum_file_size: int = 25 * 1024 * 1024
    maximum_pages: int = 200
    native_extraction_concurrency: int = 2
    ocr_concurrency: int = 1
    ocr_timeout_seconds: int = 120
    ocr_max_pages: int = 50


def safe_filename(filename: str) -> str:
    raw = str(filename or "").strip()
    if not raw or raw in {".", ".."}:
        raise DocumentSecurityError(ErrorCode.FILENAME_INVALID, "A valid filename is required")
    if Path(raw).is_absolute() or "/" in raw or "\\" in raw or ".." in Path(raw).parts:
        raise DocumentSecurityError(ErrorCode.FILENAME_INVALID, "Filename paths are not allowed")
    stem = Path(raw).stem.strip(" .")
    if stem.upper() in WINDOWS_RESERVED:
        raise DocumentSecurityError(ErrorCode.FILENAME_INVALID, "Reserved filename is not allowed")
    cleaned_stem = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._") or "document"
    suffix = Path(raw).suffix.lower()
    if suffix != ".pdf":
        raise DocumentSecurityError(ErrorCode.MIME_INVALID, "Only PDF documents are accepted")
    return f"{cleaned_stem[:120]}.pdf"


def validate_pdf_upload(content: bytes, filename: str, mime_type: str, limits: ResourceLimits) -> str:
    cleaned = safe_filename(filename)
    if not content:
        raise DocumentSecurityError(ErrorCode.FILE_EMPTY, "The uploaded file is empty")
    if len(content) > limits.maximum_file_size:
        raise DocumentSecurityError(ErrorCode.FILE_TOO_LARGE, "The uploaded file exceeds the configured size limit")
    if mime_type.lower().split(";", 1)[0].strip() != "application/pdf":
        raise DocumentSecurityError(ErrorCode.MIME_INVALID, "MIME type must be application/pdf")
    if not content.startswith(b"%PDF-"):
        raise DocumentSecurityError(ErrorCode.MIME_INVALID, "File content is not a PDF")
    return cleaned
