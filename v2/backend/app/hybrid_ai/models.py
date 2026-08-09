from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class AiMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    HYBRID_PRIVATE = "HYBRID_PRIVATE"
    FULL_CLOUD_DOCUMENT_ANALYSIS = "FULL_CLOUD_DOCUMENT_ANALYSIS"


class BillingMode(StrEnum):
    FREE_ONLY = "FREE_ONLY"
    PAID_ALLOWED = "PAID_ALLOWED"


class PrivacyMode(StrEnum):
    STRICT = "STRICT"
    BALANCED = "BALANCED"
    OFF_ADMIN_ONLY = "OFF_ADMIN_ONLY"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ResultState(StrEnum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_MORE_CONTEXT = "NEEDS_MORE_CONTEXT"
    LOCAL_RUNTIME_UNAVAILABLE = "LOCAL_RUNTIME_UNAVAILABLE"
    CLOUD_QUOTA_BLOCKED = "CLOUD_QUOTA_BLOCKED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    PROVIDER_FAILED = "PROVIDER_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CANCELLED = "CANCELLED"


class Capability(StrEnum):
    TEXT = "TEXT"
    VISION = "VISION"
    TOOLS = "TOOLS"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    REASONING = "REASONING"


@dataclass(frozen=True)
class TenantContext:
    organization_id: UUID
    company_id: UUID
    user_id: UUID
    roles: frozenset[str]


@dataclass(frozen=True)
class AiAction:
    action: str
    payload: dict[str, Any]
    rationale: str
    source_references: tuple[str, ...] = ()
    confidence: ConfidenceBand = ConfidenceBand.LOW
    validation_impact: str = "requires deterministic preview"
    risk: str = "HIGH"


@dataclass(frozen=True)
class AiTemplateProposal:
    summary: str
    actions: tuple[AiAction, ...]
    provider: str
    model: str
    prompt_version: str
    proposal_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    provider_reported_neurons: int | None = None
    application_estimated_neurons: int = 0
    accounted_neurons: int = 0
    accounting_basis: str = "NONE"
    provider_usage_verifiable: bool = False


@dataclass(frozen=True)
class ProviderResult:
    payload: dict[str, Any]
    usage: ProviderUsage
    provider: str
    model: str
    latency_ms: int


ALLOWED_TEMPLATE_ACTIONS = frozenset({
    "create_field", "update_field", "delete_field", "create_table", "update_table",
    "create_anchor", "create_ignore_region",
})

PROHIBITED_INTENTS = frozenset({
    "approve_template", "post_voucher", "reconcile_bank", "delete_document",
    "change_permissions", "disable_validation", "execute_code", "fetch_url",
})
