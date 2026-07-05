@echo off
setlocal

cd /d "%~dp0"

where uv >nul 2>&1
if %errorlevel%==0 (
  uv run python app.py
  exit /b %errorlevel%
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
  exit /b %errorlevel%
)

echo uv is not installed and .venv\Scripts\python.exe was not found.
echo Run: uv sync
exit /b 1
