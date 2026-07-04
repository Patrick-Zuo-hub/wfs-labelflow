# WFS LabelFlow MVP design

- Date: 2026-07-04
- Status: Approved in collaborative design review
- Audience: Product owner and implementers
- Maintenance owner: Project implementer, with business-rule changes approved
  by the product owner
- Authoritative business source:
  `../../../wfs_label_processing_requirements.md`

## 1. Objective

Create a local, single-user browser application that accepts up to five
independent groups of WFS label inputs, validates their page-level
relationships, displays a read-only box-pair preview, and produces one PDF per
SKU inside a ZIP.

The design succeeds when:

- ZPL/TXT determines WFS page type and SKU metadata.
- Every effective WFS box page is paired exactly once with the logistics page
  at the same effective-box position.
- Pallet pages consume no logistics page and appear in no SKU output.
- In-group page order and cross-group upload-window order are preserved.
- Strong validation prevents all partial or ambiguous output.
- Successful generation clears the completed round's uploads and intermediate
  state before another round can begin.

## 2. Scope

### Included in the MVP

- Local, single-user web application.
- Five upload windows, each accepting a set of three files.
- Empty windows skipped; partially populated windows rejected.
- ZPL/TXT segmentation and metadata parsing.
- WFS and logistics PDF page inspection and page-level output.
- Twelve mandatory strong validations from the requirements.
- Read-only pre-generation preview.
- Fixed WFS repeat count of two.
- Logistics repeat selection of one or two.
- Same-SKU append merge across groups in upload-window order.
- `summary.csv`, `processing_log.txt`, SKU PDFs, and a final ZIP.
- Per-file delete, per-group clear, and clear-all controls.
- Precise group/file/rule error reporting.
- `job_id`-scoped cleanup.

### Deferred

- Final general-purpose filename classification rules.
- Accounts, permissions, multi-user concurrency, and remote access.
- Database persistence and background task queues.
- Cloud deployment.
- Manual editing of SKU values or box/page mappings.
- XLSX summaries.

The classifier remains an explicit interface. During initial implementation it
may recognize the provided sample naming pattern, but ambiguity must produce a
visible error rather than a guess. General filename behavior will be specified
and tested before production rollout.

## 3. Chosen approach

Use a Python FastAPI monolith with server-rendered HTML and minimal native
JavaScript.

This approach keeps file upload, ZPL parsing, PDF manipulation, ZIP generation,
and cleanup in one runtime. It is smaller and easier to operate locally than a
separate React frontend, while preserving service boundaries that allow a
future frontend replacement.

Rejected alternatives:

- FastAPI plus React/Vite: useful for a larger interactive product, but adds a
  second build/runtime and unnecessary state synchronization for the MVP.
- Native desktop application: offers desktop packaging but adds platform and
  release complexity without improving the core label workflow.

No database is used in the MVP. Job state lives only in immutable in-memory
records and a uniquely scoped runtime directory.

## 4. Architecture and module boundaries

```text
Browser
  -> FastAPI routes and server-rendered views
    -> job orchestrator
      -> file classifier
      -> ZPL parser
      -> validation service
      -> box pairing service
      -> PDF/output service
      -> cleanup service
```

Planned source structure:

```text
app/
  main.py
  models/
    schemas.py
  services/
    file_classifier.py
    zpl_parser.py
    validation.py
    pairing.py
    pdf_processor.py
    output_builder.py
    job_processor.py
    cleanup.py
  templates/
    upload.html
    preview.html
    result.html
  static/
    app.js
    styles.css
tests/
  fixtures/
  unit/
  integration/
  e2e/
```

Responsibilities:

- Web layer: upload controls, processing options, error display, preview
  confirmation, result download, and browser-state reset.
- Classifier: return exactly one WFS PDF, one WFS ZPL/TXT, and one logistics
  PDF for a populated group, or a structured ambiguity/incompleteness error.
- Parser: split complete `^XA ... ^XZ` segments, classify pages, and extract
  metadata without relying on fixed line numbers.
- Validation: return structured strong errors, weak warnings, and audit facts.
  It does not mutate parsed input.
- Pairing: construct the immutable box-to-logistics mapping before SKU
  grouping.
- PDF/output: copy pages, validate output page counts, append same-SKU group
  outputs, create summary/log files, and build/read back the ZIP.
- Orchestrator: enforce the job state machine and atomic all-groups policy.
- Cleanup: remove only paths proven to belong to the current `job_id`.

Each service exposes typed inputs and outputs and can be tested without the web
layer.

## 5. Domain records

Core records are immutable after construction:

