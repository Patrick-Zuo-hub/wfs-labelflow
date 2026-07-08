# WFS LabelFlow MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI application that validates up to five WFS label groups, previews immutable box-to-logistics mappings, and generates verified per-SKU PDFs in a ZIP while safely resetting every completed upload round.

**Architecture:** A server-rendered FastAPI monolith owns an isolated filesystem job for each validation attempt. Pure services parse and validate ZPL, build immutable box mappings, and compose PDF/CSV/log/ZIP output; a small browser controller retains selected files during correction, invalidates stale previews, and clears all client input only after server-side ZIP read-back succeeds.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Jinja2, native browser JavaScript, pypdf, pytest, HTTPX, Ruff, and uv for dependency locking.

---

## Plan ownership and controls

- Owner: Codex implementation agent
- Business authority: `wfs_label_processing_requirements.md`
- Approved design: `docs/superpowers/specs/2026-07-04-wfs-label-flow-design.md`
- Dependencies: provided files under `/Users/patrick/Documents/WFS LabelFlow/Sample Label`
- Primary risk: production filename rules are deferred; the temporary classifier must reject every ambiguous group.
- Completion proof: unit, integration, API, and browser tests pass; generated PDFs and ZIPs pass read-back; rendered sample output is visually inspected; `STATE.md` records the verified result.
- Next action after plan approval: execute Task 1 in this worktree with test-driven development.

## File map

```text
pyproject.toml                         Dependency and tool configuration
uv.lock                                Reproducible dependency resolution
README.md                              Local setup, run, and production workflow
app/
  __init__.py
  main.py                              FastAPI construction and route wiring
  config.py                            Runtime-root and retention configuration
  models.py                            Frozen domain records and job states
  errors.py                            Typed processing exception and issue helpers
  services/
    __init__.py
    storage.py                         job_id generation, path containment, cleanup
    classifier.py                      temporary deterministic role classification
    zpl_parser.py                      segmenting, classification, metadata extraction
    validation.py                      strong checks, weak warnings, page-count checks
    pairing.py                         immutable effective-box/logistics mapping
    pdf_processor.py                   page copying, merge, and read-back checks
    output_builder.py                  CSV, log, collision-safe filenames, ZIP
    job_processor.py                   atomic validate/preview/generate orchestration
    registry.py                        in-memory validated-job and result registry
  templates/
    index.html                         upload, preview, error, and success regions
  static/
    app.js                             browser file lists, API flow, reset behavior
    styles.css                         accessible local UI styling
tests/
  conftest.py                          temp settings and app client fixtures
  fixtures/sample/                    tracked copies of the three provided samples
  unit/                                pure-service tests
  integration/                         PDF/output/orchestrator tests
  api/                                 FastAPI contract tests
  browser/                             Playwright production-flow tests
scripts/
  inspect_sample.py                    reproducible sample metadata inspection
```

## Task 1: Scaffold the Python application and portable sample fixture

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `tests/__init__.py`
- Create: `tests/test_health.py`
- Create: `tests/fixtures/sample/WFS Label-Sample.pdf`
- Create: `tests/fixtures/sample/WFS Label-Sample.txt`
- Create: `tests/fixtures/sample/Logistics Label-Sample.pdf`
- Modify: `.gitignore`

- [ ] **Step 1: Copy the user-provided sample into the tracked test fixture directory**

Run:

```bash
mkdir -p tests/fixtures/sample
cp "/Users/patrick/Documents/WFS LabelFlow/Sample Label/WFS Label-Sample.pdf" "tests/fixtures/sample/WFS Label-Sample.pdf"
cp "/Users/patrick/Documents/WFS LabelFlow/Sample Label/WFS Label-Sample.txt" "tests/fixtures/sample/WFS Label-Sample.txt"
cp "/Users/patrick/Documents/WFS LabelFlow/Sample Label/Logistics Label-Sample.pdf" "tests/fixtures/sample/Logistics Label-Sample.pdf"
```

Expected: all three commands exit 0 and `find tests/fixtures/sample -type f | wc -l` prints `3`.

- [ ] **Step 2: Write the failing health test**

Create `tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_ready() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Add the project manifest and minimal app**

Create `pyproject.toml`:

```toml
[project]
name = "wfs-labelflow"
version = "0.1.0"
description = "Local WFS and logistics label validation and PDF assembly tool"
requires-python = ">=3.11"
dependencies = [
  "fastapi",
  "jinja2",
  "pypdf",
  "python-multipart",
  "uvicorn[standard]",
]

[dependency-groups]
dev = [
  "httpx",
  "pytest",
  "pytest-asyncio",
  "ruff",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Create `app/__init__.py` and `tests/__init__.py` as empty package markers.

Create `app/main.py`:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="WFS LabelFlow")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

Append these runtime paths to `.gitignore`:

```gitignore
.ruff_cache/
data/jobs/
```

- [ ] **Step 4: Resolve dependencies and verify the test**

Run:

```bash
uv sync
uv run pytest tests/test_health.py -v
uv run ruff check app tests
```

Expected: one test passes and Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore app tests
git commit -m "chore: scaffold WFS LabelFlow application"
```

## Task 2: Define immutable domain records and structured validation issues

**Files:**
- Create: `app/models.py`
- Create: `app/errors.py`
- Create: `tests/unit/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/unit/test_models.py`:

```python
from dataclasses import FrozenInstanceError

import pytest

from app.models import (
    BoxPair,
    JobState,
    LabelType,
    ProcessingOptions,
    Severity,
    ValidationIssue,
    WfsLabel,
)


def test_processing_options_reject_invalid_logistics_repeat() -> None:
    with pytest.raises(ValueError, match="logistics_repeat"):
        ProcessingOptions(logistics_repeat=3)


def test_box_pair_is_immutable() -> None:
    label = WfsLabel(
        group_index=1,
        zpl_index=1,
        pdf_page=1,
        label_type=LabelType.BOX,
        sku="SKU-A",
        raw_zpl="^XA^FDSINGLE SKU:^FS^FDSKU-A^FS^XZ",
    )
    pair = BoxPair(
        group_index=1,
        box_index=1,
        sku="SKU-A",
        wfs_pdf_page=1,
        logistics_pdf_page=1,
        wfs_label=label,
    )

    with pytest.raises(FrozenInstanceError):
        pair.sku = "CHANGED"  # type: ignore[misc]


def test_validation_issue_serializes_exact_context() -> None:
    issue = ValidationIssue(
        severity=Severity.STRONG,
        rule="effective_box_count_matches_logistics_pages",
        message="有效箱标与货代页数不一致",
        repair="请替换货代 PDF。",
        group_index=2,
        filename="Logistics_02.pdf",
        expected=3,
        actual=2,
    )

    assert issue.as_dict()["group_index"] == 2
    assert issue.as_dict()["expected"] == 3
    assert issue.as_dict()["actual"] == 2
    assert JobState.AWAITING_CONFIRMATION.value == "awaiting_confirmation"
```

- [ ] **Step 2: Run the tests and confirm the missing-module failure**

Run:

```bash
uv run pytest tests/unit/test_models.py -v
```

Expected: collection fails because `app.models` does not exist.

- [ ] **Step 3: Implement the complete domain model**

Create `app/models.py`:

```python
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
```

Create `app/errors.py`:

```python
from app.models import ValidationIssue


class ProcessingError(Exception):
    def __init__(self, issues: tuple[ValidationIssue, ...]):
        if not issues:
            raise ValueError("ProcessingError requires at least one issue")
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/unit/test_models.py -v
uv run ruff check app/models.py app/errors.py tests/unit/test_models.py
```

Expected: three tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/errors.py tests/unit/test_models.py
git commit -m "feat: define immutable label domain model"
```

## Task 3: Implement safe job storage and cleanup containment

**Files:**
- Create: `app/config.py`
- Create: `app/services/__init__.py`
- Create: `app/services/storage.py`
- Create: `tests/unit/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/unit/test_storage.py`:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.storage import JobStorage


