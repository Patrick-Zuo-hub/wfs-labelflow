from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.models import LabelType, Severity
from app.services.zpl_parser import parse_wfs_zpl


def assert_strong_issue(
    error: ProcessingError,
    *,
    group_index: int,
    rule: str,
) -> None:
    assert len(error.issues) == 1
    issue = error.issues[0]
    assert issue.severity is Severity.STRONG
    assert issue.group_index == group_index
    assert issue.rule == rule
    assert issue.repair.strip()


def test_parse_wfs_zpl_extracts_sample_metadata() -> None:
    sample_text = Path("tests/fixtures/sample/WFS Label-Sample.txt").read_text()

    labels = parse_wfs_zpl(sample_text, group_index=1)

    assert len(labels) == 4
    assert [label.label_type for label in labels] == [
        LabelType.BOX,
        LabelType.BOX,
        LabelType.BOX,
        LabelType.PALLET,
    ]
    assert [label.sku for label in labels[:3]] == [
        "F-FPG-C9-PN-IVN",
        "P-kcup-white-2",
        "P-kcup-white-2",
    ]
    assert [label.quantity for label in labels[:3]] == [37, 28, 28]
    assert labels[0].box_id == "208500550239713066"
    assert labels[0].shipment_id == "9233758WFA"
    assert labels[0].gtin == "00761426715151"
    assert labels[0].box_text == "BOX 1 OF 3"
    assert labels[3].sku is None
    assert labels[3].label_type is LabelType.PALLET


def test_parse_wfs_zpl_requires_complete_segment_boundaries() -> None:
    sample_text = Path("tests/fixtures/sample/WFS Label-Sample.txt").read_text()
    broken_text = sample_text.rsplit("^XZ", 1)[0]

    with pytest.raises(ProcessingError) as caught:
        parse_wfs_zpl(broken_text, group_index=2)

    assert_strong_issue(caught.value, group_index=2, rule="zpl_segment_boundary")
    assert caught.value.issues[0].actual == {"segment_index": 4, "reason": "missing_xz"}
