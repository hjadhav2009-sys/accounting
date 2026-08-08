from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from ..domain.models import AuditEvent, DocumentIdentity, Job


Record = Mapping[str, Any]


class CompanyRepository(Protocol):
    def list_companies(self) -> Sequence[Record]: ...
    def get_company(self, name: str) -> Record | None: ...


class LedgerRepository(Protocol):
    def party_ledger(self, company_name: str, platform: str) -> str: ...


class MappingRepository(Protocol):
    def map_ledger(self, company_name: str, tool: str, platform: str, description: str, voucher_type: str = "") -> tuple[str, str]: ...


class BankRepository(Protocol):
    def list_bank_accounts(self, company_name: str) -> Sequence[Record]: ...


class VoucherRuleRepository(Protocol):
    def get_rule(self, company_name: str, platform: str, document_type: str) -> Record: ...


class DocumentRepository(Protocol):
    def get(self, document_id: UUID) -> DocumentIdentity | None: ...


class TemplateRepository(Protocol):
    def get_version(self, template_version_id: UUID) -> Record | None: ...


class AuditRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class JobRepository(Protocol):
    def save(self, job: Job) -> None: ...
    def get(self, job_id: UUID) -> Job | None: ...
