from __future__ import annotations

import re
from dataclasses import dataclass

from app.errors import ProcessingError
from app.models import LabelType, Severity, ValidationIssue, WfsLabel

SEGMENT_RE = re.compile(r"\^XA.*?\^XZ", re.IGNORECASE | re.DOTALL)
FIELD_RE = re.compile(
    r"\^FO(\d+),(\d+)(?:(?!\^FO).)*?\^FD(.*?)\^FS",
    re.IGNORECASE | re.DOTALL,
)
BOX_TEXT_RE = re.compile(r"\bBOX\s+\d+\s+OF\s+\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class ZplField:
    x: int
    y: int
    text: str


def _clean_field_text(text: str) -> str:
    return " ".join(text.replace("_0D", " ").replace("_0A", " ").split()).strip()


def _extract_fields(segment: str) -> tuple[ZplField, ...]:
    return tuple(
        ZplField(int(x), int(y), _clean_field_text(text))
        for x, y, text in FIELD_RE.findall(segment)
    )


def _find_inline_value(text: str, marker: str) -> str | None:
    if marker.upper() not in text.upper():
        return None
    if ":" not in text:
        return None
    _, value = text.split(":", 1)
    value = value.strip()
    return value or None


def _find_relative_value(
    fields: tuple[ZplField, ...],
    marker: str,
    *,
    vertical: bool = False,
) -> str | None:
    marker_field = next(
        (field for field in fields if marker.upper() in field.text.upper()),
        None,
    )
    if marker_field is None:
        return None

    inline_value = _find_inline_value(marker_field.text, marker)
    if inline_value is not None:
        return inline_value

    if vertical:
        candidates = [
            field
            for field in fields
            if field.x == marker_field.x and field.y > marker_field.y and field.text
        ]
        if not candidates:
            candidates = [
                field for field in fields if field.y > marker_field.y and field.text
            ]
        candidates.sort(
            key=lambda field: (
                field.y - marker_field.y,
                abs(field.x - marker_field.x),
                field.x,
            )
        )
    else:
        candidates = [
            field
            for field in fields
            if field.y == marker_field.y and field.x > marker_field.x and field.text
        ]
        candidates.sort(key=lambda field: (field.x - marker_field.x, field.y))

    return candidates[0].text if candidates else None


def _segment_boundary_error(group_index: int, segment_index: int) -> ProcessingError:
    return ProcessingError(
        (
            ValidationIssue(
                severity=Severity.STRONG,
                rule="zpl_segment_boundary",
                message="ZPL 标签段缺少完整的 ^XA / ^XZ 边界",
                repair="请重新导出完整的 WFS ZPL/TXT 文件。",
                group_index=group_index,
                actual={"segment_index": segment_index, "reason": "missing_xz"},
            ),
        )
    )


def _complete_segments(text: str, group_index: int) -> tuple[str, ...]:
    if not text.strip():
        raise _segment_boundary_error(group_index, 1)

    events = [match.group(0).upper() for match in re.finditer(r"\^XA|\^XZ", text, re.IGNORECASE)]
    starts = events.count("^XA")
    ends = events.count("^XZ")
    if starts != ends:
        if starts > ends:
            raise _segment_boundary_error(group_index, ends + 1)
        raise ProcessingError(
            (
                ValidationIssue(
                    severity=Severity.STRONG,
                    rule="zpl_segment_boundary",
                    message="ZPL 标签段缺少完整的 ^XA / ^XZ 边界",
                    repair="请重新导出完整的 WFS ZPL/TXT 文件。",
                    group_index=group_index,
                    actual={"segment_index": starts + 1, "reason": "missing_xa"},
                ),
            )
        )

    segments = SEGMENT_RE.findall(text)
    if len(segments) != starts:
        raise _segment_boundary_error(group_index, len(segments) + 1)
    return tuple(segments)


def parse_wfs_zpl(text: str, group_index: int) -> tuple[WfsLabel, ...]:
    segments = _complete_segments(text, group_index)
    labels: list[WfsLabel] = []

    for index, segment in enumerate(segments, start=1):
        fields = _extract_fields(segment)
        upper_segment = segment.upper()
        if "SINGLE SKU" in upper_segment:
            label_type = LabelType.BOX
        elif "PALLET" in upper_segment:
            label_type = LabelType.PALLET
        else:
            label_type = LabelType.UNKNOWN

        box_text = next((match.group(0).upper() for match in BOX_TEXT_RE.finditer(segment)), None)
        sku = (
            _find_relative_value(fields, "SINGLE SKU", vertical=True)
            if label_type is LabelType.BOX
            else None
        )
        quantity_text = _find_relative_value(fields, "QUANTITY")
        quantity = int(quantity_text) if quantity_text and quantity_text.isdigit() else None

        labels.append(
            WfsLabel(
                group_index=group_index,
                zpl_index=index,
                pdf_page=index,
                label_type=label_type,
                raw_zpl=segment,
                sku=sku,
                box_id=_find_relative_value(fields, "BOX ID"),
                shipment_id=_find_relative_value(fields, "SHIPMENT ID"),
                gtin=_find_relative_value(fields, "GTIN"),
                quantity=quantity,
                box_text=box_text,
            )
        )

    return tuple(labels)
