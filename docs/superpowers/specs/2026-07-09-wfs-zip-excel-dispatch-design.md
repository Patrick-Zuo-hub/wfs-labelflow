# WFS ZIP + Excel dispatch design

## Goal

Replace the previous multi-upload flow with a single ZIP upload plus one Excel
mapping file.

The new workflow must:

- accept one ZIP that contains all label PDFs and TXT files;
- accept one Excel file that maps `货代单号` to one or more `WFS Shipment ID`
  values;
- validate that each WFS shipment has both a PDF and a TXT file;
- assign carrier labels according to the Excel mapping;
- consume each carrier label PDF at most once;
- fail the whole job if any strong validation fails; and
- clear the uploaded files after a successful ZIP generation.

## Scope

This design keeps the current server-rendered local app structure and changes
only the input model, dispatch logic, and validation flow.

The output remains a generated ZIP artifact, but its contents are now built from
the ZIP + Excel dispatch rules rather than from the previous multi-input UI.

## Inputs

### ZIP upload

The ZIP is the authoritative container for all PDF and TXT label files.

File identity is derived from the basename without extension.

Required file classes:

- WFS shipment PDF
- WFS shipment TXT
- carrier label PDF

### Excel upload

The Excel file is the authoritative carrier-to-shipment mapping source.

Expected columns in the first worksheet:

- `货代单号`
- `WFS Shipment ID`

Each row defines one mapping from one carrier number to one WFS shipment ID.
A carrier number may appear on multiple rows and may therefore map to multiple
WFS shipment IDs.

## Core rules

### WFS file pairing

For every WFS shipment ID that appears in the ZIP, the system must find exactly
one PDF and exactly one TXT file.

If only one side exists, the job fails.

### Carrier label assignment

Each carrier label PDF is a shared resource bound to one carrier number.

When a carrier number is referenced by multiple WFS shipment IDs in the Excel
file, the same carrier label PDF is assigned across those shipments without
duplicating the source file.

Each carrier label PDF may be consumed only once for its carrier number. The
same carrier file must not be bound to a second carrier number.

### Strong validation failures

Any one of the following must fail the entire job:

- a WFS shipment has PDF without TXT, or TXT without PDF;
- a WFS shipment present in the ZIP is not referenced by any Excel row, or an
  Excel row references a WFS shipment ID that does not exist in the ZIP;
- a carrier number listed in the Excel file cannot be found in the uploaded
  files;
- a carrier label PDF remains unassigned after dispatch;
- the Excel file contains malformed or missing required headers;
- the ZIP contains duplicate basenames that make identity ambiguous;
- a single WFS shipment would require more than one carrier assignment; or
- a carrier label would be bound to more than one carrier number.

## Processing model

The processing pipeline should be explicit and deterministic:

1. Parse the ZIP and index files by basename.
2. Classify filenames into WFS PDF, WFS TXT, or carrier label PDF.
3. Parse the Excel mapping rows.
4. Build the WFS-to-carrier dispatch table from the mapping.
5. Validate WFS completeness.
6. Validate carrier availability and one-time consumption.
7. Build the output artifact only after all validations pass.
8. Clear the job uploads and intermediates after the ZIP is verified.

## Proposed architecture

### `app/services/archive_ingest.py`

Responsible for ZIP extraction, basename indexing, and duplicate detection.

### `app/services/excel_mapping.py`

Responsible for reading the first worksheet and converting rows into mapping
records.

### `app/services/dispatch.py`

Responsible for assigning carrier labels to WFS shipments, enforcing the
single-use carrier rule, and detecting incomplete or contradictory mappings.

### `app/services/validation.py`

Responsible for collecting strong validation errors into a user-facing report.

### `app/services/output.py`

Responsible for building the final ZIP only from validated dispatch results.

This split keeps parsing, business rules, and output generation isolated enough
to test independently.

## User experience

The UI should expose:

- one ZIP upload control;
- one Excel upload control;
- a validation preview step before generation;
- a final confirmation step before the ZIP is written; and
- an error panel that points to the exact file, sheet row, or mapping entry that
  caused the failure.

If validation fails, the user should see what is wrong and which file or row is
responsible. The job must not generate a partial ZIP.

After a successful ZIP generation, the UI must reset both uploads and clear all
job-scoped intermediate state so the next run cannot accidentally reuse prior
files.

## Testing strategy

Add or update tests for:

- ZIP inventory parsing and duplicate basename rejection;
- Excel header parsing and row mapping;
- one carrier number mapping to multiple WFS shipment IDs;
- carrier PDF single-use enforcement;
- WFS PDF/TXT pairing validation;
- unassigned carrier label detection;
- all-or-nothing failure behavior; and
- successful cleanup after ZIP generation.

An acceptance test should cover the end-to-end happy path using the bundled
sample files plus the new Excel mapping file.

## Open assumption

This design assumes the `WFS Shipment ID` value in the Excel file matches the
basename of the WFS shipment PDF and TXT files exactly.

If representative live filenames use a different pattern, we should update the
classifier before implementation starts.
