import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.models import (
    BoxPair,
    GroupPreview,
    JobPreview,
    JobState,
    LabelGroupFiles,
    LabelType,
    ProcessingOptions,
    Severity,
    ValidationIssue,
    WfsLabel,
)


def make_label(*, group_index: int = 1, sku: str = "SKU-A") -> WfsLabel:
    return WfsLabel(
        group_index=group_index,
        zpl_index=1,
        pdf_page=1,
        label_type=LabelType.BOX,
        raw_zpl="^XA^FDSINGLE SKU:^FS^FDSKU-A^FS^XZ",
        sku=sku,
    )


def make_pair(*, group_index: int = 1, sku: str = "SKU-A") -> BoxPair:
    return BoxPair(
        group_index=group_index,
        box_index=1,
        sku=sku,
        wfs_pdf_page=1,
        logistics_pdf_page=1,
        wfs_label=make_label(group_index=group_index, sku=sku),
    )


def make_files(group_index: int) -> LabelGroupFiles:
    return LabelGroupFiles(
        group_index=group_index,
        wfs_pdf_path=Path(f"group-{group_index}/wfs.pdf"),
        wfs_zpl_path=Path(f"group-{group_index}/wfs.zpl"),
        logistics_pdf_path=Path(f"group-{group_index}/logistics.pdf"),
    )


@pytest.mark.parametrize("logistics_repeat", [True, False, 1.0, 2.0, 0, 3])
def test_processing_options_reject_non_exact_repeat_values(
    logistics_repeat: object,
) -> None:
    with pytest.raises(ValueError, match="logistics_repeat"):
        ProcessingOptions(logistics_repeat=logistics_repeat)  # type: ignore[arg-type]


def test_processing_options_have_fixed_wfs_rules() -> None:
    options = ProcessingOptions(logistics_repeat=2)

    assert options.wfs_repeat == 2
    assert options.ignore_pallet is True
    assert options.merge_same_sku is True
    assert options.include_summary is True
    with pytest.raises(TypeError):
        ProcessingOptions(wfs_repeat=1)  # type: ignore[call-arg]


def test_box_pair_is_immutable() -> None:
    pair = make_pair()

    with pytest.raises(FrozenInstanceError):
        pair.sku = "CHANGED"  # type: ignore[misc]


def test_validation_issue_serializes_exact_context() -> None:
    issue = ValidationIssue(
        severity=Severity.STRONG,
        rule="effective_box_count_matches_logistics_pages",
        message="有效箱标与货代页数不一致",
        repair="请替换货代 PDF。",
        group_index=2,
        filename="Logistics_02.pdf",
        page=4,
        expected={"boxes": 3},
        actual={"pages": 2},
    )

    assert issue.as_dict() == {
        "severity": "strong",
        "rule": "effective_box_count_matches_logistics_pages",
        "message": "有效箱标与货代页数不一致",
        "repair": "请替换货代 PDF。",
        "group_index": 2,
        "filename": "Logistics_02.pdf",
        "page": 4,
        "expected": {"boxes": 3},
        "actual": {"pages": 2},
    }


def test_validation_issue_context_is_recursively_immutable_and_json_friendly() -> None:
    source = {
        "pages": [1, 2],
        "alternates": (3, 4),
        "flags": {5, 6},
    }
    issue = ValidationIssue(
        severity=Severity.AUDIT,
        rule="context_snapshot",
        message="Context must remain stable",
        repair="Replace the input.",
        expected=source,
        actual=source,
    )

    source["pages"].append(9)
    source["alternates"] += (9,)
    source["flags"].add(9)

    assert issue.expected["pages"] == (1, 2)
    assert issue.expected["alternates"] == (3, 4)
    assert issue.expected["flags"] == frozenset({5, 6})
    with pytest.raises(TypeError):
        issue.expected["pages"] = (9,)  # type: ignore[index]
    with pytest.raises(AttributeError):
        issue.expected["pages"].append(9)  # type: ignore[union-attr]

    serialized = issue.as_dict()
    assert serialized["expected"]["pages"] == [1, 2]
    assert serialized["expected"]["alternates"] == [3, 4]
    assert set(serialized["expected"]["flags"]) == {5, 6}
    json.dumps(serialized)


def test_job_state_awaiting_confirmation_value() -> None:
    assert JobState.AWAITING_CONFIRMATION.value == "awaiting_confirmation"


def test_job_preview_flattens_pairs_in_group_order() -> None:
    first_pair = make_pair(group_index=1, sku="SKU-A")
    second_pair = make_pair(group_index=2, sku="SKU-B")
    preview = JobPreview(
        job_id="job-1",
        groups=(
            GroupPreview(
                files=make_files(1),
                labels=(first_pair.wfs_label,),
                pairs=(first_pair,),
            ),
            GroupPreview(
                files=make_files(2),
                labels=(second_pair.wfs_label,),
                pairs=(second_pair,),
            ),
        ),
        options=ProcessingOptions(),
    )

    assert preview.pairs == (first_pair, second_pair)


def test_processing_error_requires_issues_and_joins_messages() -> None:
    first = ValidationIssue(Severity.STRONG, "rule-1", "first", "repair")
    second = ValidationIssue(Severity.WEAK, "rule-2", "second", "repair")

    error = ProcessingError((first, second))

    assert error.issues == (first, second)
    assert str(error) == "first; second"
    with pytest.raises(ValueError, match="at least one issue"):
        ProcessingError(())
