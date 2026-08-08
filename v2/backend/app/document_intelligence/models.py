from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    REGISTERED = "REGISTERED"
    DUPLICATE = "DUPLICATE"
    EXTRACTING = "EXTRACTING"
    OCR_REQUIRED = "OCR_REQUIRED"
    EXTRACTED = "EXTRACTED"
    VALIDATING = "VALIDATING"
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class ExtractionQuality(StrEnum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    OCR_REQUIRED = "OCR_REQUIRED"


class ExtractionMethod(StrEnum):
    NATIVE_TEXT = "NATIVE_TEXT"
    LEGACY_PARSER = "LEGACY_PARSER"
    LOCAL_OCR = "LOCAL_OCR"


class DuplicateStatus(StrEnum):
    NOT_DUPLICATE = "NOT_DUPLICATE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    EXACT_BUSINESS_DUPLICATE = "EXACT_BUSINESS_DUPLICATE"


class Severity(StrEnum):
    INFO = "INFO"
    REVIEW = "REVIEW"
    BLOCKING = "BLOCKING"


class ReviewReason(StrEnum):
    UNKNOWN_FORMAT = "UNKNOWN_FORMAT"
    LOW_EXTRACTION_CONFIDENCE = "LOW_EXTRACTION_CONFIDENCE"
    OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_FAILED = "OCR_FAILED"
    OCR_TIMEOUT = "OCR_TIMEOUT"
    OCR_EMPTY = "OCR_EMPTY"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    GST_MISMATCH = "GST_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    BANK_RECONCILIATION_FAILED = "BANK_RECONCILIATION_FAILED"
    UNKNOWN_LEDGER = "UNKNOWN_LEDGER"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"


class ErrorCode(StrEnum):
    PDF_CORRUPT = "PDF_CORRUPT"
    PDF_PASSWORD_PROTECTED = "PDF_PASSWORD_PROTECTED"
    PDF_NO_TEXT = "PDF_NO_TEXT"
    OCR_FAILED = "OCR_FAILED"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    OCR_TIMEOUT = "OCR_TIMEOUT"
    OCR_EMPTY = "OCR_EMPTY"
    FORMAT_UNKNOWN = "FORMAT_UNKNOWN"
    REQUIRED_FIELD_MISSING = "REQUIRED_FIELD_MISSING"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    GST_MISMATCH = "GST_MISMATCH"
    INVOICE_TOTAL_MISMATCH = "INVOICE_TOTAL_MISMATCH"
    BANK_BALANCE_MISMATCH = "BANK_BALANCE_MISMATCH"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
    FILE_EMPTY = "FILE_EMPTY"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    PAGE_LIMIT_EXCEEDED = "PAGE_LIMIT_EXCEEDED"
    MIME_INVALID = "MIME_INVALID"
    FILENAME_INVALID = "FILENAME_INVALID"


@dataclass(frozen=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float

    def __post_init__(self) -> None:
        if self.page_width <= 0 or self.page_height <= 0:
            raise ValueError("page dimensions must be positive")
        if not (0 <= self.x0 <= self.x1 <= self.page_width and 0 <= self.y0 <= self.y1 <= self.page_height):
            raise ValueError("bounding box must be inside the page")

    @property
    def normalized(self) -> tuple[float, float, float, float]:
        return (self.x0 / self.page_width, self.y0 / self.page_height,
                self.x1 / self.page_width, self.y1 / self.page_height)


@dataclass(frozen=True)
class SourceReference:
    page_number: int
    method: ExtractionMethod
    bounding_box: BoundingBox | None = None
    table_index: int | None = None
    row_index: int | None = None
    column_index: int | None = None
    original_token: str = ""


@dataclass(frozen=True)
class TextSpan:
    text: str
    bounding_box: BoundingBox
    font: str = ""
    size: float = 0
    flags: int = 0
    reading_order: int = 0


@dataclass(frozen=True)
class TextBlock:
    text: str
    bounding_box: BoundingBox
    spans: tuple[TextSpan, ...] = ()
    reading_order: int = 0


@dataclass(frozen=True)
class TableCell:
    text: str
    row_index: int
    column_index: int
    bounding_box: BoundingBox | None = None


@dataclass(frozen=True)
class TableRow:
    row_index: int
    cells: tuple[TableCell, ...]


@dataclass(frozen=True)
class ExtractedTable:
    table_index: int
    rows: tuple[TableRow, ...]
    bounding_box: BoundingBox | None = None


@dataclass(frozen=True)
class ImageRegion:
    bounding_box: BoundingBox
    image_index: int


@dataclass(frozen=True)
class DocumentPage:
    page_number: int
    width: float
    height: float
    text: str
    blocks: tuple[TextBlock, ...] = ()
    tables: tuple[ExtractedTable, ...] = ()
    images: tuple[ImageRegion, ...] = ()


@dataclass(frozen=True)
class DetectedField:
    name: str
    value: Any
    source: SourceReference | None
    method: ExtractionMethod
    confidence: Decimal | None = None
    original_token: str = ""
    normalization: str = ""


@dataclass(frozen=True)
class ExtractionCandidate:
    field_name: str
    value: Any
    source: SourceReference | None
    method: ExtractionMethod
    confidence: Decimal | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityAssessment:
    status: ExtractionQuality
    characters: int
    text_density: Decimal
    blank_page_ratio: Decimal
    numeric_token_density: Decimal
    garbled_character_ratio: Decimal
    line_fragmentation: Decimal
    page_coverage: Decimal
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormatFingerprint:
    signature: str
    anchors: tuple[str, ...]
    page_count: int
    dimensions: tuple[tuple[int, int], ...]
    table_headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class NormalizedExtractionResult:
    document_id: UUID
    method: ExtractionMethod
    pages: tuple[DocumentPage, ...]
    document_type: str = ""
    supplier: str = ""
    invoice_number: str = ""
    invoice_date: date | None = None
    currency: str = "INR"
    items: tuple[dict[str, Any], ...] = ()
    tax_buckets: tuple[dict[str, Any], ...] = ()
    totals: dict[str, Any] = field(default_factory=dict)
    bank_transactions: tuple[dict[str, Any], ...] = ()
    fields: tuple[DetectedField, ...] = ()
    warnings: tuple[str, ...] = ()
    quality: QualityAssessment | None = None
    fingerprint: FormatFingerprint | None = None
    format_family_id: UUID | None = None
    template_version_id: UUID | None = None


@dataclass(frozen=True)
class ValidationFinding:
    validator: str
    status: str
    severity: Severity
    message: str
    expected: str = ""
    actual: str = ""
    difference: str = ""
    source_references: tuple[SourceReference, ...] = ()
    error_code: ErrorCode | None = None


@dataclass(frozen=True)
class AccountingValidationReport:
    status: str
    findings: tuple[ValidationFinding, ...]
    calculations: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IntakeContext:
    organization_id: UUID
    company_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class DocumentRecord:
    document_id: UUID
    organization_id: UUID
    company_id: UUID
    original_filename: str
    safe_filename: str
    mime_type: str
    size: int
    sha256: str
    storage_key: str
    page_count: int
    status: DocumentStatus
    created_by: UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duplicate_of_document_id: UUID | None = None
    document_type: str = ""
    supplier: str = ""
    invoice_number: str = ""
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    extraction_method: ExtractionMethod | None = None
    quality_status: ExtractionQuality | None = None
    error_code: ErrorCode | None = None
    batch_id: UUID | None = None


@dataclass(frozen=True)
class BatchRecord:
    batch_id: UUID
    organization_id: UUID
    company_id: UUID
    created_by: UUID
    total: int
    processed: int = 0
    verified: int = 0
    review: int = 0
    blocked: int = 0
    duplicate: int = 0
    failed: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (UUID, date, datetime, StrEnum)):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
