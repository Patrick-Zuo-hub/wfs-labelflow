import zipfile
from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.models import CarrierMappingRow
from app.services.archive_ingest import parse_zip_archive
from app.services.dispatch import build_dispatch_plan


def _write_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zipped:
        for name, content in members.items():
            zipped.writestr(name, content)
    return path


def _inventory(tmp_path: Path, members: dict[str, bytes]):
    return parse_zip_archive(_write_zip(tmp_path / "labels.zip", members))


def _mapping(*rows: tuple[str, str]) -> tuple[CarrierMappingRow, ...]:
    return tuple(
        CarrierMappingRow(
            row_number=index + 2,
            carrier_number=carrier,
            shipment_id=shipment,
        )
        for index, (carrier, shipment) in enumerate(rows)
    )


def test_one_carrier_number_can_cover_many_wfs_ids(tmp_path: Path) -> None:
    inventory = _inventory(
        tmp_path,
        {
            "9233758WFA.pdf": b"pdf-a",
            "9233758WFA.txt": b"txt-a",
            "9233758WFB.pdf": b"pdf-b",
            "9233758WFB.txt": b"txt-b",
            "CD2606260718.pdf": b"carrier",
        },
    )
    rows = _mapping(
        ("CD2606260718", "9233758WFA"),
        ("CD2606260718", "9233758WFB"),
    )

    plan = build_dispatch_plan(
        inventory,
        rows,
    )

    assert plan.issues == ()
    assert plan.assignments["9233758WFA"].carrier_number == "CD2606260718"
    assert plan.assignments["9233758WFB"].carrier_pdf_path == plan.assignments[
        "9233758WFA"
    ].carrier_pdf_path


def test_missing_wfs_txt_fails(tmp_path: Path) -> None:
    inventory = _inventory(
        tmp_path,
        {
            "9233758WFA.pdf": b"pdf-a",
            "CD2606260718.pdf": b"carrier",
        },
    )

    rows = _mapping(("CD2606260718", "9233758WFA"))

    with pytest.raises(ProcessingError):
        build_dispatch_plan(inventory, rows)


def test_missing_excel_row_for_zip_shipment_fails(tmp_path: Path) -> None:
    inventory = _inventory(
        tmp_path,
        {
            "9233758WFA.pdf": b"pdf-a",
            "9233758WFA.txt": b"txt-a",
            "9233758WFB.pdf": b"pdf-b",
            "9233758WFB.txt": b"txt-b",
            "CD2606260718.pdf": b"carrier",
        },
    )
    rows = _mapping(("CD2606260718", "9233758WFA"))

    with pytest.raises(ProcessingError):
        build_dispatch_plan(inventory, rows)


def test_missing_zip_shipment_fails(tmp_path: Path) -> None:
    inventory = _inventory(
        tmp_path,
        {
            "9233758WFA.pdf": b"pdf-a",
            "9233758WFA.txt": b"txt-a",
            "CD2606260718.pdf": b"carrier",
        },
    )
    rows = _mapping(
        ("CD2606260718", "9233758WFA"),
        ("CD2606260718", "9233758WFB"),
    )

    with pytest.raises(ProcessingError):
        build_dispatch_plan(inventory, rows)


def test_leftover_carrier_label_fails(tmp_path: Path) -> None:
    inventory = _inventory(
        tmp_path,
        {
            "9233758WFA.pdf": b"pdf-a",
            "9233758WFA.txt": b"txt-a",
            "CD2606260718.pdf": b"carrier-a",
            "CD2606260719.pdf": b"carrier-b",
        },
    )
    rows = _mapping(("CD2606260718", "9233758WFA"))

    with pytest.raises(ProcessingError):
        build_dispatch_plan(inventory, rows)


def test_happy_path_builds_assignments(tmp_path: Path) -> None:
    inventory = _inventory(
        tmp_path,
        {
            "9233758WFA.pdf": b"pdf-a",
            "9233758WFA.txt": b"txt-a",
            "9233758WFB.pdf": b"pdf-b",
            "9233758WFB.txt": b"txt-b",
            "CD2606260718.pdf": b"carrier",
        },
    )
    rows = _mapping(
        ("CD2606260718", "9233758WFA"),
        ("CD2606260718", "9233758WFB"),
    )

    plan = build_dispatch_plan(
        inventory,
        rows,
    )

    assert plan.issues == ()
    assert set(plan.assignments) == {"9233758WFA", "9233758WFB"}
