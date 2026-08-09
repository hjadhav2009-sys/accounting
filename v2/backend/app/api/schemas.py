from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"
    api_version: str
    database_adapter_mode: str


class SystemInfoResponse(ApiModel):
    application: str
    api_version: str
    environment: str
    database_adapter_mode: str
    storage_mode: str
    legacy_authority: str
    postgres_cutover: str
    ai_inference: str
    ai_mode: str
    ai_billing_mode: str
    sqlite_authoritative: str
    postgres_connected: str
    shadow_mode: str


class DevelopmentStatusResponse(ApiModel):
    sqlite_authoritative: bool
    postgres_connected: bool
    shadow_mode: bool
    last_migration_run: datetime | None = None
    parity_comparisons: int = Field(ge=0)
    parity_mismatches: int = Field(ge=0)
    normalization_conflicts: int = Field(ge=0)


class CompanySummary(ApiModel):
    company_id: UUID
    display_name: str
    state: str | None = None


class DocumentSummary(ApiModel):
    document_id: UUID
    company_id: UUID
    filename: str
    status: Literal["VERIFIED", "REVIEW", "BLOCKED"]
    created_at: datetime


class DocumentUploadResult(ApiModel):
    document_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duplicate: bool


class ExtractionSummary(ApiModel):
    document_id: UUID
    format_family: str | None = None
    line_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ValidationSummary(ApiModel):
    status: Literal["VERIFIED", "REVIEW", "BLOCKED"]
    issue_count: int = Field(ge=0)


class BankSummary(ApiModel):
    company_id: UUID
    account_id: UUID
    mapped_transactions: int = Field(ge=0)
    unmapped_transactions: int = Field(ge=0)


class MarketplaceSummary(ApiModel):
    company_id: UUID
    platform: str
    voucher_count: int = Field(ge=0)
    unmatched_mappings: int = Field(ge=0)


class TemplateSummary(ApiModel):
    template_id: UUID
    family_id: UUID
    version: int = Field(ge=1)
    status: Literal["DRAFT", "APPROVED", "REJECTED"]


class ReviewSummary(ApiModel):
    review_id: UUID
    document_id: UUID
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]
    reason_code: str