```text
LabelGroupFiles
  group_index
  wfs_pdf_path
  wfs_zpl_path
  logistics_pdf_path

WfsLabel
  group_index
  zpl_index
  pdf_page
  label_type: box | pallet | unknown
  sku
  box_id
  shipment_id
  gtin
  quantity
  box_text
  raw_zpl

BoxPair
  group_index
  box_index
  sku
  wfs_pdf_page
  logistics_pdf_page
  wfs_label

ProcessingOptions
  wfs_repeat: always 2 in the MVP
  logistics_repeat: 1 | 2
  ignore_pallet: always true in the MVP
  merge_same_sku: always true in the MVP
  include_summary: always true in the MVP
```

A `ValidationIssue` contains severity, group index, optional filename and page,
rule identifier, expected value, actual value, user-facing explanation, and a
repair suggestion. This supports exact error placement without duplicating
validation logic in templates.

## 6. Processing and data flow

1. Generate a unique `job_id` and create its isolated upload area.
2. Receive zero to five upload-window groups.
3. Skip empty groups. Reject partial, duplicate, unsupported, unreadable, or
   ambiguous groups.
4. Count both PDFs and split the ZPL/TXT into complete label segments.
5. Bind ZPL segment 1 to WFS page 1, segment 2 to page 2, and so on.
6. Classify every segment as box, pallet, or unknown and extract metadata.
7. Run all group-level strong validations.
8. Remove pallet labels from the effective box sequence without consuming a
   logistics page.
9. Pair effective WFS box 1 with logistics page 1, effective box 2 with page 2,
   and so on.
10. Validate uniqueness and full coverage of logistics page assignments.
11. Produce a read-only preview of every `BoxPair` and projected output order.
12. Require explicit user confirmation. Any input deletion or replacement
    invalidates the preview and requires validation again.
13. Group pairs by SKU within each group while preserving original WFS order.
14. For each box, append `W W L` or `W W L L`.
15. Merge the same SKU across groups by ascending upload-window number, using
    simple append only.
16. Re-open every generated PDF and validate its page-count formula.
17. Generate `summary.csv` and `processing_log.txt`.
18. Create the final ZIP, open it again, and validate its members.
19. Only after successful ZIP validation, clear all upload controls and remove
    the job's uploaded and intermediate files.
20. Keep only the downloadable ZIP for up to 30 minutes, then remove it by the
    same `job_id` scope.

## 7. Label parsing rules

ZPL/TXT is the primary metadata source.

- A segment starts with `^XA` and ends with `^XZ`; an unmatched boundary is a
  strong error.
- A box label contains `SINGLE SKU` and yields a non-empty SKU using a
  relative-field rule, not a fixed line or character offset.
- A pallet label contains `PALLET`, contains no `SINGLE SKU`, and may use
  `SHIPMENT ID BARCODE` as an additional confidence signal.
- Zero or one pallet label is allowed per group in the MVP; more than one is a
  strong error.
- A segment that cannot be safely classified is `unknown` and causes a strong
  error.
- SKU length must be between 2 and 100 characters and contain no line break.

The parser retains the raw segment for diagnostics but output and grouping use
the parsed normalized fields.

## 8. Validation and atomicity

The job is atomic across all non-empty groups. If any group has a strong
validation error, no SKU PDF or partial ZIP is produced.

Mandatory strong validations:

1. Every populated group contains exactly the three required file roles.
2. No role has duplicate candidates.
3. Both PDFs are readable, non-empty, and unencrypted.
4. ZPL/TXT is readable, non-empty, and composed of complete segments.
5. WFS PDF page count equals the ZPL segment count.
6. Every effective box label yields a valid SKU.
7. Pallet labels are positively identified and excluded.
8. At least one effective box exists.
9. Effective box count equals logistics PDF page count.
10. Logistics assignments are unique and cover every page from 1 through n.
11. Generated PDF page counts satisfy
    `box_count × (2 + logistics_repeat)`.
12. Same-SKU cross-group merge order and `job_id` cleanup scope are verified.

Weak warnings never change mapping or output order. Examples include multiple
shipment IDs, unusually large jobs, and surprising per-SKU box counts. They
appear in the preview, summary, and log.

## 9. User interface

### Upload and options

- Exactly five group panels.
- Each panel accepts multiple files and lists every selected filename.
- Each file has a delete action.
- Each group has a clear-group action.
- The page has a clear-all action that also restores processing defaults.
- Options show WFS repeat as fixed at two and allow logistics repeat one or
  two.
- The primary action is `Validate and preview`, not immediate generation.

Deleting or replacing a file clears that group's validation result and
invalidates any whole-job preview.

### Errors

Errors appear inside the relevant group and in an accessible top-level
summary. Each error identifies the group, file or page when known, failed rule,
actual and expected values, and the next corrective action.

On generation failure, the browser retains the upload list and selected
options so the user can replace the identified problem input. No output is
offered.

### Preview

The preview is read-only and includes group, effective box index, WFS page,
SKU, logistics page, and projected page sequence. It summarizes ignored pallet
pages, weak warnings, effective box totals, and expected SKU outputs.

The user may return to uploads or confirm generation. There is no manual SKU or
mapping edit.