def test_job_paths_are_isolated_under_runtime_root(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")

    assert paths.root == tmp_path.resolve() / "20260704_080000_ab12"
    assert paths.uploads.is_dir()
    assert paths.intermediate.is_dir()
    assert paths.output.is_dir()


def test_cleanup_rejects_path_escape(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)

    with pytest.raises(ValueError, match="invalid job_id"):
        storage.cleanup("../outside")


def test_success_cleanup_keeps_only_zip(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")
    (paths.uploads / "source.pdf").write_bytes(b"source")
    (paths.intermediate / "part.pdf").write_bytes(b"part")
    archive = paths.output / "output.zip"
    archive.write_bytes(b"zip")

    storage.cleanup_inputs("20260704_080000_ab12", archive)

    assert not paths.uploads.exists()
    assert not paths.intermediate.exists()
    assert archive.read_bytes() == b"zip"


def test_expired_result_is_removed(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    paths = storage.create("20260704_080000_ab12")
    archive = paths.output / "output.zip"
    archive.write_bytes(b"zip")
    old = datetime.now(UTC) - timedelta(minutes=31)

    removed = storage.cleanup_expired({"20260704_080000_ab12": old}, timedelta(minutes=30))

    assert removed == ("20260704_080000_ab12",)
    assert not paths.root.exists()
```

- [ ] **Step 2: Run the tests and confirm the missing-module failure**

Run:

```bash
uv run pytest tests/unit/test_storage.py -v
```

Expected: collection fails because `app.services.storage` does not exist.

- [ ] **Step 3: Implement storage containment and retention**

Create `app/config.py`:

```python
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    runtime_root: Path = Path("data/jobs")
    zip_retention: timedelta = timedelta(minutes=30)
```

Create `app/services/__init__.py` as an empty package marker.

Create `app/services/storage.py`:

```python
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

JOB_ID = re.compile(r"^\d{8}_\d{6}_[a-f0-9]{4,16}$")


@dataclass(frozen=True)
class JobPaths:
    root: Path
    uploads: Path
    intermediate: Path
    output: Path


class JobStorage:
    def __init__(self, runtime_root: Path):
        self.runtime_root = runtime_root.resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)

    def _root_for(self, job_id: str) -> Path:
        if not JOB_ID.fullmatch(job_id):
            raise ValueError("invalid job_id")
        root = (self.runtime_root / job_id).resolve()
        if root.parent != self.runtime_root:
            raise ValueError("job path escapes runtime root")
        return root

    def create(self, job_id: str) -> JobPaths:
        root = self._root_for(job_id)
        uploads = root / "uploads"
        intermediate = root / "intermediate"
        output = root / "output"
        for path in (uploads, intermediate, output):
            path.mkdir(parents=True, exist_ok=False)
        return JobPaths(root, uploads, intermediate, output)

    def paths(self, job_id: str) -> JobPaths:
        root = self._root_for(job_id)
        return JobPaths(root, root / "uploads", root / "intermediate", root / "output")

    def cleanup_inputs(self, job_id: str, archive: Path) -> None:
        paths = self.paths(job_id)
        resolved_archive = archive.resolve()
        if resolved_archive.parent != paths.output.resolve():
            raise ValueError("archive is outside job output")
        if not resolved_archive.is_file():
            raise FileNotFoundError(resolved_archive)
        shutil.rmtree(paths.uploads, ignore_errors=False)
        shutil.rmtree(paths.intermediate, ignore_errors=False)
        for child in paths.output.iterdir():
            if child.resolve() != resolved_archive:
                child.unlink()

    def cleanup(self, job_id: str) -> None:
        root = self._root_for(job_id)
        if root.exists():
            shutil.rmtree(root)

    def cleanup_expired(
        self,
        completed_at: dict[str, datetime],
        retention: timedelta,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        current = now or datetime.now(UTC)
        removed: list[str] = []
        for job_id, timestamp in completed_at.items():
            if current - timestamp > retention:
                self.cleanup(job_id)
                removed.append(job_id)
        return tuple(removed)
```

- [ ] **Step 4: Run storage tests**

Run:

```bash
uv run pytest tests/unit/test_storage.py -v
uv run ruff check app/config.py app/services/storage.py tests/unit/test_storage.py
```

Expected: four tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/services tests/unit/test_storage.py
git commit -m "feat: isolate and safely clean job storage"
```

## Task 4: Implement temporary deterministic file classification

**Files:**
- Create: `app/services/classifier.py`
- Create: `tests/unit/test_classifier.py`

- [ ] **Step 1: Write failing classifier tests**

Create `tests/unit/test_classifier.py`:

```python
from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.services.classifier import classify_group


def touch(path: Path) -> Path:
    path.write_bytes(b"x")
    return path


def test_sample_stems_classify_without_guessing(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "WFS Label-Sample.pdf"),
        touch(tmp_path / "WFS Label-Sample.txt"),
        touch(tmp_path / "Logistics Label-Sample.pdf"),
    ]

    result = classify_group(1, files)

    assert result.wfs_pdf_path.name == "WFS Label-Sample.pdf"
    assert result.wfs_zpl_path.name == "WFS Label-Sample.txt"
    assert result.logistics_pdf_path.name == "Logistics Label-Sample.pdf"


def test_ambiguous_pdfs_are_rejected(tmp_path: Path) -> None:
    files = [
        touch(tmp_path / "source.txt"),
        touch(tmp_path / "first.pdf"),
        touch(tmp_path / "second.pdf"),
    ]

    with pytest.raises(ProcessingError) as caught:
        classify_group(3, files)

    issue = caught.value.issues[0]
    assert issue.rule == "file_role_ambiguity"
    assert issue.group_index == 3
    assert issue.actual == ["first.pdf", "second.pdf"]


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    files = [touch(tmp_path / "notes.csv")]

    with pytest.raises(ProcessingError) as caught:
        classify_group(2, files)

    assert caught.value.issues[0].rule == "unsupported_extension"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run pytest tests/unit/test_classifier.py -v
```

Expected: collection fails because `app.services.classifier` does not exist.

- [ ] **Step 3: Implement the temporary classifier**

Create `app/services/classifier.py`:

```python
from pathlib import Path

from app.errors import ProcessingError
from app.models import LabelGroupFiles, Severity, ValidationIssue


def _fail(group_index: int, rule: str, message: str, repair: str, actual: object) -> None:
    raise ProcessingError(
        (
            ValidationIssue(
                severity=Severity.STRONG,
                rule=rule,
                message=message,
                repair=repair,
                group_index=group_index,
                actual=actual,
            ),
        )
    )


def classify_group(group_index: int, files: list[Path]) -> LabelGroupFiles:
    unsupported = sorted(path.name for path in files if path.suffix.lower() not in {".pdf", ".txt", ".zpl"})
    if unsupported:
        _fail(group_index, "unsupported_extension", "存在不支持的文件类型", "仅上传 PDF、TXT 或 ZPL。", unsupported)

    sources = [path for path in files if path.suffix.lower() in {".txt", ".zpl"}]
    pdfs = [path for path in files if path.suffix.lower() == ".pdf"]
    if len(sources) != 1 or len(pdfs) != 2:
        _fail(
            group_index,
            "required_file_roles",
            "每个非空组必须包含一个 ZPL/TXT 和两个 PDF",
            "删除重复文件或补齐缺失文件。",
            sorted(path.name for path in files),
        )

    source = sources[0]
    same_stem = [path for path in pdfs if path.stem.casefold() == source.stem.casefold()]
    keyword_wfs = [path for path in pdfs if "wfs" in path.stem.casefold()]
    wfs_candidates = same_stem or keyword_wfs
    if len(wfs_candidates) != 1:
        _fail(
            group_index,
            "file_role_ambiguity",
            "无法唯一识别 WFS PDF",
            "按样例命名文件，或等待生产命名规则确定后重试。",
            sorted(path.name for path in pdfs),
        )
    wfs_pdf = wfs_candidates[0]
    logistics_candidates = [path for path in pdfs if path != wfs_pdf]
    if len(logistics_candidates) != 1:
        _fail(
            group_index,
            "file_role_ambiguity",
            "无法唯一识别货代 PDF",
            "删除重复或不明确的 PDF。",
            sorted(path.name for path in pdfs),
        )
    return LabelGroupFiles(group_index, wfs_pdf, source, logistics_candidates[0])
```

- [ ] **Step 4: Run classifier tests**

Run:

```bash
uv run pytest tests/unit/test_classifier.py -v
uv run ruff check app/services/classifier.py tests/unit/test_classifier.py
```

Expected: three tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/services/classifier.py tests/unit/test_classifier.py
git commit -m "feat: classify sample label files without guessing"
```

## Task 5: Parse complete ZPL segments and extract label metadata

**Files:**
- Create: `app/services/zpl_parser.py`
- Create: `tests/unit/test_zpl_parser.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/unit/test_zpl_parser.py`:

```python
from pathlib import Path

import pytest

from app.errors import ProcessingError
from app.models import LabelType
from app.services.zpl_parser import parse_wfs_zpl

SAMPLE = Path("tests/fixtures/sample/WFS Label-Sample.txt")


def test_sample_has_three_boxes_and_one_pallet() -> None:
    labels = parse_wfs_zpl(SAMPLE.read_text(encoding="utf-8"), group_index=1)

    assert len(labels) == 4
    assert [label.pdf_page for label in labels] == [1, 2, 3, 4]
    assert [label.label_type for label in labels] == [
        LabelType.BOX,
        LabelType.BOX,
        LabelType.BOX,
        LabelType.PALLET,
    ]
    assert [label.sku for label in labels[:3]] == [
        "F-FPG-C9-PN-IVN",
        "P-kcup-white-2",
        "P-kcup-white-2",
    ]
    assert [label.quantity for label in labels[:3]] == [37, 28, 28]
    assert labels[3].sku is None


def test_pallet_position_does_not_depend_on_last_page() -> None:
    pallet = "^XA^FDPALLET^FS^FDSHIPMENT ID BARCODE:^FS^XZ"
    box = "^XA^FDSINGLE SKU:^FS^FDSKU-1^FS^FD BOX 1 OF 1^FS^XZ"

    labels = parse_wfs_zpl(pallet + box, group_index=2)

    assert labels[0].label_type is LabelType.PALLET
    assert labels[1].label_type is LabelType.BOX


def test_incomplete_segment_is_strong_error() -> None:
    with pytest.raises(ProcessingError) as caught:
        parse_wfs_zpl("^XA^FDSINGLE SKU:^FS", group_index=4)

    assert caught.value.issues[0].rule == "zpl_segment_boundary"
    assert caught.value.issues[0].group_index == 4


def test_unclassifiable_segment_is_unknown() -> None:
    labels = parse_wfs_zpl("^XA^FDHELLO^FS^XZ", group_index=1)

    assert labels[0].label_type is LabelType.UNKNOWN
```

- [ ] **Step 2: Run parser tests and verify failure**

Run:

```bash
uv run pytest tests/unit/test_zpl_parser.py -v
```

Expected: collection fails because `app.services.zpl_parser` does not exist.

- [ ] **Step 3: Implement segmenting and relative field extraction**

Create `app/services/zpl_parser.py`:

```python
import re
from dataclasses import dataclass

from app.errors import ProcessingError
from app.models import LabelType, Severity, ValidationIssue, WfsLabel

SEGMENT = re.compile(r"\^XA.*?\^XZ", re.DOTALL | re.IGNORECASE)
POSITIONED_FIELD = re.compile(
    r"\^FO(\d+),(\d+)(?:(?!\^FO).)*?\^FD(.*?)\^FS",
    re.DOTALL | re.IGNORECASE,
)
BOX_TEXT = re.compile(r"\bBOX\s+\d+\s+OF\s+\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class ZplField:
    x: int
    y: int
    text: str


def _clean(value: str) -> str:
    return " ".join(value.replace("_0D", " ").replace("_0A", " ").split()).strip()


def _positioned_fields(segment: str) -> tuple[ZplField, ...]:
    return tuple(
        ZplField(int(x), int(y), _clean(text))
        for x, y, text in POSITIONED_FIELD.findall(segment)
    )


def _value_near(
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
    inline = marker_field.text.split(":", 1)[1].strip() if ":" in marker_field.text else ""
    if inline:
        return inline
    if vertical:
        candidates = [
            field
            for field in fields
            if field.x == marker_field.x and field.y > marker_field.y and field.text
        ]
        candidates.sort(key=lambda field: field.y - marker_field.y)
    else:
        candidates = [
            field
            for field in fields
            if field.y == marker_field.y and field.x > marker_field.x and field.text
        ]
        candidates.sort(key=lambda field: field.x - marker_field.x)
    if candidates:
        return candidates[0].text
    return None


def parse_wfs_zpl(text: str, group_index: int) -> tuple[WfsLabel, ...]:
    starts = len(re.findall(r"\^XA", text, re.IGNORECASE))
    ends = len(re.findall(r"\^XZ", text, re.IGNORECASE))
    segments = SEGMENT.findall(text)
    if not text.strip() or starts != ends or starts != len(segments):
        raise ProcessingError(
            (
                ValidationIssue(
                    severity=Severity.STRONG,
                    rule="zpl_segment_boundary",
                    message="ZPL 标签段缺少完整的 ^XA / ^XZ 边界",
                    repair="重新导出完整的 WFS ZPL/TXT 文件。",
                    group_index=group_index,
                    expected=starts,
                    actual=len(segments),
                ),
            )
        )

    labels: list[WfsLabel] = []
    for index, segment in enumerate(segments, start=1):
        fields = _positioned_fields(segment)
        upper = segment.upper()
        if "SINGLE SKU" in upper:
            label_type = LabelType.BOX
        elif "PALLET" in upper and "SINGLE SKU" not in upper:
            label_type = LabelType.PALLET
        else:
            label_type = LabelType.UNKNOWN
        box_match = BOX_TEXT.search(" ".join(field.text for field in fields))
        quantity_text = _value_near(fields, "QUANTITY")
        labels.append(
            WfsLabel(
                group_index=group_index,
                zpl_index=index,
                pdf_page=index,
                label_type=label_type,
                sku=(
                    _value_near(fields, "SINGLE SKU", vertical=True)
                    if label_type is LabelType.BOX
                    else None
                ),
                box_id=_value_near(fields, "BOX ID"),
                shipment_id=_value_near(fields, "SHIPMENT ID"),
                gtin=_value_near(fields, "GTIN"),
                quantity=int(quantity_text) if quantity_text and quantity_text.isdigit() else None,
                box_text=box_match.group(0).upper() if box_match else None,
                raw_zpl=segment,
            )
        )
    return tuple(labels)
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
uv run pytest tests/unit/test_zpl_parser.py -v
uv run ruff check app/services/zpl_parser.py tests/unit/test_zpl_parser.py
```

Expected: four tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/services/zpl_parser.py tests/unit/test_zpl_parser.py
git commit -m "feat: parse WFS ZPL label metadata"
```

## Task 6: Validate each group and build the immutable box mapping

**Files:**
- Create: `app/services/validation.py`
- Create: `app/services/pairing.py`
- Create: `tests/unit/test_validation_and_pairing.py`

- [ ] **Step 1: Write failing validation and pairing tests**

Create `tests/unit/test_validation_and_pairing.py`:

```python
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
    assert warnings[0].actual == ["SHIP-1", "SHIP-2"]


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
```

- [ ] **Step 2: Run tests and verify missing modules**

Run:

```bash
uv run pytest tests/unit/test_validation_and_pairing.py -v
```

Expected: collection fails because validation and pairing modules do not exist.

- [ ] **Step 3: Implement strong validation and ordered pairing**

Create `app/services/validation.py`:

```python
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
```

Create `app/services/pairing.py`:

```python
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
        for box_index, (label, logistics_page) in enumerate(zip(boxes, pages, strict=True), start=1)
    )
```

- [ ] **Step 4: Run validation and pairing tests**

Run:

```bash
uv run pytest tests/unit/test_validation_and_pairing.py -v
uv run ruff check app/services/validation.py app/services/pairing.py tests/unit/test_validation_and_pairing.py
```

Expected: seven tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/services/validation.py app/services/pairing.py tests/unit/test_validation_and_pairing.py
git commit -m "feat: validate groups and pair logistics pages"
```

## Task 7: Compose ordered per-SKU PDFs and verify page counts

**Files:**
- Create: `app/services/pdf_processor.py`
- Create: `tests/unit/test_pdf_processor.py`

- [ ] **Step 1: Write failing PDF composition tests**

Create `tests/unit/test_pdf_processor.py`:

```python
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.models import BoxPair, LabelType, ProcessingOptions, WfsLabel
from app.services.pdf_processor import build_sku_pdf, merge_pdfs


def write_sized_pages(path: Path, widths: list[float]) -> Path:
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=100)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def pair(box: int, sku: str, wfs_page: int, logistics_page: int) -> BoxPair:
    label = WfsLabel(1, wfs_page, wfs_page, LabelType.BOX, "^XA^XZ", sku=sku)
    return BoxPair(1, box, sku, wfs_page, logistics_page, label)


def widths(path: Path) -> list[int]:
    return [round(float(page.mediabox.width)) for page in PdfReader(path).pages]


def test_sku_pdf_preserves_wwl_box_order(tmp_path: Path) -> None:
    wfs = write_sized_pages(tmp_path / "wfs.pdf", [101, 102])
    logistics = write_sized_pages(tmp_path / "logistics.pdf", [201, 202])
    output = tmp_path / "sku.pdf"

    build_sku_pdf(
        (pair(1, "A", 1, 1), pair(2, "A", 2, 2)),
        wfs,
        logistics,
        ProcessingOptions(logistics_repeat=1),
        output,
    )

    assert widths(output) == [101, 101, 201, 102, 102, 202]


def test_double_logistics_mode_preserves_wwll_order(tmp_path: Path) -> None:
    wfs = write_sized_pages(tmp_path / "wfs.pdf", [101])
    logistics = write_sized_pages(tmp_path / "logistics.pdf", [201])
    output = tmp_path / "sku.pdf"

    build_sku_pdf(
        (pair(1, "A", 1, 1),),
        wfs,
        logistics,
        ProcessingOptions(logistics_repeat=2),
        output,
    )

    assert widths(output) == [101, 101, 201, 201]


def test_merge_is_simple_append(tmp_path: Path) -> None:
    first = write_sized_pages(tmp_path / "first.pdf", [101, 102])
    second = write_sized_pages(tmp_path / "second.pdf", [201])
    output = tmp_path / "merged.pdf"

    merge_pdfs((first, second), output)

    assert widths(output) == [101, 102, 201]
```

- [ ] **Step 2: Run tests and verify missing module**

Run:

```bash
uv run pytest tests/unit/test_pdf_processor.py -v
```

Expected: collection fails because `app.services.pdf_processor` does not exist.

- [ ] **Step 3: Implement composition and read-back**

Create `app/services/pdf_processor.py`:

```python
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.errors import ProcessingError
from app.models import BoxPair, ProcessingOptions, Severity, ValidationIssue


def _write(writer: PdfWriter, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)


def build_sku_pdf(
    pairs: tuple[BoxPair, ...],
    wfs_pdf: Path,
    logistics_pdf: Path,
    options: ProcessingOptions,
    output: Path,
) -> None:
    wfs_reader = PdfReader(wfs_pdf)
    logistics_reader = PdfReader(logistics_pdf)
    writer = PdfWriter()
    for pair in pairs:
        wfs_page = wfs_reader.pages[pair.wfs_pdf_page - 1]
        logistics_page = logistics_reader.pages[pair.logistics_pdf_page - 1]
        for _ in range(options.wfs_repeat):
            writer.add_page(wfs_page)
        for _ in range(options.logistics_repeat):
            writer.add_page(logistics_page)
    _write(writer, output)
    expected = len(pairs) * (options.wfs_repeat + options.logistics_repeat)
    actual = len(PdfReader(output).pages)
    if actual != expected:
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    "output_page_count",
                    f"{output.name} 输出页数校验失败",
                    "停止下载并检查 PDF 生成流程。",
                    filename=output.name,
                    expected=expected,
                    actual=actual,
                ),
            )
        )


def merge_pdfs(inputs: tuple[Path, ...], output: Path) -> None:
    writer = PdfWriter()
    expected = 0
    for path in inputs:
        reader = PdfReader(path)
        expected += len(reader.pages)
        for page in reader.pages:
            writer.add_page(page)
    _write(writer, output)
    actual = len(PdfReader(output).pages)
    if actual != expected:
        raise ProcessingError(
            (
                ValidationIssue(
                    Severity.STRONG,
                    "merge_page_count",
                    f"{output.name} 合并页数校验失败",
                    "停止下载并检查跨组合并流程。",
                    filename=output.name,
                    expected=expected,
                    actual=actual,
                ),
            )
        )
```

- [ ] **Step 4: Run PDF tests**

Run:

```bash
uv run pytest tests/unit/test_pdf_processor.py -v
uv run ruff check app/services/pdf_processor.py tests/unit/test_pdf_processor.py
```

Expected: three tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/services/pdf_processor.py tests/unit/test_pdf_processor.py
git commit -m "feat: compose and verify ordered SKU PDFs"
```

## Task 8: Build collision-safe filenames, summary, log, and verified ZIP

**Files:**
- Create: `app/services/output_builder.py`
- Create: `tests/unit/test_output_builder.py`

- [ ] **Step 1: Write failing output tests**

Create `tests/unit/test_output_builder.py`:

```python
import csv
import zipfile
from pathlib import Path

from app.models import (
    BoxPair,
    GroupPreview,
    LabelGroupFiles,
    LabelType,
    Severity,
    ValidationIssue,
    WfsLabel,
)
from app.services.output_builder import (
    allocate_output_names,
    build_summary,
    build_verified_zip,
)


def pair(sku: str) -> BoxPair:
    label = WfsLabel(1, 1, 1, LabelType.BOX, "^XA^XZ", sku=sku)
    return BoxPair(1, 1, sku, 1, 1, label)


def test_sanitized_name_collisions_get_stable_suffixes() -> None:
    names = allocate_output_names(("SKU A/B", "SKU A:B", "SKU-C"))

    assert names == {
        "SKU A/B": "SKU A-B.pdf",
        "SKU A:B": "SKU A-B_2.pdf",
        "SKU-C": "SKU-C.pdf",
    }


def test_summary_keeps_original_sku_and_output_name(tmp_path: Path) -> None:
    output = tmp_path / "summary.csv"
    current_pair = pair("SKU A/B")
    files = LabelGroupFiles(
        1,
        tmp_path / "wfs.pdf",
        tmp_path / "wfs.txt",
        tmp_path / "logistics.pdf",
    )
    warning = ValidationIssue(
        Severity.WEAK,
        "multiple_shipment_ids",
        "multiple shipment IDs",
        "confirm group",
        group_index=1,
    )
    group = GroupPreview(files, (current_pair.wfs_label,), (current_pair,), (warning,))

    build_summary("job", (group,), {"SKU A/B": "SKU A-B.pdf"}, output)

    with output.open(newline="", encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle))
    assert row["sku"] == "SKU A/B"
    assert row["output_pdf"] == "SKU A-B.pdf"
    assert row["wfs_pdf_file"] == "wfs.pdf"
    assert row["logistics_pdf_file"] == "logistics.pdf"
    assert row["warnings"] == "multiple shipment IDs"


def test_zip_is_reopened_and_contains_required_members(tmp_path: Path) -> None:
    pdf = tmp_path / "SKU-A.pdf"
    summary = tmp_path / "summary.csv"
    log = tmp_path / "processing_log.txt"
    for path in (pdf, summary, log):
        path.write_bytes(b"content")
    archive = tmp_path / "output.zip"

    build_verified_zip((pdf,), summary, log, archive)

    with zipfile.ZipFile(archive) as zipped:
        assert sorted(zipped.namelist()) == ["SKU-A.pdf", "processing_log.txt", "summary.csv"]
        assert zipped.testzip() is None
```

- [ ] **Step 2: Run tests and verify missing module**

Run:

```bash
uv run pytest tests/unit/test_output_builder.py -v
```

Expected: collection fails because `app.services.output_builder` does not exist.

- [ ] **Step 3: Implement output builders**

Create `app/services/output_builder.py`:

```python
import csv
import re
import zipfile
from pathlib import Path

from app.errors import ProcessingError
from app.models import GroupPreview, Severity, ValidationIssue

UNSAFE = re.compile(r'[\/\\:*?"<>|\x00-\x1f]')


def _safe_stem(sku: str) -> str:
    stem = UNSAFE.sub("-", sku).strip(" .-")
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
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_verified_zip(
    pdfs: tuple[Path, ...],
    summary: Path,
    log: Path,
    archive: Path,
) -> None:
    if not pdfs:
        raise ValueError("at least one SKU PDF is required")
    members = (*pdfs, summary, log)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in members:
            zipped.write(path, path.name)
    try:
        with zipfile.ZipFile(archive) as zipped:
            bad_member = zipped.testzip()
            actual = set(zipped.namelist())
    except zipfile.BadZipFile as exc:
        bad_member = str(exc)
        actual = set()
    expected = {path.name for path in members}
    if bad_member is not None or actual != expected:
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
```

- [ ] **Step 4: Run output tests**

Run:

```bash
uv run pytest tests/unit/test_output_builder.py -v
uv run ruff check app/services/output_builder.py tests/unit/test_output_builder.py
```

Expected: three tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/services/output_builder.py tests/unit/test_output_builder.py
git commit -m "feat: build verified label output archive"
```

## Task 9: Orchestrate atomic validation, preview, generation, and cleanup

**Files:**
- Create: `app/services/registry.py`
- Create: `app/services/job_processor.py`
- Create: `tests/integration/test_job_processor.py`

- [ ] **Step 1: Write failing orchestration tests**

Create `tests/integration/test_job_processor.py`:

```python
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.errors import ProcessingError
from app.models import JobState, ProcessingOptions
from app.services.job_processor import JobProcessor, UploadedGroup
from app.services.registry import JobRegistry
from app.services.storage import JobStorage

SAMPLE = Path("tests/fixtures/sample")


def sample_group(index: int) -> UploadedGroup:
    return UploadedGroup(
        index,
        (
            SAMPLE / "WFS Label-Sample.pdf",
            SAMPLE / "WFS Label-Sample.txt",
            SAMPLE / "Logistics Label-Sample.pdf",
        ),
    )


def test_sample_validates_then_generates_atomic_zip(tmp_path: Path) -> None:
    registry = JobRegistry()
    processor = JobProcessor(JobStorage(tmp_path), registry)

    preview = processor.validate((sample_group(1),), ProcessingOptions(logistics_repeat=1))
    result = processor.generate(preview.job_id)

    assert registry.get(preview.job_id).state is JobState.READY_FOR_DOWNLOAD
    assert result.archive.is_file()
    assert not result.paths.uploads.exists()
    assert not result.paths.intermediate.exists()
    assert not list(result.paths.output.glob("*.pdf"))
    with zipfile.ZipFile(result.archive) as archive:
        assert set(result.sku_pdf_names) <= set(archive.namelist())
        assert archive.testzip() is None


def test_one_bad_group_prevents_all_output(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    for source in sample_group(1).files:
        (bad / source.name).write_bytes(source.read_bytes())
    (bad / "Logistics Label-Sample.pdf").write_bytes(b"not a pdf")
    registry = JobRegistry()
    processor = JobProcessor(JobStorage(tmp_path / "jobs"), registry)

    with pytest.raises(ProcessingError):
        processor.validate(
            (
                sample_group(1),
                UploadedGroup(2, tuple(bad.iterdir())),
            ),
            ProcessingOptions(),
        )

    assert not list((tmp_path / "jobs").glob("*/output/*.zip"))


def test_same_sku_across_nonadjacent_groups_is_appended_by_group(tmp_path: Path) -> None:
    processor = JobProcessor(JobStorage(tmp_path), JobRegistry())
    preview = processor.validate(
        (sample_group(1), sample_group(3)),
        ProcessingOptions(logistics_repeat=1),
    )

    result = processor.generate(preview.job_id)

    with zipfile.ZipFile(result.archive) as archive:
        repeated_sku = PdfReader(BytesIO(archive.read("P-kcup-white-2.pdf")))
    assert len(repeated_sku.pages) == 12


def test_generate_rejects_unknown_or_unconfirmed_job(tmp_path: Path) -> None:
    processor = JobProcessor(JobStorage(tmp_path), JobRegistry())

    with pytest.raises(KeyError):
        processor.generate("20260704_080000_ab12")
```

- [ ] **Step 2: Run tests and verify missing modules**

Run:

```bash
uv run pytest tests/integration/test_job_processor.py -v
```

Expected: collection fails because registry and job processor modules do not exist.

- [ ] **Step 3: Implement the in-memory registry**

Create `app/services/registry.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.models import JobPreview, JobState
from app.services.storage import JobPaths


@dataclass
class JobRecord:
    state: JobState
    preview: JobPreview
    paths: JobPaths
    archive: Path | None = None
    completed_at: datetime | None = None


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    def add(self, job_id: str, record: JobRecord) -> None:
        if job_id in self._jobs:
            raise KeyError(job_id)
        self._jobs[job_id] = record

    def get(self, job_id: str) -> JobRecord:
        return self._jobs[job_id]

    def remove(self, job_id: str) -> JobRecord | None:
        return self._jobs.pop(job_id, None)
```

- [ ] **Step 4: Implement the atomic job processor**

Create `app/services/job_processor.py`:

```python
from __future__ import annotations

import secrets
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from app.models import GroupPreview, JobPreview, JobState, ProcessingOptions
from app.services.classifier import classify_group
from app.services.output_builder import (
    allocate_output_names,
    build_processing_log,
    build_summary,
    build_verified_zip,
)
from app.services.pairing import build_pairs
from app.services.pdf_processor import build_sku_pdf, merge_pdfs
from app.services.registry import JobRecord, JobRegistry
from app.services.storage import JobPaths, JobStorage
from app.services.validation import collect_warnings, validate_group_counts, validate_labels
from app.services.zpl_parser import parse_wfs_zpl


@dataclass(frozen=True)
class UploadedGroup:
    group_index: int
    files: tuple[Path, ...]


@dataclass(frozen=True)
class JobResult:
    job_id: str
    archive: Path
    sku_pdf_names: tuple[str, ...]
    paths: JobPaths


def new_job_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{secrets.token_hex(2)}"


class JobProcessor:
    def __init__(self, storage: JobStorage, registry: JobRegistry):
        self.storage = storage
        self.registry = registry

    def validate(
        self,
        groups: tuple[UploadedGroup, ...],
        options: ProcessingOptions,
    ) -> JobPreview:
        if not groups:
            raise ValueError("at least one non-empty group is required")
        job_id = new_job_id()
        paths = self.storage.create(job_id)
        previews: list[GroupPreview] = []
        try:
            for uploaded in sorted(groups, key=lambda item: item.group_index):
                group_dir = paths.uploads / f"group_{uploaded.group_index}"
                group_dir.mkdir()
                stored: list[Path] = []
                for source in uploaded.files:
                    destination = group_dir / source.name
                    shutil.copyfile(source, destination)
                    stored.append(destination)
                files = classify_group(uploaded.group_index, stored)
                text = files.wfs_zpl_path.read_text(encoding="utf-8-sig")
                labels = parse_wfs_zpl(text, uploaded.group_index)
                validate_labels(uploaded.group_index, labels)
                _, logistics_pages = validate_group_counts(
                    uploaded.group_index,
                    files.wfs_pdf_path,
                    files.logistics_pdf_path,
                    labels,
                )
                pairs = build_pairs(uploaded.group_index, labels, logistics_pages)
                warnings = collect_warnings(uploaded.group_index, labels, logistics_pages)
                previews.append(GroupPreview(files, labels, pairs, warnings))
        except Exception:
            self.storage.cleanup(job_id)
            raise
        preview = JobPreview(
            job_id,
            tuple(previews),
            options,
            tuple(issue for group in previews for issue in group.issues),
        )
        self.registry.add(
            job_id,
            JobRecord(JobState.AWAITING_CONFIRMATION, preview, paths),
        )
        return preview

    def generate(self, job_id: str) -> JobResult:
        record = self.registry.get(job_id)
        if record.state is not JobState.AWAITING_CONFIRMATION:
            raise ValueError("job is not awaiting confirmation")
        record.state = JobState.GENERATING
        try:
            grouped_outputs: dict[str, list[tuple[int, Path]]] = defaultdict(list)
            all_pairs = record.preview.pairs
            names = allocate_output_names(tuple(dict.fromkeys(pair.sku for pair in all_pairs)))
            for group in record.preview.groups:
                pairs_by_sku: dict[str, list] = defaultdict(list)
                for pair in group.pairs:
                    pairs_by_sku[pair.sku].append(pair)
                for sku, pairs in pairs_by_sku.items():
                    temp = record.paths.intermediate / f"group_{group.files.group_index}_{names[sku]}"
                    build_sku_pdf(
                        tuple(pairs),
                        group.files.wfs_pdf_path,
                        group.files.logistics_pdf_path,
                        record.preview.options,
                        temp,
                    )
                    grouped_outputs[sku].append((group.files.group_index, temp))

            final_pdfs: list[Path] = []
            for sku, items in grouped_outputs.items():
                output = record.paths.output / names[sku]
                merge_pdfs(tuple(path for _, path in sorted(items)), output)
                final_pdfs.append(output)
            summary = record.paths.output / "summary.csv"
            log = record.paths.output / "processing_log.txt"
            archive = record.paths.output / "output.zip"
            build_summary(job_id, record.preview.groups, names, summary)
            log_lines = [f"job_id={job_id}", f"cleanup_scope={record.paths.root}"]
            for group in record.preview.groups:
                pallet_pages = [
                    label.pdf_page
                    for label in group.labels
                    if label.label_type.value == "pallet"
                ]
                log_lines.extend(
                    (
                        f"group={group.files.group_index} "
                        f"wfs={group.files.wfs_pdf_path.name} "
                        f"zpl={group.files.wfs_zpl_path.name} "
                        f"logistics={group.files.logistics_pdf_path.name}",
                        f"group={group.files.group_index} "
                        f"zpl_segments={len(group.labels)} boxes={len(group.pairs)} "
                        f"ignored_pallet_pages={pallet_pages}",
                    )
                )
                log_lines.extend(
                    f"warning rule={issue.rule} message={issue.message}"
                    for issue in group.issues
                )
            log_lines.extend(
                f"group={pair.group_index} box={pair.box_index} sku={pair.sku} "
                f"wfs_page={pair.wfs_pdf_page} logistics_page={pair.logistics_pdf_page}"
                for pair in all_pairs
            )
            for sku, path in zip(grouped_outputs, final_pdfs, strict=True):
                merge_groups = [group_index for group_index, _ in sorted(grouped_outputs[sku])]
                log_lines.append(
                    f"sku={sku} merge_groups={merge_groups} output={path.name} "
                    f"pages={len(PdfReader(path).pages)}"
                )
            build_processing_log(
                tuple(log_lines),
                log,
            )
            build_verified_zip(tuple(final_pdfs), summary, log, archive)
            self.storage.cleanup_inputs(job_id, archive)
        except Exception:
            record.state = JobState.GENERATION_FAILED
            raise
        record.state = JobState.READY_FOR_DOWNLOAD
        record.archive = archive
        record.completed_at = datetime.now(UTC)
        return JobResult(
            job_id,
            archive,
            tuple(path.name for path in final_pdfs),
            record.paths,
        )
```

- [ ] **Step 5: Run orchestration tests**

Run:

```bash
uv run pytest tests/integration/test_job_processor.py -v
uv run ruff check app/services/registry.py app/services/job_processor.py tests/integration/test_job_processor.py
```

Expected: four tests pass and Ruff passes.

- [ ] **Step 6: Commit**

```bash
git add app/services/registry.py app/services/job_processor.py tests/integration/test_job_processor.py
git commit -m "feat: orchestrate atomic label processing jobs"
```

## Task 10: Add FastAPI validation, generation, download, and invalidation endpoints

**Files:**
- Modify: `app/main.py`
- Create: `tests/conftest.py`
- Create: `tests/api/test_jobs_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(runtime_root=tmp_path / "jobs")))
```

Create `tests/api/test_jobs_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

