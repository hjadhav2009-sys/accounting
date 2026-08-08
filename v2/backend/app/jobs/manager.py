from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ..domain.enums import JobStatus
from ..domain.models import Job


TRANSITIONS = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.REVIEW, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.REVIEW: {JobStatus.RUNNING, JobStatus.COMPLETED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}


class InvalidJobTransition(ValueError):
    pass


class InMemoryJobManager:
    """Development-only process-local job store; no broker or persistence."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, Job] = {}

    def save(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: UUID) -> Job | None:
        return self._jobs.get(job_id)

    def transition(self, job_id: UUID, status: JobStatus, progress: int | None = None, error_code: str = "") -> Job:
        job = self._jobs[job_id]
        if status not in TRANSITIONS[job.status]:
            raise InvalidJobTransition(f"{job.status} cannot transition to {status}")
        now = datetime.now(timezone.utc)
        if status is JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            job.completed_at = now
        job.status = status
        job.progress = max(0, min(100, progress if progress is not None else job.progress))
        job.error_code = error_code[:80]
        return job


class PersistentJobManager:
    """Phase 2 synchronous job lifecycle backed by a JobRepository."""

    def __init__(self, repository) -> None:
        self.repository = repository

    def save(self, job: Job) -> None:
        self.repository.save(job)

    def get(self, job_id: UUID) -> Job | None:
        return self.repository.get(job_id)

    def transition(self, job_id: UUID, status: JobStatus, progress: int | None = None, error_code: str = "") -> Job:
        job = self.repository.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if status not in TRANSITIONS[job.status]:
            raise InvalidJobTransition(f"{job.status} cannot transition to {status}")
        now = datetime.now(timezone.utc)
        if status is JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            job.completed_at = now
        job.status = status
        job.progress = max(0, min(100, progress if progress is not None else job.progress))
        job.error_code = error_code[:80]
        self.repository.save(job)
        return job