### Success and reset

The result page shows output SKU count, box count, page counts, warnings, and a
ZIP download action.

The server must finish and read back the ZIP before it reports success. At that
point it deletes the job's uploads and intermediates, and the response causes
all five browser upload controls and prior preview state to reset. Processing
options return to their defaults. The verified ZIP remains downloadable for 30
minutes and belongs to the completed `job_id`, not to the next upload round.

## 10. Output contract

The ZIP contains:

```text
<sanitized-sku>.pdf
...
summary.csv
processing_log.txt
```

SKU filenames replace `/ \ : * ? " < > |` and other unsafe path characters.
If two original SKUs sanitize to the same name, later files receive a stable
numeric suffix. `summary.csv` always retains the original SKU and final output
filename.

Summary rows include job ID, group and box indexes, original SKU, source
filenames and pages, parsed metadata, final output filename, and status.

The processing log records classification results, page and segment counts,
ignored pallet pages, box mappings, output page counts, merge order, warnings,
errors, ZIP verification, and cleanup outcome.

## 11. Failure handling and cleanup

The orchestrator uses explicit states:

```text
UPLOADED -> VALIDATED -> AWAITING_CONFIRMATION -> GENERATING
          -> READY_FOR_DOWNLOAD -> EXPIRED
```

Any strong validation error enters `VALIDATION_FAILED`; a generation exception
enters `GENERATION_FAILED`.

- Validation and generation failures create no downloadable partial ZIP.
- On failure, browser-visible file selections remain until the user deletes,
  clears, or replaces them. Server-side temporary storage remains only as long
  as needed to support that correction path and is removed when the job is
  abandoned, superseded, or expires.
- On success, uploads and intermediates are removed immediately after ZIP
  read-back succeeds.
- Cleanup resolves the job root, verifies that it contains the exact current
  `job_id`, rejects paths outside the configured runtime root, and never uses a
  global delete.
- Cleanup failure is logged and shown as an operational error; it must not be
  silently treated as a clean success.

## 12. Testing strategy

### Unit tests

- ZPL segment boundaries and incomplete segments.
- Relative SKU, box ID, shipment ID, GTIN, quantity, and box-text extraction.
- Box, pallet, and unknown classification.
- SKU filename sanitation and collision handling.
- Pairing order when a pallet appears first, in the middle, or last.
- Structured validation issue contents.
- `job_id` path-containment checks.

### Integration tests

- Provided sample: four WFS pages, four ZPL segments, three logistics pages,
  with three box labels and one ignored pallet.
- One and two logistics-copy modes.
- Mismatched WFS/ZPL counts.
- Mismatched effective-box/logistics counts.
- Missing SKU and multiple pallet labels.
- Duplicate or missing file roles.
- Same SKU across non-adjacent upload groups.
- Sanitized filename collisions.
- PDF output page-count read-back.
- ZIP member read-back.

### End-to-end tests

- Upload through preview, confirm, download, and browser control reset.
- Delete one file, clear one group, and clear all groups.
- Error is rendered in the correct group with actionable values.
- Any group error prevents all output.
- Input replacement invalidates the prior preview.
- Successful generation clears all five upload controls and does not leak
  files or selections into the next round.
- Expired ZIP cleanup affects only its own `job_id`.

## 13. Acceptance criteria

The MVP is accepted only when:

- The provided sample completes the full browser workflow and all generated
  pages preserve the defined `W W L` or `W W L L` ordering.
- Every mandatory strong-validation failure blocks the entire job and points to
  the exact group and corrective action.
- A pallet in a non-final position consumes no logistics page.
- Cross-group same-SKU output is a simple append in upload-window order.
- Output PDFs and ZIP pass read-back validation.
- Successful generation leaves upload controls empty and server storage
  contains only the current downloadable ZIP.
- Starting a second production round cannot observe inputs, preview state, or
  processing selections from the first round.

## 14. Risks, unknowns, and evidence

### Known risk

Incorrect general filename classification could swap the two PDFs. The
mitigation is to keep the classifier isolated, reject ambiguity, and withhold
production rollout until naming rules are approved.

### Unknown

The final filename conventions for real production inputs are not yet defined.
Resolution requires representative production filenames and product-owner
approval of deterministic rules.

### Inspection blind spot

Current environment inspection verified PDF metadata and page counts but could
not extract PDF text because `pdftotext` was unavailable. ZPL structure and
page counts support the sample relationship, but rendered-page visual
inspection remains part of implementation verification.

### Evidence

- Business intent and validation rules:
  `../../../wfs_label_processing_requirements.md`
- Sample inputs: `../../../Sample Label/`
- Verified sample metadata on 2026-07-04: WFS PDF has four pages; logistics PDF
  has three pages; ZPL/TXT has four complete segments, with `SINGLE SKU` in the
  first three and `PALLET` without `SINGLE SKU` in the fourth.
