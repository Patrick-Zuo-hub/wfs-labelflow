from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.models import Severity
from app.services.classifier import classify_group


def touch(path: Path) -> Path:
    path.write_bytes(b"x")
    return path


def assert_strong_issue(
    error: ProcessingError,
    *,
    group_index: int,
    rule: str,
    actual: list[str],
) -> None:
    assert len(error.issues) == 1
    issue = error.issues[0]
    assert issue.severity is Severity.STRONG
    assert issue.rule == rule
    assert issue.group_index == group_index
    assert issue.as_dict()["actual"] == actual
    assert issue.repair.strip()


def test_sample_stems_classify_without_guessing(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "WFS Label-Sample.pdf"),
        touch(tmp_path / "WFS Label-Sample.txt"),
        touch(tmp_path / "Logistics Label-Sample.pdf"),
    ]

    result = classify_group(1, files)

    assert result.group_index == 1
    assert result.wfs_pdf_path.name == "WFS Label-Sample.pdf"
    assert result.wfs_zpl_path.name == "WFS Label-Sample.txt"
    assert result.logistics_pdf_path.name == "Logistics Label-Sample.pdf"


def test_real_sample_fixtures_classify() -> None:
    fixture_dir = Path("tests/fixtures/sample")
    files = sorted(fixture_dir.iterdir())

    result = classify_group(7, files)

    assert result.group_index == 7
    assert result.wfs_pdf_path.name == "WFS Label-Sample.pdf"
    assert result.wfs_zpl_path.name == "WFS Label-Sample.txt"
    assert result.logistics_pdf_path.name == "Logistics Label-Sample.pdf"


def test_non_wfs_source_is_rejected(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "source.txt"),
        touch(tmp_path / "second.pdf"),
        touch(tmp_path / "first.pdf"),
    ]

    with pytest.raises(ProcessingError) as caught:
        classify_group(3, files)

    assert_strong_issue(
        caught.value,
        group_index=3,
        rule="wfs_source_prefix_required",
        actual=["source.txt"],
    )


def test_wfs_prefix_is_required_for_the_pdf_role(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "WFS-source.zpl"),
        touch(tmp_path / "WFS-carrier.pdf"),
        touch(tmp_path / "plain.pdf"),
    ]

    result = classify_group(9, files)

    assert result.wfs_pdf_path.name == "WFS-carrier.pdf"
    assert result.logistics_pdf_path.name == "plain.pdf"


def test_multiple_wfs_pdfs_are_rejected(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "WFS-source.txt"),
        touch(tmp_path / "WFS-main.pdf"),
        touch(tmp_path / "wfs-copy.pdf"),
    ]

    with pytest.raises(ProcessingError) as caught:
        classify_group(10, files)

    assert_strong_issue(
        caught.value,
        group_index=10,
        rule="wfs_pdf_prefix_required",
        actual=["WFS-main.pdf", "wfs-copy.pdf"],
    )


def test_unsupported_extensions_are_rejected_case_insensitively(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "notes.CSV"),
        touch(tmp_path / "archive.zip"),
    ]

    with pytest.raises(ProcessingError) as caught:
        classify_group(2, files)

    assert_strong_issue(
        caught.value,
        group_index=2,
        rule="unsupported_extension",
        actual=["archive.zip", "notes.CSV"],
    )


@pytest.mark.parametrize(
    "names",
    [
        ["WFS.txt", "WFS.pdf"],
        ["WFS.txt", "WFS.zpl", "WFS.pdf", "logistics.pdf"],
        ["WFS.txt", "WFS.pdf", "one.pdf", "two.pdf"],
    ],
)
def test_missing_or_repeated_required_roles_are_rejected(
    tmp_path: Path, names: list[str]
) -> None:
    files = [touch(tmp_path / name) for name in names]

    with pytest.raises(ProcessingError) as caught:
        classify_group(4, files)

    assert_strong_issue(
        caught.value,
        group_index=4,
        rule="required_file_roles",
        actual=sorted(names),
    )


def test_supported_extensions_are_case_insensitive(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "WFS-batch.PDF"),
        touch(tmp_path / "WFS-batch.ZpL"),
        touch(tmp_path / "logistics.PdF"),
    ]

    result = classify_group(5, files)

    assert result.wfs_pdf_path.name == "WFS-batch.PDF"
    assert result.wfs_zpl_path.name == "WFS-batch.ZpL"
    assert result.logistics_pdf_path.name == "logistics.PdF"