SAMPLE = Path("tests/fixtures/sample")


def upload_payload() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "group_1",
            ("WFS Label-Sample.pdf", (SAMPLE / "WFS Label-Sample.pdf").read_bytes(), "application/pdf"),
        ),
        (
            "group_1",
            ("WFS Label-Sample.txt", (SAMPLE / "WFS Label-Sample.txt").read_bytes(), "text/plain"),
        ),
        (
            "group_1",
            (
                "Logistics Label-Sample.pdf",
                (SAMPLE / "Logistics Label-Sample.pdf").read_bytes(),
                "application/pdf",
            ),
        ),
    ]


def test_validate_generate_download_and_invalidate(client: TestClient) -> None:
    validated = client.post(
        "/api/jobs/validate",
        files=upload_payload(),
        data={"logistics_repeat": "1"},
    )
    assert validated.status_code == 200
    body = validated.json()
    assert body["ok"] is True
    assert len(body["preview"]["pairs"]) == 3

    generated = client.post(f"/api/jobs/{body['job_id']}/generate")
    assert generated.status_code == 200
    assert generated.json()["reset_uploads"] is True

    downloaded = client.get(generated.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"


def test_error_response_points_to_group_and_rule(client: TestClient) -> None:
    files = upload_payload()
    files[-1] = (
        "group_1",
        ("Logistics Label-Sample.pdf", b"broken", "application/pdf"),
    )

    response = client.post("/api/jobs/validate", files=files, data={"logistics_repeat": "1"})

    assert response.status_code == 422
    issue = response.json()["issues"][0]
    assert issue["group_index"] == 1
    assert issue["rule"] == "pdf_readable"


def test_delete_invalidates_validated_job(client: TestClient) -> None:
    validated = client.post(
        "/api/jobs/validate",
        files=upload_payload(),
        data={"logistics_repeat": "1"},
    ).json()

    deleted = client.delete(f"/api/jobs/{validated['job_id']}")

    assert deleted.json() == {"ok": True}
    assert client.post(f"/api/jobs/{validated['job_id']}/generate").status_code == 404
```

- [ ] **Step 2: Run API tests and verify route failures**

Run:

```bash
uv run pytest tests/api/test_jobs_api.py -v
```

Expected: tests fail because the job routes do not exist.

- [ ] **Step 3: Implement the API contract**

Replace `app/main.py` with:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings
from app.errors import ProcessingError
from app.models import ProcessingOptions
from app.services.job_processor import JobProcessor, UploadedGroup
from app.services.registry import JobRegistry
from app.services.storage import JobStorage


def _preview_dict(preview) -> dict:
    return {
        "pairs": [
            {
                "group_index": pair.group_index,
                "box_index": pair.box_index,
                "sku": pair.sku,
                "wfs_pdf_page": pair.wfs_pdf_page,
                "logistics_pdf_page": pair.logistics_pdf_page,
                "output_sequence": (
                    ["W"] * preview.options.wfs_repeat
                    + ["L"] * preview.options.logistics_repeat
                ),
            }
            for pair in preview.pairs
        ],
        "ignored_pallets": [
            {"group_index": group.files.group_index, "page": label.pdf_page}
            for group in preview.groups
            for label in group.labels
            if label.label_type.value == "pallet"
        ],
        "issues": [issue.as_dict() for issue in preview.issues],
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    registry = JobRegistry()
    storage = JobStorage(resolved.runtime_root)
    processor = JobProcessor(storage, registry)
    app = FastAPI(title="WFS LabelFlow")
    app.state.registry = registry
    app.state.storage = storage
    app.state.processor = processor

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/jobs/validate")
    async def validate_job(
        group_1: list[UploadFile] = File(default=[]),
        group_2: list[UploadFile] = File(default=[]),
        group_3: list[UploadFile] = File(default=[]),
        group_4: list[UploadFile] = File(default=[]),
        group_5: list[UploadFile] = File(default=[]),
        logistics_repeat: int = Form(default=1),
    ) -> dict:
        uploads = (group_1, group_2, group_3, group_4, group_5)
        with TemporaryDirectory() as temporary:
            incoming = Path(temporary)
            groups: list[UploadedGroup] = []
            for index, files in enumerate(uploads, start=1):
                if not files:
                    continue
                group_dir = incoming / f"group_{index}"
                group_dir.mkdir()
                paths: list[Path] = []
                for upload in files:
                    destination = group_dir / Path(upload.filename or "unnamed").name
                    with destination.open("wb") as handle:
                        shutil.copyfileobj(upload.file, handle)
                    paths.append(destination)
                groups.append(UploadedGroup(index, tuple(paths)))
            try:
                preview = processor.validate(
                    tuple(groups),
                    ProcessingOptions(logistics_repeat=logistics_repeat),
                )
            except (ProcessingError, ValueError) as exc:
                issues = getattr(exc, "issues", ())
                raise HTTPException(
                    status_code=422,
                    detail={"issues": [issue.as_dict() for issue in issues]},
                ) from exc
        return {"ok": True, "job_id": preview.job_id, "preview": _preview_dict(preview)}

    @app.post("/api/jobs/{job_id}/generate")
    def generate_job(job_id: str) -> dict:
        try:
            result = processor.generate(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except ProcessingError as exc:
            raise HTTPException(
                status_code=500,
                detail={"issues": [issue.as_dict() for issue in exc.issues]},
            ) from exc
        return {
            "ok": True,
            "reset_uploads": True,
            "download_url": f"/downloads/{job_id}",
        }

    @app.get("/downloads/{job_id}")
    def download(job_id: str) -> FileResponse:
        try:
            record = registry.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        if record.archive is None or not record.archive.is_file():
            raise HTTPException(status_code=404, detail="archive not ready")
        return FileResponse(record.archive, media_type="application/zip", filename="output.zip")

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, bool]:
        record = registry.remove(job_id)
        if record is not None:
            storage.cleanup(job_id)
        return {"ok": True}

    return app


app = create_app()
```

Update the HTTP error assertions in `tests/api/test_jobs_api.py` to unwrap FastAPI's `detail` envelope:

```python
issue = response.json()["detail"]["issues"][0]
```

- [ ] **Step 4: Run API tests**

Run:

```bash
uv run pytest tests/api/test_jobs_api.py -v
uv run ruff check app/main.py tests/conftest.py tests/api/test_jobs_api.py
```

Expected: three tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/conftest.py tests/api/test_jobs_api.py
git commit -m "feat: expose atomic label job API"
```

## Task 11: Build the five-group upload, read-only preview, and success-reset UI

**Files:**
- Create: `app/templates/index.html`
- Create: `app/static/app.js`
- Create: `app/static/styles.css`
- Modify: `app/main.py`
- Create: `tests/api/test_index.py`

- [ ] **Step 1: Write the failing page smoke test**

Create `tests/api/test_index.py`:

```python
from fastapi.testclient import TestClient


def test_index_has_five_groups_and_required_actions(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.text.count('class="group-panel"') == 5
    assert 'id="clear-all"' in response.text
    assert 'id="validate-button"' in response.text
    assert 'id="confirm-button"' in response.text
```

- [ ] **Step 2: Run the test and verify the missing page**

Run:

```bash
uv run pytest tests/api/test_index.py -v
```

Expected: test fails because `/` returns 404.

- [ ] **Step 3: Create the complete server-rendered shell**

Create `app/templates/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>WFS LabelFlow</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <main>
      <header>
        <div>
          <p class="eyebrow">本机处理 · 文件不外传</p>
          <h1>WFS LabelFlow</h1>
          <p>先校验逐箱关系，再确认生成标签。</p>
        </div>
        <button id="clear-all" class="danger" type="button">清空全部上传</button>
      </header>

      <section id="error-summary" class="notice error" hidden aria-live="assertive"></section>

      <form id="upload-form">
        <section class="workspace">
          <div id="groups">
            {% for group in range(1, 6) %}
            <article class="group-panel" data-group="{{ group }}">
              <div class="group-heading">
                <h2>第 {{ group }} 组</h2>
                <button class="clear-group ghost" type="button">清空本组</button>
              </div>
              <label class="dropzone">
                <span>拖入或选择 WFS PDF、ZPL/TXT、货代 PDF</span>
                <input name="group_{{ group }}" type="file" multiple accept=".pdf,.txt,.zpl">
              </label>
              <ul class="file-list"></ul>
              <div class="group-error notice error" hidden></div>
            </article>
            {% endfor %}
          </div>

          <aside>
            <h2>处理选项</h2>
            <p><strong>WFS 标签：</strong>固定 2 份</p>
            <fieldset>
              <legend>货代标签份数</legend>
              <label><input type="radio" name="logistics_repeat" value="1" checked> 1 份</label>
              <label><input type="radio" name="logistics_repeat" value="2"> 2 份</label>
            </fieldset>
            <p>✓ 忽略 Pallet Label</p>
            <p>✓ 跨组合并相同 SKU</p>
            <p>✓ 输出 summary.csv</p>
            <button id="validate-button" type="submit">校验并预览</button>
          </aside>
        </section>
      </form>

      <section id="preview" hidden>
        <div class="notice success"><strong>强校验通过</strong>，请确认逐箱映射。</div>
        <table>
          <thead>
            <tr><th>组</th><th>箱序</th><th>WFS 页</th><th>SKU</th><th>货代页</th><th>输出顺序</th></tr>
          </thead>
          <tbody id="preview-rows"></tbody>
        </table>
        <div class="actions">
          <button id="back-button" class="ghost" type="button">返回重新上传</button>
          <button id="confirm-button" type="button">确认并生成 ZIP</button>
        </div>
      </section>

      <section id="result" hidden aria-live="polite">
        <div class="notice success">
          <strong>ZIP 已成功生成。</strong>
          本轮上传和预览已清空，下一轮可安全开始。
        </div>
        <a id="download-link" class="button" href="#">下载 ZIP</a>
      </section>
    </main>
    <script src="/static/app.js" defer></script>
  </body>
</html>
```

- [ ] **Step 4: Implement browser file deletion, validation, invalidation, and reset**

Create `app/static/app.js`:

```javascript
const form = document.querySelector("#upload-form");
const preview = document.querySelector("#preview");
const result = document.querySelector("#result");
const errorSummary = document.querySelector("#error-summary");
const previewRows = document.querySelector("#preview-rows");
const confirmButton = document.querySelector("#confirm-button");
const backButton = document.querySelector("#back-button");
const downloadLink = document.querySelector("#download-link");
let activeJobId = null;

function listFiles(panel) {
  const input = panel.querySelector('input[type="file"]');
  const list = panel.querySelector(".file-list");
  list.replaceChildren();
  [...input.files].forEach((file, index) => {
    const item = document.createElement("li");
    item.append(document.createTextNode(file.name));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-file ghost";
    remove.textContent = "删除";
    remove.addEventListener("click", () => removeFile(input, index));
    item.append(remove);
    list.append(item);
  });
}

async function invalidatePreview() {
  if (activeJobId) {
    await fetch(`/api/jobs/${activeJobId}`, { method: "DELETE" });
  }
  activeJobId = null;
  preview.hidden = true;
  previewRows.replaceChildren();
}

function removeFile(input, removedIndex) {
  const transfer = new DataTransfer();
  [...input.files].forEach((file, index) => {
    if (index !== removedIndex) transfer.items.add(file);
  });
  input.files = transfer.files;
  listFiles(input.closest(".group-panel"));
  invalidatePreview();
}

function clearErrors() {
  errorSummary.hidden = true;
  errorSummary.replaceChildren();
  document.querySelectorAll(".group-error").forEach((element) => {
    element.hidden = true;
    element.replaceChildren();
  });
}

function showIssues(issues) {
  clearErrors();
  errorSummary.hidden = false;
  errorSummary.textContent = "校验未通过，请按组修正以下问题。";
  issues.forEach((issue) => {
    const target = issue.group_index
      ? document.querySelector(`[data-group="${issue.group_index}"] .group-error`)
      : errorSummary;
    target.hidden = false;
    const line = document.createElement("p");
    line.textContent = `${issue.message}。期望：${issue.expected ?? "-"}；实际：${issue.actual ?? "-"}。${issue.repair}`;
    target.append(line);
  });
}

function clearPanelFiles(panel) {
  panel.querySelector('input[type="file"]').value = "";
  listFiles(panel);
  panel.querySelector(".group-error").hidden = true;
}

async function discardAndClearAll() {
  await invalidatePreview();
  document.querySelectorAll(".group-panel").forEach(clearPanelFiles);
  form.reset();
  preview.hidden = true;
  result.hidden = true;
  previewRows.replaceChildren();
  clearErrors();
}

function resetInputsAfterSuccess() {
  document.querySelectorAll(".group-panel").forEach(clearPanelFiles);
  form.reset();
  activeJobId = null;
  preview.hidden = true;
  previewRows.replaceChildren();
  clearErrors();
}

document.querySelectorAll('.group-panel input[type="file"]').forEach((input) => {
  input.addEventListener("change", () => {
    listFiles(input.closest(".group-panel"));
    invalidatePreview();
  });
});

document.querySelectorAll(".clear-group").forEach((button) => {
  button.addEventListener("click", async () => {
    await invalidatePreview();
    clearPanelFiles(button.closest(".group-panel"));
  });
});

document.querySelector("#clear-all").addEventListener("click", discardAndClearAll);
backButton.addEventListener("click", () => {
  preview.hidden = true;
  form.hidden = false;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await invalidatePreview();
  clearErrors();
  const response = await fetch("/api/jobs/validate", {
    method: "POST",
    body: new FormData(form),
  });
  const body = await response.json();
  if (!response.ok) {
    showIssues(body.detail?.issues ?? []);
    return;
  }
  activeJobId = body.job_id;
  previewRows.replaceChildren(
    ...body.preview.pairs.map((pair) => {
      const row = document.createElement("tr");
      [pair.group_index, pair.box_index, pair.wfs_pdf_page, pair.sku, pair.logistics_pdf_page, pair.output_sequence.join(" ")].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      return row;
    }),
  );
  form.hidden = true;
  preview.hidden = false;
  result.hidden = true;
});

confirmButton.addEventListener("click", async () => {
  const response = await fetch(`/api/jobs/${activeJobId}/generate`, { method: "POST" });
  const body = await response.json();
  if (!response.ok) {
    showIssues(body.detail?.issues ?? []);
    form.hidden = false;
    preview.hidden = true;
    return;
  }
  const url = body.download_url;
  resetInputsAfterSuccess();
  form.hidden = false;
  result.hidden = false;
  downloadLink.href = url;
});
```

- [ ] **Step 5: Add focused styling**

Create `app/static/styles.css`:

```css
:root {
  color: #1d2939;
  background: #f7f9fc;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; }
main { width: min(1180px, 94vw); margin: 40px auto; }
header, .group-heading, .actions { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.eyebrow { color: #16794b; font-weight: 700; }
.workspace { display: grid; grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr); gap: 24px; }
.group-panel, aside, #preview, #result { background: white; border: 1px solid #d0d5dd; border-radius: 12px; padding: 18px; margin-bottom: 14px; }
.dropzone { display: block; border: 2px dashed #98a2b3; border-radius: 8px; padding: 24px; cursor: pointer; }
.dropzone input { display: block; margin-top: 12px; width: 100%; }
.file-list { list-style: none; padding: 0; }
.file-list li { display: flex; justify-content: space-between; background: #f2f4f7; margin-top: 8px; padding: 8px; border-radius: 6px; }
button, .button { border: 0; border-radius: 7px; background: #16794b; color: white; padding: 10px 14px; cursor: pointer; text-decoration: none; }
.ghost { background: #667085; }
.danger { background: #b42318; }
.notice { border-radius: 8px; padding: 12px; margin: 12px 0; }
.error { background: #fef3f2; color: #b42318; }
.success { background: #ecfdf3; color: #067647; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; border-bottom: 1px solid #eaecf0; padding: 10px; }
.actions { justify-content: flex-end; margin-top: 18px; }
@media (max-width: 760px) {
  .workspace { grid-template-columns: 1fr; }
  header { align-items: flex-start; flex-direction: column; }
}
```

- [ ] **Step 6: Mount assets and render the index**

Add these imports to `app/main.py`:

```python
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
```

Inside `create_app`, after constructing `app`, add:

```python
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")
```

- [ ] **Step 7: Run UI smoke tests and full suite**

Run:

```bash
uv run pytest tests/api/test_index.py tests/api/test_jobs_api.py -v
uv run pytest
uv run ruff check app tests
```

Expected: all tests pass and Ruff passes.

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/templates app/static tests/api/test_index.py
git commit -m "feat: add five-group validation and preview UI"
```

## Task 12: Add browser tests for deletion, precise errors, and successful reset

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/browser/test_production_flow.py`

- [ ] **Step 1: Add Playwright test dependency**

Run:

```bash
uv add --dev playwright pytest-playwright
uv run playwright install chromium
```

Expected: lock file updates and Chromium installation succeeds.

- [ ] **Step 2: Write the browser acceptance tests**

Create `tests/browser/test_production_flow.py`:

```python
from pathlib import Path

from playwright.sync_api import Page, expect

SAMPLE = Path("tests/fixtures/sample").resolve()


def sample_paths() -> list[str]:
    return [
        str(SAMPLE / "WFS Label-Sample.pdf"),
        str(SAMPLE / "WFS Label-Sample.txt"),
        str(SAMPLE / "Logistics Label-Sample.pdf"),
    ]


def test_remove_file_and_clear_group(page: Page, live_server_url: str) -> None:
    page.goto(live_server_url)
    picker = page.locator('[name="group_1"]')
    picker.set_input_files(sample_paths())
    expect(page.locator('[data-group="1"] .file-list li')).to_have_count(3)

    page.locator('[data-group="1"] .remove-file').first.click()
    expect(page.locator('[data-group="1"] .file-list li')).to_have_count(2)

    page.locator('[data-group="1"] .clear-group').click()
    expect(page.locator('[data-group="1"] .file-list li')).to_have_count(0)


def test_validation_error_stays_in_exact_group(page: Page, live_server_url: str, tmp_path: Path) -> None:
    broken = tmp_path / "Logistics Label-Sample.pdf"
    broken.write_bytes(b"broken")
    page.goto(live_server_url)
    page.locator('[name="group_2"]').set_input_files(
        [
            str(SAMPLE / "WFS Label-Sample.pdf"),
            str(SAMPLE / "WFS Label-Sample.txt"),
            str(broken),
        ]
    )

    page.locator("#validate-button").click()

    error = page.locator('[data-group="2"] .group-error')
    expect(error).to_be_visible()
    expect(error).to_contain_text("第 2 组")
    expect(page.locator('[data-group="1"] .group-error')).to_be_hidden()


def test_success_clears_all_five_groups_and_keeps_download(page: Page, live_server_url: str) -> None:
    page.goto(live_server_url)
    page.locator('[name="group_1"]').set_input_files(sample_paths())
    page.locator("#validate-button").click()
    expect(page.locator("#preview")).to_be_visible()

    page.locator("#confirm-button").click()

    expect(page.locator("#result")).to_be_visible()
    expect(page.locator("#download-link")).to_have_attribute("href", re.compile(r"^/downloads/"))
    for index in range(1, 6):
        expect(page.locator(f'[data-group="{index}"] .file-list li')).to_have_count(0)
        assert page.locator(f'[name="group_{index}"]').input_value() == ""
    expect(page.locator('[name="logistics_repeat"][value="1"]')).to_be_checked()
    with page.expect_download() as download_info:
        page.locator("#download-link").click()
    assert download_info.value.suggested_filename == "output.zip"
```

Add the missing import at the top:

```python
import re
```

- [ ] **Step 3: Provide a live-server fixture**

Append to `tests/conftest.py`:

```python
import socket
import threading

import uvicorn


@pytest.fixture
def live_server_url(tmp_path: Path) -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(
        create_app(Settings(runtime_root=tmp_path / "browser-jobs")),
        host="127.0.0.1",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
```

- [ ] **Step 4: Run browser tests and observe any real UI failures**

Run:

```bash
uv run pytest tests/browser/test_production_flow.py -v
```

Expected: three browser tests pass. If a test fails, use `superpowers:systematic-debugging`; do not loosen the acceptance assertion.

- [ ] **Step 5: Run full verification**

Run:

```bash
uv run pytest
uv run ruff check app tests
```

Expected: all tests pass and Ruff passes.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock tests/conftest.py tests/browser/test_production_flow.py
git commit -m "test: verify label correction and reset workflow"
```

## Task 13: Add retention cleanup and stale-job invalidation

**Files:**
- Modify: `app/services/registry.py`
- Modify: `app/main.py`
- Create: `tests/api/test_retention.py`

- [ ] **Step 1: Write failing retention test**

Create `tests/api/test_retention.py`:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import JobPreview, JobState, ProcessingOptions
from app.services.registry import JobRecord, JobRegistry
from app.services.storage import JobStorage


def test_registry_expiration_removes_only_expired_completed_job(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path)
    registry = JobRegistry()
    old_id = "20260704_080000_ab12"
    fresh_id = "20260704_083000_cd34"
    for job_id in (old_id, fresh_id):
        paths = storage.create(job_id)
        archive = paths.output / "output.zip"
        archive.write_bytes(b"zip")
        preview = JobPreview(job_id, (), ProcessingOptions())
        registry.add(job_id, JobRecord(JobState.READY_FOR_DOWNLOAD, preview, paths, archive))
    registry.get(old_id).completed_at = datetime.now(UTC) - timedelta(minutes=31)
    registry.get(fresh_id).completed_at = datetime.now(UTC)

    expired = registry.expire(storage, timedelta(minutes=30), datetime.now(UTC))

    assert expired == (old_id,)
    assert not storage.paths(old_id).root.exists()
    assert storage.paths(fresh_id).root.exists()
```

- [ ] **Step 2: Run test and verify missing method**

Run:

```bash
uv run pytest tests/api/test_retention.py -v
```

Expected: test fails because `JobRegistry.expire` does not exist.

- [ ] **Step 3: Implement explicit expiration**

Add to `JobRegistry` in `app/services/registry.py`:

```python
def expire(
    self,
    storage,
    retention,
    now,
) -> tuple[str, ...]:
    completed = {
        job_id: record.completed_at
        for job_id, record in self._jobs.items()
        if record.completed_at is not None
    }
    expired = storage.cleanup_expired(completed, retention, now)
    for job_id in expired:
        record = self._jobs.pop(job_id)
        record.state = JobState.EXPIRED
    return expired
```

Add a maintenance endpoint inside `create_app` in `app/main.py`:

```python
@app.post("/api/maintenance/expire")
def expire_results() -> dict[str, list[str]]:
    expired = registry.expire(storage, resolved.zip_retention, datetime.now(UTC))
    return {"expired_job_ids": list(expired)}
```

Add these imports to `app/main.py`:

```python
from datetime import UTC, datetime
```

- [ ] **Step 4: Run retention and full tests**

Run:

```bash
uv run pytest tests/api/test_retention.py -v
uv run pytest
uv run ruff check app tests
```

Expected: all tests pass and Ruff passes.

- [ ] **Step 5: Commit**

```bash
git add app/services/registry.py app/main.py tests/api/test_retention.py
git commit -m "feat: expire completed label archives safely"
```

## Task 14: Inspect sample PDFs, render generated output, and document operation

**Files:**
- Create: `scripts/inspect_sample.py`
- Create: `README.md`
- Modify: `AGENTS.md`
- Modify: `STATE.md`

- [ ] **Step 1: Add a reproducible sample inspection script**

Create `scripts/inspect_sample.py`:

```python
from pathlib import Path

from pypdf import PdfReader

from app.models import ProcessingOptions
from app.services.job_processor import JobProcessor, UploadedGroup
from app.services.registry import JobRegistry
from app.services.storage import JobStorage
from app.services.zpl_parser import parse_wfs_zpl

SAMPLE = Path("tests/fixtures/sample")


def main() -> None:
    wfs = SAMPLE / "WFS Label-Sample.pdf"
    logistics = SAMPLE / "Logistics Label-Sample.pdf"
    zpl = SAMPLE / "WFS Label-Sample.txt"
    labels = parse_wfs_zpl(zpl.read_text(encoding="utf-8"), 1)
    print(
        {
            "wfs_pages": len(PdfReader(wfs).pages),
            "logistics_pages": len(PdfReader(logistics).pages),
            "zpl_segments": len(labels),
            "label_types": [label.label_type.value for label in labels],
            "skus": [label.sku for label in labels if label.sku],
        }
    )
    processor = JobProcessor(
        JobStorage(Path("/tmp/wfs-labelflow-qa/jobs")),
        JobRegistry(),
    )
    preview = processor.validate(
        (
            UploadedGroup(
                1,
                (
                    wfs,
                    zpl,
                    logistics,
                ),
            ),
        ),
        ProcessingOptions(logistics_repeat=1),
    )
    result = processor.generate(preview.job_id)
    print({"verified_archive": str(result.archive)})


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the sample through the actual processor**

Run:

```bash
uv run python scripts/inspect_sample.py
uv run pytest tests/integration/test_job_processor.py -v
```

Expected: inspection reports 4 WFS pages, 3 logistics pages, 4 ZPL segments, and label types `box, box, box, pallet`; integration tests pass.

- [ ] **Step 3: Render input and generated PDFs for visual inspection**

Run:

```bash
mkdir -p /tmp/wfs-labelflow-render
pdftoppm -png -r 150 "tests/fixtures/sample/WFS Label-Sample.pdf" "/tmp/wfs-labelflow-render/wfs"
pdftoppm -png -r 150 "tests/fixtures/sample/Logistics Label-Sample.pdf" "/tmp/wfs-labelflow-render/logistics"
archive="$(find /tmp/wfs-labelflow-qa/jobs -name output.zip -print | tail -1)"
unzip -o "$archive" -d /tmp/wfs-labelflow-render/generated
for pdf in /tmp/wfs-labelflow-render/generated/*.pdf; do
  name="$(basename "$pdf" .pdf)"
  pdftoppm -png -r 150 "$pdf" "/tmp/wfs-labelflow-render/generated-$name"
done
```

If `pdftoppm` is unavailable, install Poppler with explicit user approval, then rerun. Inspect every rendered input page and at least one generated SKU PDF using the image viewer. Confirm no clipping, corruption, rotation change, blank replacement, or unexpected page-size change. Record filenames and page counts in `STATE.md`.

- [ ] **Step 4: Write local operating instructions**

Create `README.md`:

```markdown
# WFS LabelFlow

Local single-user tool for validating and assembling WFS and logistics labels.

## Start

```sh
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8790
```

Open `http://127.0.0.1:8790`.

## Production workflow

1. Add up to five groups; each non-empty group needs one WFS PDF, one WFS
   ZPL/TXT, and one logistics PDF.
2. Delete an individual file, clear a group, or clear all before validation.
3. Select one or two logistics copies and choose **Validate and preview**.
4. Correct every group-specific error. Never override a page mapping.
5. Review the read-only box mapping and confirm generation.
6. Download the ZIP. Successful generation clears every upload control before
   the next production round.

## Verification

```sh
uv run pytest
uv run ruff check app tests
uv run python scripts/inspect_sample.py
```

Runtime jobs live under `data/jobs/<job_id>/`. Cleanup is always scoped to one
validated job ID. Completed ZIPs expire after 30 minutes.
```

- [ ] **Step 5: Update project recovery documents last**

In `AGENTS.md`, replace the documentation-only verification section with:

```markdown
## Verification

```sh
uv run pytest
uv run ruff check app tests
uv run python scripts/inspect_sample.py
```
```

Update `STATE.md` last with:

- the exact test count and command output;
- rendered PDF inspection result and paths inspected;
- current phase `MVP implemented and awaiting product-owner acceptance`;
- remaining unknown filename classification rules;
- the next action `Run a user acceptance production round with representative real filenames`.

- [ ] **Step 6: Run final verification**

Run:

```bash
uv run pytest
uv run ruff check app tests
uv run python scripts/inspect_sample.py
git diff --check
git status --short
```

Expected: all tests pass, Ruff passes, sample counts are correct, no whitespace errors exist, and status lists only intended README/script/recovery-document changes.

- [ ] **Step 7: Commit**

```bash
git add scripts/inspect_sample.py README.md AGENTS.md STATE.md
git commit -m "docs: verify and document local production workflow"
```

## Final acceptance checkpoint

- [ ] Confirm every task commit exists in order with `git log --oneline --reverse master..HEAD`.
- [ ] Run `uv run pytest` and record the exact passing count.
- [ ] Run `uv run ruff check app tests` and record `All checks passed!`.
- [ ] Confirm browser tests prove file deletion, group clearing, precise error placement, immutable preview, successful ZIP download, and full five-group reset.
- [ ] Confirm a non-final pallet fixture maps the next effective WFS box to the next logistics page.
- [ ] Confirm output PDF page counts obey `box_count × (2 + logistics_repeat)`.
- [ ] Confirm ZIP read-back includes at least one SKU PDF, `summary.csv`, and `processing_log.txt`.
- [ ] Confirm successful cleanup leaves only the current ZIP and expiration removes only that `job_id`.
- [ ] Confirm rendered sample input and generated output pages have no visual defects.
- [ ] Keep production filename classification marked unresolved until real filenames and deterministic rules are approved.
