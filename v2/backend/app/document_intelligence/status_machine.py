from __future__ import annotations

from .models import DocumentStatus


TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.REGISTERED, DocumentStatus.DUPLICATE, DocumentStatus.FAILED}),
    DocumentStatus.REGISTERED: frozenset({DocumentStatus.EXTRACTING, DocumentStatus.ARCHIVED, DocumentStatus.FAILED}),
    DocumentStatus.DUPLICATE: frozenset({DocumentStatus.ARCHIVED}),
    DocumentStatus.EXTRACTING: frozenset({DocumentStatus.OCR_REQUIRED, DocumentStatus.EXTRACTED, DocumentStatus.REVIEW, DocumentStatus.FAILED}),
    DocumentStatus.OCR_REQUIRED: frozenset({DocumentStatus.EXTRACTED, DocumentStatus.REVIEW, DocumentStatus.FAILED}),
    DocumentStatus.EXTRACTED: frozenset({DocumentStatus.VALIDATING, DocumentStatus.REVIEW, DocumentStatus.FAILED}),
    DocumentStatus.VALIDATING: frozenset({DocumentStatus.VERIFIED, DocumentStatus.REVIEW, DocumentStatus.BLOCKED, DocumentStatus.FAILED}),
    DocumentStatus.VERIFIED: frozenset({DocumentStatus.ARCHIVED}),
    DocumentStatus.REVIEW: frozenset({DocumentStatus.VALIDATING, DocumentStatus.ARCHIVED}),
    DocumentStatus.BLOCKED: frozenset({DocumentStatus.REVIEW, DocumentStatus.ARCHIVED}),
    DocumentStatus.FAILED: frozenset({DocumentStatus.ARCHIVED}),
    DocumentStatus.ARCHIVED: frozenset(),
}


class InvalidDocumentTransition(ValueError):
    pass


class DocumentStatusMachine:
    def transition(self, current: DocumentStatus, target: DocumentStatus) -> DocumentStatus:
        if target not in TRANSITIONS[current]:
            raise InvalidDocumentTransition(f"{current} cannot transition to {target}")
        return target
