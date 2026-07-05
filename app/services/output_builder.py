from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path

from app.errors import ProcessingError
from app.models import GroupPreview, Severity, ValidationIssue

_UNSAFE = re.compile(r'[\/\\:*?"<>|\x00-\x1f]')


def _safe_stem(sku: str) -> str:
    stem = _UNSAFE.sub("-", sku).strip(" .-")
    return stem or "SKU"


def allocate_output_names(skus: tuple[str, ...]) -> dict[str, str]:
    allocated: dict[str, str] = {}
    counts: dict[str, int] = {}
    for sku in skus:
        stem = _safe_stem(sku)
        counts[stem] = counts.get(stem, 0) + 1
        suffix = "" if counts[stem] == 1 else f"_{counts[stem]}"
        allocated[sku] = f"{stem}{suffix}.pdf"
    return allocated


def build_summary(
    job_id: str,
    groups: tuple[GroupPreview, ...],
    names: dict[str, str],
    output: Path,
) -> None:
    fields = [
        "job_id",
        "group_index",
        "box_index",
        "sku",
        "wfs_pdf_file",
        "wfs_pdf_page",
        "logistics_pdf_file",
        "logistics_pdf_page",
        "quantity",
        "box_id",
        "shipment_id",
        "gtin",
        "output_pdf",
        "status",
        "warnings",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for group in groups:
            warnings = " | ".join(issue.message for issue in group.issues)
            for pair in group.pairs:
                label = pair.wfs_label
                writer.writerow(
                    {
                        "job_id": job_id,
                        "group_index": pair.group_index,
                        "box_index": pair.box_index,
                        "sku": pair.sku,
                        "wfs_pdf_file": group.files.wfs_pdf_path.name,
                        "wfs_pdf_page": pair.wfs_pdf_page,
                        "logistics_pdf_file": group.files.logistics_pdf_path.name,
                        "logistics_pdf_page": pair.logistics_pdf_page,
                        "quantity": label.quantity or "",
                        "box_id": label.box_id or "",
                        "shipment_id": label.shipment_id or "",
                        "gtin": label.gtin or "",
                        "output_pdf": names[pair.sku],
                        "status": "processed_with_warning" if warnings else "processed",
                        "warnings": warnings,
                    }
                )


def build_processing_log(lines: tuple[str, ...], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _raise_zip_readback_error(
    archive: Path,
    expected: set[str],
    actual: set[str],
    bad_member: str | None,
) -> None:
    raise ProcessingError(
        (
            ValidationIssue(
                Severity.STRONG,
                "zip_readback",
                "输出 ZIP 回读校验失败",
                "不要下载；检查输出文件并重新生成。",
                filename=archive.name,
                expected=sorted(expected),
                actual={"members": sorted(actual), "bad_member": bad_member},
            ),
        )
    )


def build_verified_zip(
    pdfs: tuple[Path, ...],
    summary: Path,
    log: Path,
    archive: Path,
) -> None:
    if not pdfs:
        raise ValueError("at least one SKU PDF is required")
    archive.parent.mkdir(parents=True, exist_ok=True)
    members = (*pdfs, summary, log)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in members:
            zipped.write(path, path.name)
    try:
        with zipfile.ZipFile(archive) as zipped:
            bad_member = zipped.testzip()
            actual = set(zipped.namelist())
    except zipfile.BadZipFile as exc:
        _raise_zip_readback_error(archive, {path.name for path in members}, set(), str(exc))
    expected = {path.name for path in members}
    if bad_member is not None or actual != expected:
        _raise_zip_readback_error(archive, expected, actual, bad_member)
