from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.errors import ProcessingError
from app.models import LabelType, Severity, ValidationIssue, WfsLabel


def _raise(issues: list[ValidationIssue]) -> None:
    if issues:
        raise ProcessingError(tuple(issues))


def page_count(path: Path, group_index: int, role: str) -> int:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("encrypted")
        count = len(reader.pages)
    except Exception as exc:
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    "pdf_readable",
                    f"第 {group_index} 组 {role} PDF 无法读取",
                    "替换损坏或加密的 PDF。",
                    group_index=group_index,
                    filename=path.name,
                    actual=str(exc),
                ),
            )
        ) from exc
    if count < 1:
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    "pdf_has_pages",
                    f"第 {group_index} 组 {role} PDF 没有页面",
                    "上传至少包含一页的 PDF。",
                    group_index=group_index,
                    filename=path.name,
                    expected=">=1",
                    actual=count,
                ),
            )
        )
    return count


def validate_labels(group_index: int, labels: tuple[WfsLabel, ...]) -> None:
    issues: list[ValidationIssue] = []
    pallet_count = sum(label.label_type is LabelType.PALLET for label in labels)
    if pallet_count > 1:
        issues.append(
            ValidationIssue(
                Severity.STRONG,
                "single_pallet_maximum",
                f"第 {group_index} 组识别到多个 Pallet Label",
                "确认输入是否包含多个托盘；MVP 每组最多支持一个。",
                group_index=group_index,
                expected="0 or 1",
                actual=pallet_count,
            )
        )
    for label in labels:
        if label.label_type is LabelType.UNKNOWN:
            issues.append(
                ValidationIssue(
                    Severity.STRONG,
                    "unknown_label_type",
                    f"第 {group_index} 组 WFS 第 {label.pdf_page} 页类型无法识别",
                    "重新导出包含 SINGLE SKU 或 PALLET 标记的标签。",
                    group_index=group_index,
                    page=label.pdf_page,
                )
            )
        if label.label_type is LabelType.BOX and (
            label.sku is None or not 2 <= len(label.sku) <= 100 or "\n" in label.sku
        ):
            issues.append(
                ValidationIssue(
                    Severity.STRONG,
                    "box_sku_required",
                    f"第 {group_index} 组 WFS 第 {label.pdf_page} 页 SKU 无效",
                    "检查 SINGLE SKU 后的字段并重新导出 ZPL/TXT。",
                    group_index=group_index,
                    page=label.pdf_page,
                    expected="2-100 characters",
                    actual=label.sku,
                )
            )
    if not any(label.label_type is LabelType.BOX for label in labels):
        issues.append(
            ValidationIssue(
                Severity.STRONG,
                "effective_box_required",
                f"第 {group_index} 组没有有效箱标",
                "上传至少包含一个 SINGLE SKU 箱标的文件。",
                group_index=group_index,
            )
        )
    _raise(issues)


def validate_group_counts(
    group_index: int,
    wfs_pdf: Path,
    logistics_pdf: Path,
    labels: tuple[WfsLabel, ...],
) -> tuple[int, int]:
    wfs_pages = page_count(wfs_pdf, group_index, "WFS")
    logistics_pages = page_count(logistics_pdf, group_index, "货代")
    issues: list[ValidationIssue] = []
    if wfs_pages != len(labels):
        issues.append(
            ValidationIssue(
                Severity.STRONG,
                "wfs_pages_match_zpl_segments",
                f"第 {group_index} 组 WFS PDF 页数与 ZPL 标签段数不一致",
                "上传同一次导出的 WFS PDF 与 ZPL/TXT。",
                group_index=group_index,
                filename=wfs_pdf.name,
                expected=len(labels),
                actual=wfs_pages,
            )
        )
    box_count = sum(label.label_type is LabelType.BOX for label in labels)
    if box_count != logistics_pages:
        issues.append(
            ValidationIssue(
                Severity.STRONG,
                "effective_box_count_matches_logistics_pages",
                f"第 {group_index} 组有效箱标与货代页数不一致",
                f"请替换 {logistics_pdf.name}。",
                group_index=group_index,
                filename=logistics_pdf.name,
                expected=box_count,
                actual=logistics_pages,
            )
        )
    _raise(issues)
    return wfs_pages, logistics_pages


def collect_warnings(
    group_index: int,
    labels: tuple[WfsLabel, ...],
    logistics_page_count: int,
) -> tuple[ValidationIssue, ...]:
    warnings: list[ValidationIssue] = []
    shipment_ids = sorted({label.shipment_id for label in labels if label.shipment_id})
    if len(shipment_ids) > 1:
        warnings.append(
            ValidationIssue(
                Severity.WEAK,
                "multiple_shipment_ids",
                f"第 {group_index} 组识别到多个 Shipment ID",
                "确认该上传组确实属于同一批处理。",
                group_index=group_index,
                expected=1,
                actual=shipment_ids,
            )
        )
    if logistics_page_count > 200:
        warnings.append(
            ValidationIssue(
                Severity.WEAK,
                "large_logistics_pdf",
                f"第 {group_index} 组货代标签超过 200 页",
                "生成前确认没有误传大文件。",
                group_index=group_index,
                expected="<=200",
                actual=logistics_page_count,
            )
        )
    return tuple(warnings)
