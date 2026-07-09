# WFS ZIP + Excel Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old multi-upload WFS workflow with a single ZIP upload plus one Excel mapping file that validates WFS PDF/TXT completeness, dispatches carrier labels by Excel relation, fails atomically on any strong error, and clears all job-scoped uploads after successful ZIP generation.

**Architecture:** Keep the current FastAPI app and server-rendered UI, but split the new flow into three focused services: ZIP ingestion/indexing, Excel mapping parsing, and dispatch validation. The job processor will orchestrate those services, build the verified output ZIP only after all strong checks pass, and keep cleanup scoped to the current job id.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, vanilla browser JS, openpyxl for Excel parsing, zipfile/pathlib/shutil for ingest and cleanup, pytest for unit/integration/browser coverage.

---

### Task 1: Add ZIP and Excel ingestion primitives

**Files:**
- Create: `app/services/archive_ingest.py`
- Create: `app/services/excel_mapping.py`
- Modify: `app/models.py`
- Modify: `tests/unit/test_archive_ingest.py`
- Modify: `tests/unit/test_excel_mapping.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
import zipfile

import pytest
from openpyxl import Workbook

from app.errors import ProcessingError
from app.services.archive_ingest import parse_zip_archive
from app.services.excel_mapping import read_excel_mapping


def test_archive_ingest_rejects_duplicate_basenames(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("123.pdf", b"one")
        zipped.writestr("nested/123.pdf", b"two")

    with pytest.raises(ProcessingError):
        parse_zip_archive(archive)


def test_excel_mapping_reads_first_sheet_and_expected_headers(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["货代单号", "WFS Shipment ID"])
    sheet.append(["CD2606260718", "9233758WFA"])
    sample = tmp_path / "mapping.xlsx"
    workbook.save(sample)

    rows = read_excel_mapping(sample)

    assert rows[0].carrier_number == "CD2606260718"
    assert rows[0].shipment_id == "9233758WFA"
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
pytest tests/unit/test_archive_ingest.py tests/unit/test_excel_mapping.py -v
```

Expected: the tests fail because the new ingestion helpers do not exist yet.

- [ ] **Step 3: Implement the minimal ingestion layer**

Create small immutable records in `app/models.py` for:

- uploaded ZIP members;
- Excel mapping rows;
- parsed dispatch inputs; and
- structured validation issues for missing headers, duplicate basenames, and unreadable spreadsheets.

Implement `app/services/archive_ingest.py` with:

- a public `parse_zip_archive(path: Path) -> ArchiveInventory` helper;
- extraction into a job-scoped temporary directory;
- indexing by basename without extension;
- duplicate-basename rejection;
- unsupported-extension rejection; and
- typed return values instead of raw paths.

Implement `app/services/excel_mapping.py` with:

- a public `read_excel_mapping(path: Path) -> tuple[CarrierMappingRow, ...]` helper;
- first-sheet loading through `openpyxl`;
- exact header checks for `货代单号` and `WFS Shipment ID`;
- one record per non-empty mapping row; and
- row-number preservation in validation errors so the UI can point at the bad row.

- [ ] **Step 4: Re-run the focused tests until they pass**

Run:

```bash
pytest tests/unit/test_archive_ingest.py tests/unit/test_excel_mapping.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/services/archive_ingest.py app/services/excel_mapping.py tests/unit/test_archive_ingest.py tests/unit/test_excel_mapping.py
git commit -m "feat: add ZIP and Excel ingestion helpers"
```

### Task 2: Implement carrier dispatch and all-or-nothing validation

