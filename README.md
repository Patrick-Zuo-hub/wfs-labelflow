# WFS LabelFlow

Local single-user tool for validating and assembling WFS and logistics labels.

This repository is meant to be cloned and run locally on macOS or Windows
without any shared backend. All validation, previewing, and ZIP generation
happen on the machine that opens the app.

## Requirements

- Python 3.11 or newer
- `uv`
- A browser for opening the local web app

## Quick Start

On macOS, double-click `start.command` to launch the app.

On Windows, double-click `start.bat` to launch the app.

On macOS or Windows, from the repository root:

```sh
uv sync
make dev
```

If `make` is not available, use:

```sh
uv run python app.py
```

Open `http://127.0.0.1:8788`.

If you are on Windows PowerShell, run the same commands there. The server
listens only on `127.0.0.1`, so other people on the network cannot use it
unless you change the host binding.

If you prefer a direct command instead of `make dev`, this also works:

```sh
uv run uvicorn app.main:app --host 127.0.0.1 --port 8788
```

## Required Files

A fresh clone should include these project files and folders:

- `app/`
- `tests/`
- `pyproject.toml`
- `uv.lock`
- `Sample Label/`
- `wfs_label_processing_requirements.md`

The sample label folder is useful for verifying the bundled sample workflow,
and the requirements document explains the operating rules in Chinese.

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
