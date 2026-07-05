#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  exec uv run python app.py
fi

if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python app.py
fi

echo "uv is not installed and .venv/bin/python was not found."
echo "Run: uv sync"
exit 1
