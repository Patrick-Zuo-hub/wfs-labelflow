import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook
from pypdf import PdfReader

from app.errors import ProcessingError
from app.models import JobState, ProcessingOptions
from app.services.job_processor import JobProcessor, UploadedGroup
from app.services.registry import JobRegistry
from app.services.storage import JobStorage

SAMPLE = Path("tests/fixtures/sample")


def sample_group(index: int) -> UploadedGroup:
    return UploadedGroup(
        index,
        (
            SAMPLE / "WFS Label-Sample.pdf",
            SAMPLE / "WFS Label-Sample.txt",
            SAMPLE / "Logistics Label-Sample.pdf",
        ),
    )


def test_sample_validates_then_generates_atomic_zip(tmp_path: Path) -> None:
    registry = JobRegistry()
    processor = JobProcessor(JobStorage(tmp_path), registry)

    preview = processor.validate((sample_group(1),), ProcessingOptions(logistics_repeat=1))
    result = processor.generate(preview.job_id)

    assert registry.get(preview.job_id).state is JobState.READY_FOR_DOWNLOAD
    assert result.archive.is_file()
    assert not result.paths.uploads.exists()
    assert not result.paths.intermediate.exists()
    assert not list(result.paths.output.glob("*.pdf"))
    with zipfile.ZipFile(result.archive) as archive:
        assert set(result.sku_pdf_names) <= set(archive.namelist())
        assert archive.testzip() is None


def test_one_bad_group_prevents_all_output(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    for source in sample_group(1).files:
        (bad / source.name).write_bytes(source.read_bytes())
    (bad / "Logistics Label-Sample.pdf").write_bytes(b"not a pdf")
    registry = JobRegistry()
    processor = JobProcessor(JobStorage(tmp_path / "jobs"), registry)

    with pytest.raises(ProcessingError):
        processor.validate(
            (
                sample_group(1),
                UploadedGroup(2, tuple(bad.iterdir())),
            ),
            ProcessingOptions(),
        )

    assert not list((tmp_path / "jobs").glob("*/output/*.zip"))


def test_same_sku_across_nonadjacent_groups_is_appended_by_group(tmp_path: Path) -> None:
    processor = JobProcessor(JobStorage(tmp_path), JobRegistry())
    preview = processor.validate(
        (sample_group(1), sample_group(3)),
        ProcessingOptions(logistics_repeat=1),
    )

    result = processor.generate(preview.job_id)

    with zipfile.ZipFile(result.archive) as archive:
        repeated_sku = PdfReader(BytesIO(archive.read("P-kcup-white-2.pdf")))
    assert len(repeated_sku.pages) == 12


def test_generate_rejects_unknown_or_unconfirmed_job(tmp_path: Path) -> None:
    processor = JobProcessor(JobStorage(tmp_path), JobRegistry())

    with pytest.raises(KeyError):
        processor.generate("20260704_080000_ab12")


def test_dispatch_validation_failure_cleans_job_root(tmp_path: Path) -> None:
    processor = JobProcessor(JobStorage(tmp_path / "jobs"), JobRegistry())

    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("9233758WFA.txt", b"txt")
        zipped.writestr("CD2606260718.pdf", b"carrier")
        zipped.writestr("CD2606260719.pdf", b"carrier")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["货代单号", "WFS Shipment ID"])
    sheet.append(["CD2606260718", "9233758WFA"])
    mapping = tmp_path / "mapping.xlsx"
    workbook.save(mapping)

    with pytest.raises(ProcessingError):
        processor.validate_dispatch(archive, mapping)

    assert not list((tmp_path / "jobs").glob("*"))


def test_dispatch_validate_then_generate_atomic_zip(tmp_path: Path) -> None:
    processor = JobProcessor(JobStorage(tmp_path / "jobs"), JobRegistry())

    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("9233758WFA.txt", b"txt")
        zipped.writestr("CD2606260718.pdf", b"carrier")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["货代单号", "WFS Shipment ID"])
    sheet.append(["CD2606260718", "9233758WFA"])
    mapping = tmp_path / "mapping.xlsx"
    workbook.save(mapping)

    preview = processor.validate_dispatch(archive, mapping)
    result = processor.generate(preview.job_id)

    assert result.archive.is_file()
    assert not result.paths.uploads.exists()
    assert not result.paths.intermediate.exists()
    assert not list(result.paths.output.glob("*.pdf"))
    with zipfile.ZipFile(result.archive) as zipped:
        assert zipped.testzip() is None
