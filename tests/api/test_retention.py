from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import JobPreview, JobState, ProcessingOptions
from app.services.registry import JobRecord, JobRegistry
from app.services.storage import JobStorage


def test_registry_expiration_removes_only_expired_completed_job(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    registry = JobRegistry()
    old_id = "20260704_080000_ab12"
    fresh_id = "20260704_083000_cd34"
    for job_id in (old_id, fresh_id):
        paths = storage.create(job_id)
        archive = paths.output / "output.zip"
        archive.write_bytes(b"zip")
        preview = JobPreview(job_id, (), ProcessingOptions())
        registry.add(job_id, JobRecord(JobState.READY_FOR_DOWNLOAD, preview, paths, archive))
    registry.get(old_id).completed_at = datetime.now(UTC) - timedelta(minutes=31)
    registry.get(fresh_id).completed_at = datetime.now(UTC)

    expired = registry.expire(storage, timedelta(minutes=30), datetime.now(UTC))

    assert expired == (old_id,)
    assert not storage.paths(old_id).root.exists()
    assert storage.paths(fresh_id).root.exists()
