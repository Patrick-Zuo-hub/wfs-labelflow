from __future__ import annotations

from app.errors import ProcessingError
from app.models import BoxPair, LabelType, Severity, ValidationIssue, WfsLabel


def build_pairs(
    group_index: int,
    labels: tuple[WfsLabel, ...],
    logistics_page_count: int,
) -> tuple[BoxPair, ...]:
    boxes = [label for label in labels if label.label_type is LabelType.BOX]
    pages = tuple(range(1, logistics_page_count + 1))
    if len(boxes) != len(pages):
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    "logistics_assignment_coverage",
                    f"第 {group_index} 组货代页无法完整且唯一地分配",
                    "修正有效箱标数与货代 PDF 页数后重试。",
                    group_index=group_index,
                    expected=len(boxes),
                    actual=len(pages),
                ),
            )
        )
    return tuple(
        BoxPair(
            group_index=group_index,
            box_index=box_index,
            sku=label.sku or "",
            wfs_pdf_page=label.pdf_page,
            logistics_pdf_page=logistics_page,
            wfs_label=label,
        )
        for box_index, (label, logistics_page) in enumerate(
            zip(boxes, pages, strict=True),
            start=1,
        )
    )
