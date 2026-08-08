from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class TemplateInvalid(ValueError):
    pass


class TemplateConflict(RuntimeError):
    pass


class TemplateImmutable(RuntimeError):
    pass


class TemplatePermissionDenied(PermissionError):
    pass


class TemplateStatus(StrEnum):
    DRAFT = "DRAFT"
    TESTING = "TESTING"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


class DocumentMode(StrEnum):
    INVOICE = "INVOICE"
    MARKETPLACE = "MARKETPLACE"
    BANK = "BANK"
    STOCK_TRANSFER = "STOCK_TRANSFER"
    GENERIC = "GENERIC"


@dataclass(frozen=True)
class StudioContext:
    organization_id: UUID
    company_id: UUID
    user_id: UUID
    roles: frozenset[str] = frozenset({"VIEWER"})


@dataclass
class EditorCommand:
    before: dict[str, Any]
    after: dict[str, Any]
    label: str
    command_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CommandHistory:
    """UI-independent undo/redo model. Cursor movement is intentionally excluded."""

    def __init__(self, initial: dict[str, Any]) -> None:
        import copy
        self.current = copy.deepcopy(initial)
        self._undo: list[EditorCommand] = []
        self._redo: list[EditorCommand] = []

    def apply(self, next_value: dict[str, Any], label: str) -> dict[str, Any]:
        import copy
        command = EditorCommand(copy.deepcopy(self.current), copy.deepcopy(next_value), label)
        self._undo.append(command); self._redo.clear(); self.current = copy.deepcopy(next_value)
        return copy.deepcopy(self.current)

    def undo(self) -> dict[str, Any]:
        import copy
        if not self._undo:
            return copy.deepcopy(self.current)
        command = self._undo.pop(); self._redo.append(command); self.current = copy.deepcopy(command.before)
        return copy.deepcopy(self.current)

    def redo(self) -> dict[str, Any]:
        import copy
        if not self._redo:
            return copy.deepcopy(self.current)
        command = self._redo.pop(); self._undo.append(command); self.current = copy.deepcopy(command.after)
        return copy.deepcopy(self.current)
