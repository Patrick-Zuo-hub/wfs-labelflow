from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


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
        if self.logistics_repeat not in (1, 2):
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

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


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
