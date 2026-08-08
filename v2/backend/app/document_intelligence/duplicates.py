from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ..services.fingerprints import accounting_duplicate_signature
from .models import DuplicateStatus


@dataclass(frozen=True)
class BusinessDuplicateResult:
    status: DuplicateStatus
    signature: str
    matching_document_ids: tuple[UUID, ...] = ()


class AccountingDuplicateDetector:
    def detect(self, company: str, fields: dict[str, Any], existing: dict[str, tuple[UUID, ...]]) -> BusinessDuplicateResult:
        required = (fields.get("supplier"), fields.get("document_type"), fields.get("invoice_number"),
                    fields.get("invoice_date"), fields.get("total_amount"))
        if not all(value not in (None, "") for value in required):
            return BusinessDuplicateResult(DuplicateStatus.NOT_DUPLICATE, "")
        signature = accounting_duplicate_signature(company, *required)
        matches = existing.get(signature, ())
        status = DuplicateStatus.EXACT_BUSINESS_DUPLICATE if matches else DuplicateStatus.NOT_DUPLICATE
        return BusinessDuplicateResult(status, signature, tuple(matches))
