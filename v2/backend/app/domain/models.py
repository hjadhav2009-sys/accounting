from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid4

from .enums import JobStatus, ValidationStatus


CURRENCY_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", Decimal(str(self.amount)).quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP))
        normalized_currency = self.currency.strip().upper()
        if len(normalized_currency) != 3:
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", normalized_currency)

    def _assert_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError("money currencies must match")

    def __add__(self, other: "Money") -> "Money":
        self._assert_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_currency(other)
        return Money(self.amount - other.amount, self.currency)


@dataclass(frozen=True)
class TaxBucket:
    tax_type: str
    rate: Decimal
    taxable: Money
    tax: Money
    hsn_sac: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", Decimal(str(self.rate)))
        if self.taxable.currency != self.tax.currency:
            raise ValueError("tax bucket currencies must match")


@dataclass(frozen=True)
class InvoiceHeader:
    invoice_number: str
    invoice_date: date | None
    supplier: str
    document_type: str
    company_id: UUID | None = None
    currency: str = "INR"


@dataclass(frozen=True)
class InvoiceLine:
    description: str
    quantity: Decimal
    unit_price: Money
    taxable: Money
    hsn_sac: str = ""
    tax_buckets: tuple[TaxBucket, ...] = ()


@dataclass(frozen=True)
class BankTransaction:
    transaction_date: date
    narration: str
    debit: Money | None = None
    credit: Money | None = None
    balance: Money | None = None
    mapped_ledger: str = ""


@dataclass(frozen=True)
class DocumentIdentity:
    document_id: UUID
    organization_id: UUID
    company_id: UUID
    sha256: str
    filename: str
    mime_type: str
    size: int
    created_at: datetime
    created_by: UUID


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    status: ValidationStatus
    source_reference: str = ""


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    issues: tuple[ValidationIssue, ...] = ()
    calculations: dict[str, str] = field(default_factory=dict)
    source_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    document_id: UUID
    header: InvoiceHeader | None
    lines: tuple[InvoiceLine, ...]
    tax_buckets: tuple[TaxBucket, ...]
    raw_legacy_rows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class VoucherResult:
    voucher_type: str
    reference: str
    xml: str
    validation: ValidationResult | None = None


@dataclass
class Job:
    job_type: str
    organization_id: UUID
    company_id: UUID
    created_by: UUID
    job_id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str = ""


@dataclass(frozen=True)
class AuditEvent:
    action: str
    organization_id: UUID
    company_id: UUID | None
    actor_id: UUID
    entity_type: str
    entity_id: UUID | str
    reason: str = ""
    previous_reference: str = ""
    new_reference: str = ""
    document_id: UUID | None = None
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class Organization:
    organization_id: UUID
    name: str


@dataclass(frozen=True)
class CompanyAccess:
    organization_id: UUID
    company_id: UUID
    user_id: UUID
    roles: frozenset[str]
