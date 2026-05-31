# One Piece integration

Design-change provenance via a minimal JSON SSOT layer. Full [One Piece](https://github.com/hirototamura/one-piece) web UI is **out of scope** for the current MVP.

## Goal

When agents propose or apply design changes during a run, record **who changed what, when, and why** in a format compatible with One Piece's provenance model — without blocking the simulation loop.

## Planned layout

```text
integrations/one_piece/
├── client.py          # append/read provenance records
└── ssot_schema.json   # MVP subset: elements, parameters, traces
```

## Trigger points (planned)

Hook from `scenario/runner.py` after:

1. `sim.apply_design_change()` — permanent topology/parameter mutation
2. Optionally: Operator recovery commands (temporary vs permanent distinction)

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

Storage: JSON file co-located with run output (e.g. `provenance.jsonl`) or appended to project-level SSOT seed in `ssot_schema.json`.

## SSOS topology ingest (optional)

One Piece connector [`one_piece_connectors/ssos.py`](https://github.com/hirototamura/one-piece/blob/main/packages/connectors/one_piece_connectors/ssos.py) can seed initial `SystemElement` + ICD graph from a real SSOS repo. The MVP may instead hand-author `ssot_schema.json` from Mock ECLSS default topology in `environment/eclss_ops/design_state.py`.

## Dependency strategy

Recommendation (see also [mvp_plan.md](../memo/mvp_plan.md)):

- **JSON file + future connector** — no hard dependency on One Piece packages until provenance stabilizes
- Git submodule or `pip install -e ../one-piece/packages/connectors` when ingest is needed

## Status

**In progress.** Implementation is active on a parallel track.

`labeled_shadow` mode is separate: LLM logging only, no One Piece writes yet.

## Related docs

- [api-contracts.md](api-contracts.md) — `design_change` event schema
- [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) — where to inspect design changes in run output
- [architecture.md](architecture.md) — layer placement of `integrations/`
