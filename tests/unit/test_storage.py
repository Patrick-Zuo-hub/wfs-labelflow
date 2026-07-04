from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import Settings
from app.services.storage import JobStorage


def test_settings_have_safe_defaults_and_are_frozen() -> None:
    settings = Settings()

    assert settings.runtime_root == Path("data/jobs")
    assert settings.zip_retention == timedelta(minutes=30)
    with pytest.raises(FrozenInstanceError):
        settings.runtime_root = Path("elsewhere")  # type: ignore[misc]


def test_job_paths_are_isolated_under_runtime_root(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")

    assert paths.root == tmp_path.resolve() / "20260704_080000_ab12"
    assert paths.uploads.is_dir()
    assert paths.intermediate.is_dir()
    assert paths.output.is_dir()


def test_cleanup_rejects_path_escape(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)

    with pytest.raises(ValueError, match="invalid job_id"):
        storage.cleanup("../outside")


def test_success_cleanup_keeps_only_zip(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")
    (paths.uploads / "source.pdf").write_bytes(b"source")
    (paths.intermediate / "part.pdf").write_bytes(b"part")
    archive = paths.output / "output.zip"
    archive.write_bytes(b"zip")
    (paths.output / "obsolete.pdf").write_bytes(b"obsolete")

    storage.cleanup_inputs("20260704_080000_ab12", archive)

    assert not paths.uploads.exists()
    assert not paths.intermediate.exists()
    assert tuple(paths.output.iterdir()) == (archive,)
    assert archive.read_bytes() == b"zip"


def test_cleanup_inputs_removes_nested_output_directories(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")
    archive = paths.output / "output.zip"
    archive.write_bytes(b"zip")
    nested = paths.output / "obsolete" / "nested"
    nested.mkdir(parents=True)
    (nested / "part.pdf").write_bytes(b"part")

    storage.cleanup_inputs("20260704_080000_ab12", archive)

    assert tuple(paths.output.iterdir()) == (archive,)


def test_cleanup_inputs_rejects_archive_outside_job_output(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "jobs")
    storage.create("20260704_080000_ab12")
    archive = tmp_path / "outside.zip"
    archive.write_bytes(b"zip")

    with pytest.raises(ValueError, match="archive is outside job output"):
        storage.cleanup_inputs("20260704_080000_ab12", archive)


def test_cleanup_inputs_rejects_missing_archive(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")
    archive = paths.output / "missing.zip"

    with pytest.raises(FileNotFoundError):
        storage.cleanup_inputs("20260704_080000_ab12", archive)

    assert paths.uploads.is_dir()
    assert paths.intermediate.is_dir()


def test_expired_results_remove_only_old_jobs(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    old_paths = storage.create("20260704_080000_ab12")
    new_paths = storage.create("20260704_080100_cd34")
    now = datetime(2026, 7, 4, 8, 40, tzinfo=UTC)

    removed = storage.cleanup_expired(
        {
            "20260704_080000_ab12": now - timedelta(minutes=31),
            "20260704_080100_cd34": now - timedelta(minutes=29),
        },
        timedelta(minutes=30),
        now=now,
    )

    assert removed == ("20260704_080000_ab12",)
    assert not old_paths.root.exists()
    assert new_paths.root.is_dir()


@pytest.mark.parametrize(
    "completed_at, now",
    [
        (
            datetime(2026, 7, 4, 8, 0),
            datetime(2026, 7, 4, 9, 0, tzinfo=UTC),
        ),
        (
            datetime(2026, 7, 4, 8, 0, tzinfo=UTC),
            datetime(2026, 7, 4, 9, 0),
        ),
    ],
)
def test_cleanup_expired_rejects_naive_datetimes(
    tmp_path: Path,
    completed_at: datetime,
    now: datetime,
) -> None:
    storage = JobStorage(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        storage.cleanup_expired(
            {"20260704_080000_ab12": completed_at},
            timedelta(minutes=30),
            now=now,
        )


@pytest.mark.parametrize(
    "job_id",
    [
        "20260704_080000_abcd",
        "20260704_080000_0123456789abcdef",
    ],
)
def test_job_id_accepts_suffix_length_boundaries(tmp_path: Path, job_id: str) -> None:
    storage = JobStorage(tmp_path)

    assert storage.paths(job_id).root == tmp_path.resolve() / job_id


@pytest.mark.parametrize(
    "job_id",
    [
        "20260704_080000_abc",
        "20260704_080000_0123456789abcdef0",
        "20260704_080000_ABCD",
        "2026074_080000_abcd",
        "20260704_80000_abcd",
        "20260704-080000-abcd",
    ],
)
def test_job_id_rejects_values_outside_format_boundaries(tmp_path: Path, job_id: str) -> None:
    storage = JobStorage(tmp_path)

    with pytest.raises(ValueError, match="invalid job_id"):
        storage.paths(job_id)
