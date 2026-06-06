# One Piece integration

Design-change provenance via a minimal JSON SSOT layer. Full [One Piece](https://github.com/hirototamura/one-piece) web UI is **out of scope** for the current MVP.

## Goal

When agents propose or apply design changes during a run, record **who changed what, when, and why** in a format compatible with One Piece's provenance model — without blocking the simulation loop.

## Planned layout

```text
integrations/one_piece/
├── client.py          # generate provenance records from run outputs
└── ssot_schema.json   # MVP subset: elements, parameters, traces
```

## Trigger points

`scenario/runner.py` exports provenance after the run summary is written:

1. Read `events.jsonl` design-change rows (`/eclss/events/design_change`)
2. Join matching `messages.jsonl` entries for `reasoning` / `decision_source`
3. Attach `before` / `after` topology snapshots from `design_state.jsonl`
4. Write `provenance.jsonl` into the same run directory

Each record should link to:

- Run ID and step from `summary.json`
- Matching row in `events.jsonl` (`/eclss/events/design_change`)
- Agent role from `messages.jsonl` when applicable

## Data model (MVP subset)

Aligned with One Piece `SsotProvenanceRecord` concept:

| Field | Example |
| --- | --- |
| `actor` | `design_engineer` (rule) or future LLM agent id |
| `actor_kind` | `ai_agent` / `logic_automation` |
| `step` | 35 |
| `change_kind` | `add_edge` |
| `payload` | bypass edge manifold → scrubber |
| `before_topology` | snapshot from prior `design_state.jsonl` |
| `after_topology` | post-change snapshot |

Storage: JSON file co-located with run output (`provenance.jsonl`). Schema contract lives in `integrations/one_piece/ssot_schema.json`.

## SSOS topology ingest (optional)

One Piece connector [`one_piece_connectors/ssos.py`](https://github.com/hirototamura/one-piece/blob/main/packages/connectors/one_piece_connectors/ssos.py) can seed initial `SystemElement` + ICD graph from a real SSOS repo. The MVP may instead hand-author `ssot_schema.json` from Mock ECLSS default topology in `environment/eclss_ops/design_state.py`.

## Dependency strategy

Recommendation (see also [mvp_plan.md](../memo/mvp_plan.md)):

- **JSON file + future connector** — no hard dependency on One Piece packages until provenance stabilizes
- Git submodule or `pip install -e ../one-piece/packages/connectors` when ingest is needed

## Status

**Day5B complete (MVP scope).**

- `integrations/one_piece/client.py` provides `export_run_provenance(run_dir)`
- `summary.json` now includes:
  - `provenance_path`
  - `provenance_record_count`
- `labeled` and `labeled_llm_guarded` runs emit design-change provenance when applicable

## Day5B retrospective

- Export timing is end-of-run, but records include all `design_change` steps (not final state only).
- Baseline runs still produce `provenance.jsonl` with zero records, keeping file contract stable.
- Trace linkage now carries `reasoning`, `decision_source`, `parse_status` when available.

## Next plan (post-Day5B)

1. Add run-index export (`provenance_index.json`) for cross-run comparison in dashboard/CLI.
2. ~~Expand optional provenance scope for selected recovery commands~~ — **Done (EPS-4):** `request_eps_boost` recovery records with `record_type: recovery`.
3. Add connector handoff shim so One Piece repo can ingest run outputs without custom parsing.

## Related docs

- [api-contracts.md](api-contracts.md) — `design_change` event schema
- [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) — where to inspect design changes in run output
- [architecture.md](architecture.md) — layer placement of `integrations/`
