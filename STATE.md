# Project state

## Snapshot

- Last updated: 2026-07-09 20:40:00 CST +0800
- Confidence: high for the new ZIP + Excel dispatch workflow in API and
  integration tests; medium for browser automation in this sandbox because
  Chromium launch is blocked by macOS permission constraints here.
- One-line status: the ZIP + Excel dispatch flow is implemented and
  regression-tested at the service/API level; browser smoke verification is
  environment-blocked in the Codex sandbox.

## Objective and success criteria

- Objective: Build a local, single-user WFS label processor that can validate
  the WFS ZIP + Excel carrier mapping workflow and produce an atomic dispatch
  ZIP.
- Success criteria: The updated upload flow passes validation, preview,
  generation, download, cleanup, and upload-reset checks for the ZIP + Excel
  dispatch path.

## Current phase

- Phase: ZIP + Excel dispatch workflow implemented; awaiting browser smoke
  verification in an environment that can launch Chromium.
- Evidence: The API/integration path for ZIP + Excel upload, mapping
  validation, atomic generation, download, and cleanup is implemented and
  regression-tested in the worktree.

## Work status

### Completed

- Inspected the updated business rules for the ZIP + Excel dispatch workflow.
- Implemented ZIP ingestion, Excel mapping ingestion, and dispatch planning.
- Implemented atomic validation and generation for the dispatch flow.
- Reworked the server-rendered UI for one ZIP upload and one Excel upload.
- Added clear-file controls, clear-all controls, and upload reset after
  successful generation.
- Added API and integration coverage for the dispatch path.
- Verified the dispatch API/integration suite in the worktree.

### Active

- Browser smoke verification remains blocked in this sandbox because Chromium
  cannot launch here.

### Pending

- Run the browser smoke tests in an environment that can launch Playwright
  Chromium.
- If the user wants additional refinements, update the classifier or UX
  accordingly.

### Unknown

- Browser automation success in this sandbox is still unknown because the
  Chromium launch is blocked by macOS permission handling here.

## Blockers, risks, and conflicts

- Blockers: Browser smoke verification is blocked by the sandboxed Chromium
  launch permission issue.
- Risks: The dispatch workflow depends on the uploaded ZIP and Excel file
  contents matching the expected naming and mapping rules; ambiguous inputs
  must still fail atomically.
- Conflicts: None known in the current dispatch design.

## Next actions

| Priority | Action | Owner or trigger | Evidence |
| --- | --- | --- | --- |
| P0 | Run browser smoke verification in a Chromium-capable environment | Codex | Browser flow passes without the sandbox launch error |
| P1 | Gather user feedback on the new ZIP + Excel dispatch UX | Product owner | Explicit approval of the current upload/preview/confirm flow |
| P2 | Archive the verified dispatch state | Codex after verification | `STATE.md` and `AGENTS.md` reflect the accepted operating model |

## Recent consequential changes

- 2026-07-04 — Established `AGENTS.md` as the project map and mandated
  `STATE.md`-first recovery for every production/development round.
- 2026-07-09 — Added ZIP ingestion, Excel mapping ingestion, dispatch
  planning, and atomic dispatch generation.
- 2026-07-09 — Reworked the upload UI to a single ZIP + Excel workflow with
  clear controls and upload reset after successful generation.
- 2026-07-09 — Verified the dispatch API/integration suite successfully in the
  worktree.
- 2026-07-09 — Browser smoke tests were blocked by Chromium launch permission
  errors in the Codex sandbox.

## Evidence and deeper reading

- [Approved MVP design](docs/superpowers/specs/2026-07-04-wfs-label-flow-design.md)
- [Authoritative requirements](wfs_label_processing_requirements.md)
- [Project map](AGENTS.md)
- [Sample inputs](Sample%20Label/)
