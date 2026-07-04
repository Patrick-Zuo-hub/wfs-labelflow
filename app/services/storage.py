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
        root = self.runtime_root / job_id
        if root.parent != self.runtime_root:
            raise ValueError("job path escapes runtime root")
        self._validate_job_root(root)
        return root

    def _validate_job_root(self, root: Path) -> None:
        if root.is_symlink():
            raise ValueError("invalid job root: symlink")
        if root.exists():
            resolved = root.resolve()
            if (
                not root.is_dir()
                or resolved.parent != self.runtime_root
                or resolved != root.absolute()
            ):
                raise ValueError("invalid job root")

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
        physical_root = paths.root.resolve()
        for name, path in (
            ("uploads", paths.uploads),
            ("intermediate", paths.intermediate),
            ("output", paths.output),
        ):
            if path.is_symlink():
                raise ValueError(f"{name} must be a physical job directory")
            if not path.exists():
                if name == "output":
                    raise ValueError("output must be a physical job directory")
                continue
            expected = physical_root / name
            resolved = path.resolve()
            if (
                resolved != expected
                or resolved.parent != physical_root
                or not path.is_dir()
            ):
                raise ValueError(f"{name} must be a physical job directory")

        if archive.parent != paths.output:
            raise ValueError("archive is outside job output")
        if archive.is_symlink():
            raise ValueError("archive must be a regular file, not a symlink")
        resolved_archive = archive.resolve()
        if (
            resolved_archive.parent != paths.output
            or resolved_archive != paths.output / archive.name
        ):
            raise ValueError("archive is outside job output")
        if not resolved_archive.is_file():
            raise FileNotFoundError(resolved_archive)

        if paths.uploads.exists():
            shutil.rmtree(paths.uploads)
        if paths.intermediate.exists():
            shutil.rmtree(paths.intermediate)
        for child in paths.output.iterdir():
            if child == archive:
                continue
            if child.is_symlink():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def cleanup(self, job_id: str) -> None:
        root = self._root_for(job_id)
        if root.exists():
            self._validate_job_root(root)
            shutil.rmtree(root)

    def cleanup_expired(
        self,
        completed_at: dict[str, datetime],
        retention: timedelta,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        if retention < timedelta(0):
            raise ValueError("retention must not be negative")
        current = now or datetime.now(UTC)
        timestamps = (current, *completed_at.values())
        if any(timestamp.utcoffset() is None for timestamp in timestamps):
            raise ValueError("cleanup timestamps must be timezone-aware")

        current_utc = current.astimezone(UTC)
        removed: list[str] = []
        for job_id, timestamp in completed_at.items():
            if current_utc - timestamp.astimezone(UTC) > retention:
                self.cleanup(job_id)
                removed.append(job_id)
        return tuple(removed)
