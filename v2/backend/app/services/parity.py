from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable


class ParityStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MISSING_IN_POSTGRES = "MISSING_IN_POSTGRES"
    EXTRA_IN_POSTGRES = "EXTRA_IN_POSTGRES"
    NORMALIZATION_DIFFERENCE = "NORMALIZATION_DIFFERENCE"
    SHADOW_ERROR = "SHADOW_ERROR"


@dataclass(frozen=True)
class ParityObservation:
    query_type: str
    status: ParityStatus
    compared_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Values are intentionally excluded: reports must not become a PII side channel.


class ParityRecorder:
    def __init__(self) -> None:
        self._observations: list[ParityObservation] = []

    def record(self, observation: ParityObservation) -> None:
        self._observations.append(observation)

    def summary(self) -> dict[str, Any]:
        counts = {status.value: 0 for status in ParityStatus}
        for item in self._observations:
            counts[item.status.value] += 1
        return {"comparisons": len(self._observations), "counts": counts,
                "last_run": self._observations[-1].compared_at if self._observations else None}


def classify(authoritative: Any, shadow: Any) -> ParityStatus:
    if authoritative == shadow:
        return ParityStatus.MATCH
    if authoritative in (None, "", [], ()) and shadow not in (None, "", [], ()):
        return ParityStatus.EXTRA_IN_POSTGRES
    if shadow in (None, "", [], ()) and authoritative not in (None, "", [], ()):
        return ParityStatus.MISSING_IN_POSTGRES
    if isinstance(authoritative, str) and isinstance(shadow, str) and authoritative.strip().casefold() == shadow.strip().casefold():
        return ParityStatus.NORMALIZATION_DIFFERENCE
    return ParityStatus.MISMATCH


class ShadowRepositories:
    """Observes PostgreSQL but always returns the certified SQLite decision."""

    def __init__(self, sqlite_repository: Any, postgres_repository: Any, recorder: ParityRecorder) -> None:
        self.sqlite = sqlite_repository
        self.postgres = postgres_repository
        self.recorder = recorder

    def _call(self, name: str, *args, **kwargs):
        authoritative = getattr(self.sqlite, name)(*args, **kwargs)
        try:
            shadow = getattr(self.postgres, name)(*args, **kwargs)
            status = classify(authoritative, shadow)
        except Exception:
            status = ParityStatus.SHADOW_ERROR
        self.recorder.record(ParityObservation(name, status))
        return authoritative

    def __getattr__(self, name: str) -> Callable[..., Any]:
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self._call(name, *args, **kwargs)
