# WFS LabelFlow Public GitHub Preparation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the classifier follow the newly confirmed `WFS*` filename rule, record it as a provisional optimization item, and prepare the repository for a public GitHub upload with clear Mac/Windows setup guidance.

**Architecture:** Keep filename role detection deterministic and strict: any PDF or source file whose basename starts with `WFS` is treated as the WFS side, and the remaining PDF must be non-`WFS`. Update state and onboarding docs in the root repository so the public clone has a single source of truth for progress, local startup, required files, and the remaining filename-rule follow-up.

**Tech Stack:** Python 3.11, FastAPI, PyPDF, Jinja2, uv/uvicorn, pytest, ruff, Git/GitHub CLI.

---

### Task 1: Tighten filename classification

**Files:**
- Modify: `.worktrees/wfs-label-flow-plan/app/services/classifier.py`
- Modify: `.worktrees/wfs-label-flow-plan/tests/unit/test_classifier.py`

- [ ] **Step 1: Write the failing test**

Add a test that accepts these files in one group:

```python
[
    touch(tmp_path / "WFS-20260705.txt"),
    touch(tmp_path / "WFS-20260705.pdf"),
    touch(tmp_path / "Logistics-20260705.pdf"),
]
```

and asserts the first two are classified as WFS source/PDF, while the third is logistics.

Add a rejection test for a group like:

```python
[
    touch(tmp_path / "WFS-20260705.txt"),
    touch(tmp_path / "WFS-20260705.pdf"),
    touch(tmp_path / "WFS-logistics.pdf"),
]
```

and assert the classifier raises `ProcessingError` with rule `file_role_ambiguity`.

- [ ] **Step 2: Implement the minimal rule change**

Update `classify_group` so the WFS candidate set is built from filenames whose `stem` starts with `WFS` case-insensitively, and the logistics PDF must be the remaining PDF whose `stem` does not start with `WFS`.

- [ ] **Step 3: Run the focused tests**

Run:

```sh
.worktrees/wfs-label-flow-plan/.venv/bin/pytest tests/unit/test_classifier.py -v
```

Expected: the full classifier test file passes.

- [ ] **Step 4: Commit**

```sh
git add .worktrees/wfs-label-flow-plan/app/services/classifier.py .worktrees/wfs-label-flow-plan/tests/unit/test_classifier.py
git commit -m "fix: tighten WFS filename classification"
```

### Task 2: Record the provisional rule in project state and onboarding docs

**Files:**
- Modify: `STATE.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the state snapshot**

Add a pending follow-up that says the current provisional rule is `WFS*`-prefix classification for the WFS PDF and source file, and that the next optimization pass should confirm any additional production filename patterns before removing the provisional status.

- [ ] **Step 2: Rewrite the README for public onboarding**

Add a Mac/Windows-friendly setup section that includes:

```sh
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8790
```

and explains the required repository files and folders:

```text
app/
tests/
pyproject.toml
uv.lock
Sample Label/
wfs_label_processing_requirements.md
```

Keep the README focused on local cloning, startup, verification, and the ZIP workflow.

- [ ] **Step 3: Update the project map**

Point the map at the root repository paths instead of the temporary worktree paths, and keep the recovery order based on `STATE.md`.

- [ ] **Step 4: Run a documentation sanity check**

Run:

```sh
git diff --check
```

Expected: no whitespace or patch-format errors.

- [ ] **Step 5: Commit**

```sh
git add STATE.md README.md AGENTS.md
git commit -m "docs: refresh state and onboarding for public release"
```

### Task 3: Merge the implementation branch into the public root and publish

**Files:**
- Modify: repository branch history and Git remote configuration

- [ ] **Step 1: Verify the implementation branch is clean**

Run:

```sh
git status --short
```

Expected: no unexpected tracked changes in the implementation branch before merge.

- [ ] **Step 2: Merge the implementation branch into `master`**

Bring the tracked `app/`, `tests/`, `pyproject.toml`, `uv.lock`, and supporting files into the root branch so the public GitHub repository contains a runnable project from a fresh clone.

- [ ] **Step 3: Create the public GitHub repository and add the remote**

Create a public repo and add it as `origin`, then push the public branch.

- [ ] **Step 4: Verify the public clone instructions**

Run the documented local startup command from the repository root and confirm the homepage loads on `http://127.0.0.1:8790`.

- [ ] **Step 5: Commit/push publication prep**

```sh
git push -u origin master
```
