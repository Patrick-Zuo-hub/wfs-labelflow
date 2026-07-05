from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.errors import ProcessingError
from app.models import LabelType, WfsLabel
from app.services.pairing import build_pairs
from app.services.validation import collect_warnings, validate_group_counts, validate_labels


def pdf_with_pages(path: Path, count: int) -> Path:
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=100, height=100)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def label(index: int, label_type: LabelType, sku: str | None = None) -> WfsLabel:
    return WfsLabel(1, index, index, label_type, "^XA^XZ", sku=sku)


def test_pallet_in_middle_does_not_consume_logistics_page() -> None:
    labels = (
        label(1, LabelType.BOX, "A"),
        label(2, LabelType.PALLET),
        label(3, LabelType.BOX, "B"),
    )

    pairs = build_pairs(1, labels, logistics_page_count=2)

    assert [(pair.wfs_pdf_page, pair.logistics_pdf_page) for pair in pairs] == [(1, 1), (3, 2)]


def test_unknown_label_stops_group() -> None:
    with pytest.raises(ProcessingError) as caught:
        validate_labels(1, (label(1, LabelType.UNKNOWN),))

    assert caught.value.issues[0].rule == "unknown_label_type"


def test_missing_sku_stops_group() -> None:
    with pytest.raises(ProcessingError) as caught:
        validate_labels(1, (label(1, LabelType.BOX),))

    assert caught.value.issues[0].rule == "box_sku_required"


def test_multiple_pallets_stop_group() -> None:
    labels = (
        label(1, LabelType.BOX, "A"),
        label(2, LabelType.PALLET),
        label(3, LabelType.PALLET),
    )

    with pytest.raises(ProcessingError) as caught:
        validate_labels(1, labels)

    assert caught.value.issues[0].rule == "single_pallet_maximum"


def test_pdf_and_effective_box_counts_are_checked(tmp_path: Path) -> None:
    wfs = pdf_with_pages(tmp_path / "wfs.pdf", 3)
    logistics = pdf_with_pages(tmp_path / "logistics.pdf", 1)
    labels = (
        label(1, LabelType.BOX, "A"),
        label(2, LabelType.PALLET),
        label(3, LabelType.BOX, "B"),
    )

    with pytest.raises(ProcessingError) as caught:
        validate_group_counts(1, wfs, logistics, labels)

    assert caught.value.issues[0].rule == "effective_box_count_matches_logistics_pages"
    assert caught.value.issues[0].expected == 2
    assert caught.value.issues[0].actual == 1


def test_multiple_shipment_ids_emit_group_warning() -> None:
    labels = (
        WfsLabel(1, 1, 1, LabelType.BOX, "^XA^XZ", sku="A1", shipment_id="SHIP-1"),
        WfsLabel(1, 2, 2, LabelType.BOX, "^XA^XZ", sku="A2", shipment_id="SHIP-2"),
    )

    warnings = collect_warnings(1, labels, logistics_page_count=2)

    assert warnings[0].severity.value == "weak"
    assert warnings[0].rule == "multiple_shipment_ids"
    assert warnings[0].actual == ("SHIP-1", "SHIP-2")


def test_wfs_page_count_must_match_zpl_segment_count(tmp_path: Path) -> None:
    wfs = pdf_with_pages(tmp_path / "wfs.pdf", 2)
    logistics = pdf_with_pages(tmp_path / "logistics.pdf", 2)
    labels = (
        label(1, LabelType.BOX, "A"),
        label(2, LabelType.PALLET),
        label(3, LabelType.BOX, "B"),
    )

    with pytest.raises(ProcessingError) as caught:
        validate_group_counts(1, wfs, logistics, labels)

    assert caught.value.issues[0].rule == "wfs_pages_match_zpl_segments"
    assert caught.value.issues[0].expected == 3
    assert caught.value.issues[0].actual == 2
