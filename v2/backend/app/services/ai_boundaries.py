from __future__ import annotations

from typing import Any, Protocol

from ..domain.enums import ProcessingMode


class DocumentIntelligenceService(Protocol):
    def propose(self, minimized_document: dict[str, Any]) -> dict[str, Any]: ...


class OcrService(Protocol):
    def extract(self, document_bytes: bytes) -> dict[str, Any]: ...


class LocalAiService(DocumentIntelligenceService, Protocol): ...
class CloudAiService(DocumentIntelligenceService, Protocol): ...


class PrivacyService(Protocol):
    def minimize(self, document: dict[str, Any], mode: ProcessingMode) -> dict[str, Any]: ...


class AiQuotaService(Protocol):
    def may_run(self, company_id: str, user_id: str, mode: ProcessingMode) -> bool: ...


class TemplateGenerationService(Protocol):
    def draft_template(self, proposal: dict[str, Any]) -> dict[str, Any]: ...