**Files:**
- Create: `app/services/dispatch.py`
- Modify: `app/services/job_processor.py`
- Modify: `app/services/output_builder.py`
- Modify: `app/errors.py`
- Modify: `tests/unit/test_dispatch.py`
- Modify: `tests/integration/test_job_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path
import zipfile

import pytest

from app.errors import ProcessingError
from app.models import CarrierMappingRow
from app.services.archive_ingest import parse_zip_archive
from app.services.dispatch import build_dispatch_plan


def test_one_carrier_number_can_cover_many_wfs_ids(tmp_path: Path) -> None:
    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("9233758WFA.txt", b"txt")
        zipped.writestr("CD2606260718.pdf", b"carrier")

    inventory = parse_zip_archive(archive)
    mappings = (
        CarrierMappingRow(row_number=2, carrier_number="CD2606260718", shipment_id="9233758WFA"),
        CarrierMappingRow(row_number=3, carrier_number="CD2606260718", shipment_id="9233758WFA"),
    )

    plan = build_dispatch_plan(inventory, mappings)

    assert plan.issues == ()
    assert plan.assignments["9233758WFA"].carrier_number == "CD2606260718"


def test_carrier_label_cannot_be_bound_to_two_carrier_numbers(tmp_path: Path) -> None:
    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("9233758WFA.txt", b"txt")
        zipped.writestr("CD2606260718.pdf", b"carrier")

    inventory = parse_zip_archive(archive)
    mappings = (
        CarrierMappingRow(row_number=2, carrier_number="CD2606260718", shipment_id="9233758WFA"),
        CarrierMappingRow(row_number=3, carrier_number="CD2606260718-ALT", shipment_id="9233758WFA"),
    )

    with pytest.raises(ProcessingError):
        build_dispatch_plan(inventory, mappings)


def test_wfs_pdf_and_txt_must_both_exist(tmp_path: Path) -> None:
    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("CD2606260718.pdf", b"carrier")

    inventory = parse_zip_archive(archive)
    mappings = (
        CarrierMappingRow(row_number=2, carrier_number="CD2606260718", shipment_id="9233758WFA"),
    )

    with pytest.raises(ProcessingError):
        build_dispatch_plan(inventory, mappings)
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
pytest tests/unit/test_dispatch.py tests/integration/test_job_processor.py -v
```

Expected: failures show the dispatch engine is still missing.

- [ ] **Step 3: Implement the dispatch engine**

Add `app/services/dispatch.py` with a single responsibility: turn parsed ZIP members plus Excel rows into a dispatch plan and a list of strong validation issues.

Use a public entry point with this signature:

```python
build_dispatch_plan(
    inventory: ArchiveInventory,
    mappings: tuple[CarrierMappingRow, ...],
) -> DispatchPlan
```

Enforce these rules in code:

- each WFS shipment must have exactly one PDF and one TXT;
- one Excel carrier number may point at multiple WFS shipment IDs;
- the same carrier label PDF cannot be assigned to a second carrier number; and
- any unresolved Excel row, missing file pair, or leftover carrier PDF is a strong failure.

Update `app/services/job_processor.py` to call the new ingestion + dispatch pipeline before any output is written. Keep the existing job lifecycle (`awaiting_confirmation`, `generating`, `ready_for_download`) but make validation atomic: if any strong issue is present, do not persist a preview and do not build a partial ZIP.

Update `app/services/output_builder.py` only as needed to write the final verified ZIP from an approved dispatch result. Do not let output code re-run business validation.

- [ ] **Step 4: Re-run the focused tests until they pass**

Run:

```bash
pytest tests/unit/test_dispatch.py tests/integration/test_job_processor.py -v
```

Expected: the dispatch and job processor tests pass, including the no-partial-output case.

- [ ] **Step 5: Commit**

```bash
git add app/services/dispatch.py app/services/job_processor.py app/services/output_builder.py app/errors.py tests/unit/test_dispatch.py tests/integration/test_job_processor.py
git commit -m "feat: add ZIP and Excel dispatch validation"
```

### Task 3: Switch the HTTP layer and browser UI to the new upload model

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Modify: `tests/api/test_jobs_api.py`
- Modify: `tests/browser/test_production_flow.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from playwright.sync_api import Page, expect
import zipfile


def test_validate_job_requires_zip_and_excel(client: TestClient) -> None:
    response = client.post("/api/jobs/validate", files=[])

    assert response.status_code == 422
    assert response.json()["detail"]["issues"][0]["rule"] == "validation_error"


def test_browser_flow_clears_uploads_after_success(
    page: Page,
    live_server_url: str,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "labels.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", b"pdf")
        zipped.writestr("9233758WFA.txt", b"txt")
        zipped.writestr("CD2606260718.pdf", b"carrier")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["货代单号", "WFS Shipment ID"])
    sheet.append(["CD2606260718", "9233758WFA"])
    sample_xlsx = tmp_path / "mapping.xlsx"
    workbook.save(sample_xlsx)

    page.goto(live_server_url)
    page.locator('[name="label_zip"]').set_input_files(str(archive))
    page.locator('[name="mapping_xlsx"]').set_input_files(str(sample_xlsx))
    page.locator("#validate-button").click()
    page.locator("#confirm-button").click()

    expect(page.locator('[name="label_zip"]')).to_have_value("")
    expect(page.locator('[name="mapping_xlsx"]')).to_have_value("")
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
pytest tests/api/test_jobs_api.py tests/browser/test_production_flow.py -v
```

