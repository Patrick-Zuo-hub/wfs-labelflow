from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.models import JobPreview, JobState
from app.services.storage import JobPaths


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
