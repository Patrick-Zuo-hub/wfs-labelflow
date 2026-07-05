from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.models import JobPreview, JobState
from app.services.storage import JobPaths, JobStorage


@dataclass
class JobRecord:
    state: JobState
    preview: JobPreview
    paths: JobPaths
    archive: Path | None = None
    completed_at: datetime | None = None


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def add(self, job_id: str, record: JobRecord) -> None:
        if job_id in self._jobs:
            raise KeyError(job_id)
        self._jobs[job_id] = record

    def get(self, job_id: str) -> JobRecord:
        return self._jobs[job_id]

    def remove(self, job_id: str) -> JobRecord | None:
        return self._jobs.pop(job_id, None)

    def expire(
        self,
        storage: JobStorage,
        retention: timedelta,
        now: datetime,
    ) -> tuple[str, ...]:
        completed = {
            job_id: record.completed_at
            for job_id, record in self._jobs.items()
            if record.completed_at is not None
        }
        expired = storage.cleanup_expired(completed, retention, now)
        for job_id in expired:
            record = self._jobs.pop(job_id)
            record.state = JobState.EXPIRED
        return expired
