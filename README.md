# WFS LabelFlow

Local single-user tool for validating and assembling WFS and logistics labels.

## Start

```sh
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8788
```

Open `http://127.0.0.1:8788`.

## Production workflow

1. Add up to five groups; each non-empty group needs one WFS PDF, one WFS ZPL/TXT, and one logistics PDF.
2. Delete an individual file, clear a group, or clear all before validation.
3. Select one or two logistics copies and choose Validate and preview.
4. Correct every group-specific error. Never override a page mapping.
5. Review the read-only box mapping and confirm generation.
6. Download the ZIP. Successful generation clears every upload control before the next production round.

## Verification

```sh
uv run pytest
uv run ruff check app tests
uv run python scripts/inspect_sample.py
```

Runtime jobs live under `data/jobs/<job_id>/`. Cleanup is always scoped to one validated job ID. Completed ZIPs expire after 30 minutes.