Expected: the old UI and old multipart payload shape no longer match the tests.

- [ ] **Step 3: Rework the request handling and page markup**

Change `app/main.py` so `/api/jobs/validate` accepts:

- one ZIP upload field named `label_zip`; and
- one Excel upload field named `mapping_xlsx`.

Return preview payloads that describe the new dispatch plan, not the old five-group pairing model.

Change `app/templates/index.html` and `app/static/app.js` so the browser exposes:

- one ZIP picker;
- one Excel picker;
- a validation preview panel;
- a confirm/generate button; and
- an error area that can identify the exact file or Excel row.

Keep the reset behavior explicit: after a successful generation response, clear both file inputs and any cached file list in the DOM.

- [ ] **Step 4: Re-run the API and browser tests until they pass**

Run:

```bash
pytest tests/api/test_jobs_api.py tests/browser/test_production_flow.py -v
```

Expected: the new request shape, preview rendering, and reset behavior all pass.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/templates/index.html app/static/app.js app/static/styles.css tests/api/test_jobs_api.py tests/browser/test_production_flow.py
git commit -m "feat: switch UI to ZIP and Excel uploads"
```

### Task 4: Refresh sample fixtures, docs, and end-to-end verification

**Files:**
- Create: `tests/fixtures/sample/对照关系表.xlsx`
- Modify: `tests/conftest.py`
- Modify: `tests/integration/test_job_processor.py`
- Modify: `tests/browser/test_production_flow.py`
- Modify: `README.md`
- Modify: `STATE.md`

- [ ] **Step 1: Write the failing acceptance tests**

```python
from pathlib import Path
import zipfile

from app.models import JobState
from app.services.job_processor import JobProcessor
from app.services.registry import JobRegistry
from app.services.storage import JobStorage


def test_sample_zip_and_excel_produce_verified_output(tmp_path: Path) -> None:
    sample_zip = tmp_path / "sample.zip"
    with zipfile.ZipFile(sample_zip, "w") as zipped:
        zipped.writestr("9233758WFA.pdf", Path("tests/fixtures/sample/WFS Label-Sample.pdf").read_bytes())
        zipped.writestr("9233758WFA.txt", Path("tests/fixtures/sample/WFS Label-Sample.txt").read_bytes())
        zipped.writestr("CD2606260718.pdf", Path("tests/fixtures/sample/Logistics Label-Sample.pdf").read_bytes())

    sample_xlsx = Path("tests/fixtures/sample/对照关系表.xlsx")
    registry = JobRegistry()
    processor = JobProcessor(JobStorage(tmp_path / "jobs"), registry)
    preview = processor.validate(sample_zip, sample_xlsx)
    result = processor.generate(preview.job_id)

    assert registry.get(preview.job_id).state is JobState.READY_FOR_DOWNLOAD
    assert result.archive.is_file()
    assert not result.paths.uploads.exists()
```

- [ ] **Step 2: Run the acceptance test and confirm it fails before the fixture is added**

Run:

```bash
pytest tests/integration/test_job_processor.py tests/browser/test_production_flow.py -v
```

Expected: the new acceptance path still lacks the shared sample Excel fixture or the new assertions.

- [ ] **Step 3: Add the sample Excel fixture and refresh docs**

Copy the provided sample Excel into `tests/fixtures/sample/对照关系表.xlsx` so the test suite can run without depending on the external sample folder.

Use `Sample Label/对照关系表.xlsx` as the source copy when creating the fixture.

Update `README.md` with the new quick-start path for the ZIP + Excel workflow and the local launch instructions that still mention `start.command`, `start.bat`, and port `8790`.

Update `STATE.md` last, after the tests pass, so the recovery instructions reflect the new validated flow and the next action is the current implementation state rather than the older provisional filename-rule note.

- [ ] **Step 4: Re-run the full verification set**

Run:

```bash
pytest
ruff check app tests
python scripts/inspect_sample.py
git diff --check
```

Expected: the suite passes, the sample inspection succeeds, and there are no whitespace or patch-format problems.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/sample/对照关系表.xlsx tests/conftest.py tests/integration/test_job_processor.py tests/browser/test_production_flow.py README.md STATE.md
git commit -m "docs: refresh ZIP and Excel dispatch workflow"
```
