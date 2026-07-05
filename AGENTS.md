# WFS LabelFlow project map

## Purpose

Build a local, single-user web tool that validates, pairs, splits, inserts, and
merges WFS and logistics label PDFs using the WFS ZPL/TXT source as the
authoritative page metadata.

## Mandatory recovery order

At the start of every production or development round:

1. Read `STATE.md`.
2. Follow its `Next actions` and open only the linked evidence needed for that
   action.
3. Do not rescan the whole project unless `STATE.md` says its map is stale or
   the referenced evidence is missing or contradictory.
4. Update `STATE.md` last, after verified work changes the recoverable state.

## Reading order

1. `STATE.md` — current phase, verified result, blocker, and next action.
2. `docs/superpowers/specs/2026-07-04-wfs-label-flow-design.md` — approved MVP
   design.
3. `wfs_label_processing_requirements.md` — authoritative business
   requirements and validation policy.
4. `Sample Label/` — primary sample input files.

## Repository boundary

The repository root is this directory. The executable MVP lives in the
`.worktrees/wfs-label-flow-plan/` worktree; this root keeps the project map,
state, scripts, docs, and sample evidence. Runtime uploads, intermediate PDFs,
generated output, local virtual environments, caches, and visual brainstorming
artifacts are not source files and must remain ignored by Git.

## Durable constraints

- Use the Project Architecture skill for project recovery and organization.
- Preserve uncommitted user work and never delete or overwrite authoritative
  sources without explicit approval.
- ZPL/TXT label order binds directly to WFS PDF page order.
- Build the WFS-to-logistics box mapping before grouping by SKU.
- Never infer a mapping when classification or validation is ambiguous.
- A strong validation failure in any non-empty group fails the whole job.
- A generated mapping is read-only; correction requires replacing inputs.
- After a ZIP is generated and verified, clear every upload control and remove
  that job's uploaded and intermediate files.
- Cleanup is always scoped by `job_id`; global runtime cleanup is forbidden.

## Planned entry points

- `.worktrees/wfs-label-flow-plan/app/main.py` — FastAPI application and HTTP
  routes.
- `.worktrees/wfs-label-flow-plan/app/services/` — classification, parsing,
  validation, pairing, PDF output, job orchestration, and cleanup.
- `.worktrees/wfs-label-flow-plan/app/models/` — immutable domain records and
  API/view schemas.
- `.worktrees/wfs-label-flow-plan/app/templates/` and
  `.worktrees/wfs-label-flow-plan/app/static/` — server-rendered interface and
  minimal browser behavior.
- `.worktrees/wfs-label-flow-plan/tests/` — unit, integration, and end-to-end
  acceptance tests.
- `scripts/inspect_sample.py` — sample inspection and verified output smoke
  test.

These paths describe the implemented MVP and its recovery helpers.

## Verification

The current baseline is an implemented, sample-verified MVP. Verify it with:

```sh
.worktrees/wfs-label-flow-plan/.venv/bin/pytest
.worktrees/wfs-label-flow-plan/.venv/bin/ruff check app tests
.worktrees/wfs-label-flow-plan/.venv/bin/python scripts/inspect_sample.py
git diff --check
```

Always read `STATE.md` first, then only the evidence needed for the next action.

Latest verified run: 99 tests passed, with 3 warnings from third-party
dependencies only.

After implementation begins, the implementation plan must define executable
test and startup commands before they are recorded here as established facts.
