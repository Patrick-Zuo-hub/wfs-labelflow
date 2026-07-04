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

The repository root is this directory. Runtime uploads, intermediate PDFs,
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

- `app/main.py` — FastAPI application and HTTP routes.
- `app/services/` — classification, parsing, validation, pairing, PDF output,
  job orchestration, and cleanup.
- `app/models/` — immutable domain records and API/view schemas.
- `app/templates/` and `app/static/` — server-rendered interface and minimal
  browser behavior.
- `tests/` — unit, integration, and end-to-end acceptance tests.

These paths describe the approved design; executable application files do not
exist yet.

## Verification

The current baseline is documentation-only. Verify it with:

```sh
test -f STATE.md
test -f docs/superpowers/specs/2026-07-04-wfs-label-flow-design.md
rg -n "TBD|TODO|implement later|fill in details" \
  docs/superpowers/specs/2026-07-04-wfs-label-flow-design.md
```

After implementation begins, the implementation plan must define executable
test and startup commands before they are recorded here as established facts.
