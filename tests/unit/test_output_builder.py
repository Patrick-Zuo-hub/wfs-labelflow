import csv
import zipfile
from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.models import (
    BoxPair,
    GroupPreview,
    LabelGroupFiles,
    LabelType,
    Severity,
    ValidationIssue,
    WfsLabel,
)
from app.services.output_builder import (
    allocate_output_names,
    build_processing_log,
    build_summary,
    build_verified_zip,
)


def pair(sku: str) -> BoxPair:
    label = WfsLabel(1, 1, 1, LabelType.BOX, "^XA^XZ", sku=sku)
    return BoxPair(1, 1, sku, 1, 1, label)


def test_sanitized_name_collisions_get_stable_suffixes() -> None:
    names = allocate_output_names(("SKU A/B", "SKU A:B", "SKU-C"))

    assert names == {
        "SKU A/B": "SKU A-B.pdf",
        "SKU A:B": "SKU A-B_2.pdf",
        "SKU-C": "SKU-C.pdf",
    }


def test_summary_keeps_original_sku_and_output_name(tmp_path: Path) -> None:
    output = tmp_path / "summary.csv"
    current_pair = pair("SKU A/B")
    files = LabelGroupFiles(
        1,
        tmp_path / "wfs.pdf",
        tmp_path / "wfs.txt",
        tmp_path / "logistics.pdf",
    )
    warning = ValidationIssue(
        Severity.WEAK,
        "multiple_shipment_ids",
        "multiple shipment IDs",
        "confirm group",
        group_index=1,
    )
    group = GroupPreview(files, (current_pair.wfs_label,), (current_pair,), (warning,))

    build_summary("job", (group,), {"SKU A/B": "SKU A-B.pdf"}, output)

    with output.open(newline="", encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle))

    assert row["job_id"] == "job"
    assert row["sku"] == "SKU A/B"
    assert row["output_pdf"] == "SKU A-B.pdf"
    assert row["wfs_pdf_file"] == "wfs.pdf"
    assert row["wfs_pdf_page"] == "1"
    assert row["logistics_pdf_file"] == "logistics.pdf"
    assert row["logistics_pdf_page"] == "1"
    assert row["warnings"] == "multiple shipment IDs"


def test_processing_log_uses_plain_text_lines(tmp_path: Path) -> None:
    output = tmp_path / "processing.log"

    build_processing_log(("line 1", "line 2"), output)

    assert output.read_text(encoding="utf-8") == "line 1\nline 2\n"


def test_zip_is_reopened_and_contains_required_members(tmp_path: Path) -> None:
    pdf = tmp_path / "SKU-A.pdf"
    summary = tmp_path / "summary.csv"
    log = tmp_path / "processing_log.txt"
    for path in (pdf, summary, log):
        path.write_bytes(b"content")
    archive = tmp_path / "output.zip"

    build_verified_zip((pdf,), summary, log, archive)

    with zipfile.ZipFile(archive) as zipped:
        assert sorted(zipped.namelist()) == ["SKU-A.pdf", "processing_log.txt", "summary.csv"]
        assert zipped.testzip() is None


def test_zip_readback_failures_raise_processing_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "SKU-A.pdf"
    summary = tmp_path / "summary.csv"
    log = tmp_path / "processing_log.txt"
    for path in (pdf, summary, log):
        path.write_bytes(b"content")
    archive = tmp_path / "output.zip"

    original_zipfile = zipfile.ZipFile

    class BrokenZipFile(original_zipfile):
        def testzip(self) -> str | None:  # type: ignore[override]
            if self.mode == "r":
                return "summary.csv"
            return super().testzip()

    monkeypatch.setattr(zipfile, "ZipFile", BrokenZipFile)

    with pytest.raises(ProcessingError) as excinfo:
        build_verified_zip((pdf,), summary, log, archive)

    assert excinfo.value.issues[0].rule == "zip_readback"
