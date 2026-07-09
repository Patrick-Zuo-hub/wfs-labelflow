import zipfile
from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.services.archive_ingest import parse_zip_archive


def test_parse_zip_archive_extracts_members(tmp_path: Path) -> None:
    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("9233758WFA.txt", b"txt")
        zipped.writestr("CD2606260718.pdf", b"carrier")

    inventory = parse_zip_archive(archive)

    assert inventory.archive_path == archive
    assert inventory.extracted_root.is_dir()
    assert {entry.name for entry in inventory.entries} == {
        "9233758WFA.pdf",
        "9233758WFA.txt",
        "CD2606260718.pdf",
    }
    assert all(entry.path.is_file() for entry in inventory.entries)


def test_parse_zip_archive_rejects_duplicate_basenames(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("123.pdf", b"one")
        zipped.writestr("nested/123.pdf", b"two")

    with pytest.raises(ProcessingError, match="duplicate"):
        parse_zip_archive(archive)
