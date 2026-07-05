.PHONY: dev sync test lint inspect

dev:
	uv run python app.py

sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check app tests

inspect:
	uv run python scripts/inspect_sample.py
