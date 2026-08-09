from __future__ import annotations

from .domain import AuditEvent


class InMemoryAuditRepository:
    """Small append-only audit repository used by foundation tests and adapters."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    def list_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)
