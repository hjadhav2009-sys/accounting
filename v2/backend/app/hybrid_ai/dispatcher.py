from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable
from uuid import UUID


@dataclass(frozen=True)
class ResetQueuedJob:
    job_id: UUID
    not_before: datetime
    document_exists: bool
    template_revision_matches: bool
    cancel_requested: bool
    policy_permits_cloud: bool
    resume: Callable[[], None]


class ResetDispatcher:
    """Fail-closed dispatcher with an injected UTC clock for certification."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def dispatch(self, jobs: Iterable[ResetQueuedJob], quota_verifiable: Callable[[], bool]) -> tuple[UUID, ...]:
        now = self._clock()
        if now.tzinfo is None: raise ValueError("dispatcher clock must be timezone-aware")
        resumed: list[UUID] = []
        for job in jobs:
            eligible = (job.not_before <= now and job.document_exists and
                        job.template_revision_matches and not job.cancel_requested and
                        job.policy_permits_cloud)
            if not eligible or not quota_verifiable():
                continue
            job.resume()
            resumed.append(job.job_id)
        return tuple(resumed)
