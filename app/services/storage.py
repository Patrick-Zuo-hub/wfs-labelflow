from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

JOB_ID = re.compile(r"^\d{8}_\d{6}_[a-f0-9]{4,16}$")


@dataclass(frozen=True)
class JobPaths:
    root: Path
    uploads: Path
    intermediate: Path
    output: Path


class JobStorage:
    def __init__(self, runtime_root: Path):
        self.runtime_root = runtime_root.resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)

    def _root_for(self, job_id: str) -> Path:
        if not JOB_ID.fullmatch(job_id):
            raise ValueError("invalid job_id")
        root = (self.runtime_root / job_id).resolve()
        if root.parent != self.runtime_root:
            raise ValueError("job path escapes runtime root")
        return root

    def create(self, job_id: str) -> JobPaths:
        paths = self.paths(job_id)
        for path in (paths.uploads, paths.intermediate, paths.output):
            path.mkdir(parents=True, exist_ok=False)
        return paths

    def paths(self, job_id: str) -> JobPaths:
        root = self._root_for(job_id)
        return JobPaths(
            root=root,
            uploads=root / "uploads",
            intermediate=root / "intermediate",
            output=root / "output",
        )

    def cleanup_inputs(self, job_id: str, archive: Path) -> None:
        paths = self.paths(job_id)
        resolved_archive = archive.resolve()
        if resolved_archive.parent != paths.output.resolve():
            raise ValueError("archive is outside job output")
        if not resolved_archive.is_file():
            raise FileNotFoundError(resolved_archive)

        shutil.rmtree(paths.uploads)
        shutil.rmtree(paths.intermediate)
        for child in paths.output.iterdir():
            if child.resolve() == resolved_archive:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

    def cleanup(self, job_id: str) -> None:
        root = self._root_for(job_id)
        if root.exists():
            shutil.rmtree(root)

    def cleanup_expired(
        self,
        completed_at: dict[str, datetime],
        retention: timedelta,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        current = now or datetime.now(UTC)
        timestamps = (current, *completed_at.values())
        if any(timestamp.utcoffset() is None for timestamp in timestamps):
            raise ValueError("cleanup timestamps must be timezone-aware")

        removed: list[str] = []
        for job_id, timestamp in completed_at.items():
            if current - timestamp > retention:
                self.cleanup(job_id)
                removed.append(job_id)
        return tuple(removed)
