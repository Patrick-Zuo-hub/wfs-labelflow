from pathlib import Path

import pytest
from openpyxl import Workbook

from app.errors import ProcessingError
from app.services.excel_mapping import read_excel_mapping


def _write_workbook(path: Path, rows: list[list[str]]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    for row in rows:
        sheet.append(row)
    workbook.create_sheet("Ignored")
    workbook["Ignored"].append(["货代单号", "WFS Shipment ID"])
    workbook["Ignored"].append(["SHOULD_NOT", "BE_READ"])
    workbook.save(path)
    return path


def test_read_excel_mapping_reads_first_sheet_and_row_numbers(tmp_path: Path) -> None:
    workbook_path = _write_workbook(
        tmp_path / "mapping.xlsx",
        [
            ["货代单号", "WFS Shipment ID"],
            ["CD2606260718", "9233758WFA"],
            ["CD2606260718", "9233758WFB"],
        ],
    )

    rows = read_excel_mapping(workbook_path)

    assert rows == (
        type(rows[0])(row_number=2, carrier_number="CD2606260718", shipment_id="9233758WFA"),
        type(rows[0])(row_number=3, carrier_number="CD2606260718", shipment_id="9233758WFB"),
    )


def test_read_excel_mapping_requires_exact_headers(tmp_path: Path) -> None:
    workbook_path = _write_workbook(
        tmp_path / "broken.xlsx",
        [
            ["Carrier", "Shipment"],
            ["CD2606260718", "9233758WFA"],
        ],
    )

    with pytest.raises(ProcessingError, match="header"):
        read_excel_mapping(workbook_path)
