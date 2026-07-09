from __future__ import annotations

from collections import defaultdict
from types import MappingProxyType

from app.errors import ProcessingError
from app.models import (
    ArchiveEntry,
    ArchiveInventory,
    CarrierMappingRow,
    DispatchAssignment,
    DispatchPlan,
    Severity,
    ValidationIssue,
)


def _issue(
    rule: str,
    message: str,
    *,
    filename: str | None = None,
    expected: object | None = None,
    actual: object | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        severity=Severity.STRONG,
        rule=rule,
        message=message,
        repair="请修正 ZIP 或 Excel 文件后重新上传。",
        filename=filename,
        expected=expected,
        actual=actual,
    )


def _group_entries(
    inventory: ArchiveInventory,
) -> dict[str, dict[str, ArchiveEntry]]:
    grouped: dict[str, dict[str, ArchiveEntry]] = defaultdict(dict)
    for entry in inventory.entries:
        grouped[entry.stem.casefold()][entry.suffix] = entry
    return grouped


def build_dispatch_plan(
    inventory: ArchiveInventory,
    mappings: tuple[CarrierMappingRow, ...],
) -> DispatchPlan:
    grouped = _group_entries(inventory)
    issues: list[ValidationIssue] = []
    row_numbers_by_shipment: dict[str, list[int]] = defaultdict(list)
    shipment_display_by_key: dict[str, str] = {}
    shipment_to_carrier: dict[str, str] = {}
    carrier_to_shipments: dict[str, set[str]] = defaultdict(set)

    for row in mappings:
        shipment_key = row.shipment_id.casefold()
        row_numbers_by_shipment[shipment_key].append(row.row_number)
        shipment_display_by_key.setdefault(shipment_key, row.shipment_id)
        if shipment_key in shipment_to_carrier:
            if shipment_to_carrier[shipment_key] != row.carrier_number:
                issues.append(
                    _issue(
                        "multiple_carrier_assignment",
                        "a WFS shipment would require more than one carrier assignment",
                        actual={
                            "shipment_id": row.shipment_id,
                            "carrier_number": row.carrier_number,
                        },
                    )
                )
            continue
        shipment_to_carrier[shipment_key] = row.carrier_number
        carrier_to_shipments[row.carrier_number.casefold()].add(shipment_key)

    inventory_shipments = {
        stem: files
        for stem, files in grouped.items()
        if ".pdf" in files and ".txt" in files
    }
    inventory_carriers = {
        stem: files for stem, files in grouped.items() if ".pdf" in files and ".txt" not in files
    }

    for shipment_key in shipment_to_carrier:
        files = grouped.get(shipment_key)
        if files is None:
            issues.append(
                _issue(
                    "wfs_missing_from_zip",
                    "a WFS shipment listed in Excel cannot be found in the ZIP",
                    actual=shipment_display_by_key[shipment_key],
                )
            )
            continue

        if ".pdf" not in files or ".txt" not in files:
            issues.append(
                _issue(
                    "wfs_pdf_txt_pair_required",
                    "a WFS shipment must have both PDF and TXT files",
                    actual={
                        "shipment_id": shipment_display_by_key[shipment_key],
                        "has_pdf": ".pdf" in files,
                        "has_txt": ".txt" in files,
                    },
                )
            )
            continue

        carrier_number = shipment_to_carrier[shipment_key]
        carrier_files = inventory_carriers.get(carrier_number.casefold())
        if carrier_files is None:
            issues.append(
                _issue(
                    "carrier_missing_from_zip",
                    "a carrier number listed in Excel cannot be found in the uploaded files",
                    actual=carrier_number,
                )
            )

    for shipment_id, files in inventory_shipments.items():
        if shipment_id not in shipment_to_carrier:
            issues.append(
                _issue(
                    "unmapped_wfs_shipment",
                    "a WFS shipment present in the ZIP is not referenced by Excel",
                    actual=files[".pdf"].stem,
                )
            )

    for carrier_number, files in inventory_carriers.items():
        if carrier_number not in carrier_to_shipments:
            issues.append(
                _issue(
                    "unassigned_carrier_label",
                    "a carrier label PDF remains unassigned after dispatch",
                    actual=carrier_number,
                )
            )
        elif ".txt" in files:
            issues.append(
                _issue(
                    "carrier_must_be_pdf_only",
                    "a carrier label PDF must not also have a TXT file",
                    actual=carrier_number,
                )
            )

    if issues:
        raise ProcessingError(tuple(issues))

    assignments: dict[str, DispatchAssignment] = {}
    for shipment_key, carrier_number in shipment_to_carrier.items():
        shipment_files = grouped[shipment_key]
        carrier_files = inventory_carriers[carrier_number.casefold()]
        source_rows = tuple(row_numbers_by_shipment[shipment_key])
        shipment_id = shipment_display_by_key[shipment_key]
        assignments[shipment_id] = DispatchAssignment(
            shipment_id=shipment_id,
            carrier_number=carrier_number,
            shipment_pdf_path=shipment_files[".pdf"].path,
            shipment_txt_path=shipment_files[".txt"].path,
            carrier_pdf_path=carrier_files[".pdf"].path,
            source_rows=source_rows,
        )

    return DispatchPlan(assignments=MappingProxyType(assignments), issues=())
