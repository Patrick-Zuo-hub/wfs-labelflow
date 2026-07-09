from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeAlias

ContextScalar: TypeAlias = str | int | float | bool | None
ImmutableContext: TypeAlias = (
    ContextScalar
    | Mapping[str, "ImmutableContext"]
    | tuple["ImmutableContext", ...]
)


def _freeze_context(value: Any) -> ImmutableContext:
    if type(value) is float and not math.isfinite(value):
        raise TypeError("non-finite float is not supported in validation context")
    if type(value) in (type(None), bool, int, float, str):
        return value
    if isinstance(value, Mapping):
        frozen_mapping: dict[str, ImmutableContext] = {}
        for key, nested_value in value.items():
            if type(key) is not str:
                raise TypeError(
                    "unsupported validation context type: "
                    f"mapping key {type(key).__name__}"
                )
            frozen_mapping[key] = _freeze_context(nested_value)
        return MappingProxyType(frozen_mapping)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_context(item) for item in value)
    if isinstance(value, (set, frozenset)):
        frozen_items = (_freeze_context(item) for item in value)
        return tuple(sorted(frozen_items, key=repr))
    raise TypeError(f"unsupported validation context type: {type(value).__name__}")


def _thaw_context(value: ImmutableContext) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_context(nested_value) for key, nested_value in value.items()}
    if isinstance(value, tuple):
        return [_thaw_context(item) for item in value]
    return value


class LabelType(StrEnum):
    BOX = "box"
    PALLET = "pallet"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    STRONG = "strong"
    WEAK = "weak"
    AUDIT = "audit"


class JobState(StrEnum):
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    GENERATING = "generating"
    READY_FOR_DOWNLOAD = "ready_for_download"
    VALIDATION_FAILED = "validation_failed"
    GENERATION_FAILED = "generation_failed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class LabelGroupFiles:
    group_index: int
    wfs_pdf_path: Path
    wfs_zpl_path: Path
    logistics_pdf_path: Path


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    stem: str
    suffix: str
    path: Path


@dataclass(frozen=True)
class ArchiveInventory:
    archive_path: Path
    extracted_root: Path
    entries: tuple[ArchiveEntry, ...]


@dataclass(frozen=True)
class CarrierMappingRow:
    row_number: int
    carrier_number: str
    shipment_id: str


@dataclass(frozen=True)
class WfsLabel:
    group_index: int
    zpl_index: int
    pdf_page: int
    label_type: LabelType
    raw_zpl: str
    sku: str | None = None
    box_id: str | None = None
    shipment_id: str | None = None
    gtin: str | None = None
    quantity: int | None = None
    box_text: str | None = None


@dataclass(frozen=True)
class BoxPair:
    group_index: int
    box_index: int
    sku: str
    wfs_pdf_page: int
    logistics_pdf_page: int
    wfs_label: WfsLabel


@dataclass(frozen=True)
class ProcessingOptions:
    logistics_repeat: int = 1
    wfs_repeat: int = field(default=2, init=False)
    ignore_pallet: bool = field(default=True, init=False)
    merge_same_sku: bool = field(default=True, init=False)
    include_summary: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        if type(self.logistics_repeat) is not int or self.logistics_repeat not in (1, 2):
            raise ValueError("logistics_repeat must be 1 or 2")


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    rule: str
    message: str
    repair: str
    group_index: int | None = None
    filename: str | None = None
    page: int | None = None
    expected: Any = None
    actual: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", _freeze_context(self.expected))
        object.__setattr__(self, "actual", _freeze_context(self.actual))

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "rule": self.rule,
            "message": self.message,
            "repair": self.repair,
            "group_index": self.group_index,
            "filename": self.filename,
            "page": self.page,
            "expected": _thaw_context(self.expected),
            "actual": _thaw_context(self.actual),
        }


@dataclass(frozen=True)
class GroupPreview:
    files: LabelGroupFiles
    labels: tuple[WfsLabel, ...]
    pairs: tuple[BoxPair, ...]
    issues: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True)
class JobPreview:
    job_id: str
    groups: tuple[GroupPreview, ...]
    options: ProcessingOptions
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def pairs(self) -> tuple[BoxPair, ...]:
        return tuple(pair for group in self.groups for pair in group.pairs)
