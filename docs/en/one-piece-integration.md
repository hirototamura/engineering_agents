
# One Piece Integration

Two different integrations share this directory:

| Track | What is implemented | What is not |
| --- | --- | --- |
| **`balancing_cube`** | `MechanicalBridge` **reads** a pinned One-Piece store (`ssot.path`): snapshot, requirements, KDPs, detailed parameters. Evidence is written through a durable outbox. | Editing One-Piece requirements from this repo; treating CPU-only as GPU agreement |
| **ECLSS** (`scrubber_degradation`, `ssos_eclss_loop`) | **Provenance export** of recovery/ops/design events as JSON compatible with the One Piece data model | Pulling ECLSS design/verification requirements from One-Piece SSOT (still stubbed in `scenario.yaml`) |

The full [One Piece](https://github.com/hirototamura/one-piece) Web UI is out of scope. Cube runbook: [MuJoCo design loop](mujoco-one-piece.md).

> JSONL schema: [api-contracts.md](api-contracts.md). Incomplete items: [development-plan.md](development-plan.md).

---

## Purpose

As a precursor to autonomous hardware development, make the following traceable:

1. **Runtime recovery** — who requested which EPS boost and when
2. **Post-run design proposals** — who recommended which topology change and why (`design_proposals.json`)
3. (Future) ingestion into One Piece SSOT and cross-run indexing

The simulation loop is not blocked by provenance generation. On failure, only a warning is logged.

---

## Layout

```text
src/integrations/one_piece/
├── __init__.py              # export_run_provenance (ECLSS)
├── client.py                # build records from events/messages
├── ssot_schema.json         # MVP subset (elements, parameters, traces)
├── mechanical_bridge.py     # balancing_cube SSOT load + evidence outbox
├── balancing_cube_import.py
└── agent_context_exclusions.json
```

---

## Trigger and flow

At the end of `ScrubberDegradationScenario.run()`:

```text
1. team.propose_post_run_design()  → design_proposals.json
2. log.write_summary(summary)
3. export_run_provenance(run_dir)  → provenance.jsonl
4. append provenance_path / provenance_record_count to summary
```

```text
events.jsonl ──┐
messages.jsonl ├──► build_provenance_records() ──► provenance.jsonl
design_state.jsonl ┘
summary.json
```

### ssos_eclss_loop

`SsosEclssLoopScenario.run()` exports operational provenance when `agents.actor.mode` is `labeled_rule_base` or `llm`. `/eclss/events/operational_applied` becomes `record_type: operational`. Post-run `design_proposals.json` comes from `PostRunDesignAgent` (not `team.propose_post_run_design`).

---

## Records exported today

| Type | Source | Current scrubber_degradation |
| --- | --- | --- |
| `design_change` | Runtime `/eclss/events/design_change` | **0 records** (no design applied at runtime) |
| `recovery` | `recovery_applied` for `request_eps_boost` | **1 or more** (labeled / llm when power is critical) |

### Recovery record (implemented)

```json
{
  "record_id": "scrubber_degradation_labeled_rule_base:recovery:1",
  "record_type": "recovery",
  "run_id": "scrubber_degradation_labeled_rule_base",
  "scenario": "scrubber_degradation",
  "step": 28,
  "actor": "engineer_3",
  "actor_kind": "ai_agent",
  "change_kind": "request_eps_boost",
  "payload": {
    "support_w": 120.0,
    "eps": {"bcdu_mode": "discharging"}
  },
  "trace": {
    "event_kind": "/eclss/events/recovery_applied",
    "decision_source": "rule",
    "message": "Requesting EPS support boost of 120 W.",
    "reasoning": "Power margin critical; requesting temporary EPS assist."
  }
}
```

`actor` is `issued_by` (`engineer_*`). `trace` is resolved from the `recovery_command` message at the same step (`from_role == actor`).

### Design change record (protocol ready, no data)

Format when `apply_design_change` is used at runtime (future or other scenarios):

```json
{
  "record_id": "run_id:design_change:1",
  "run_id": "run_id",
  "scenario": "scrubber_degradation",
  "step": 35,
  "actor": "engineer_4",
  "actor_kind": "ai_agent",
  "change_kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "before_topology": {"nodes": [], "edges": []},
  "after_topology": {"nodes": [], "edges": []},
  "trace": {
    "event_kind": "/eclss/events/design_change",
    "decision_source": "rule"
  }
}
```

---

## Relationship to design_proposals.json

| Artifact | Timing | provenance link |
| --- | --- | --- |
| `design_proposals.json` | After run | **Not exported** (planned) |
| `provenance.jsonl` | After run | Runtime events only |

Post-run permanent proposals (bypass valve addition, emergency power, `set_parameter`, etc.) live in `design_proposals.json`; the dashboard renders Before/After preview. **Automatic linkage to One Piece is not implemented yet.**

### Expected next steps (Day 9)

1. Read `design_proposals.json` and append `record_type: design_proposal` records
2. `before_topology` = `baseline_topology`, `after_topology` = virtual graph after applying the proposal
3. `trace.decision_source` = `rule` / `llm`, `trace.reasoning` = proposal rationale

---

## Data model (MVP subset)

Aligned with the One Piece `SsotProvenanceRecord` concept. Required fields:

| Field | Description |
| --- | --- |
| `record_id` | `{run_id}:{type}:{sequence}` |
| `run_id` | Run directory name |
| `scenario` | `scrubber_degradation`, etc. |
| `step` | Event step |
| `actor` | Representative engineer ID (`engineer_*`) |
| `actor_kind` | `ai_agent` / `logic_automation` |
| `change_kind` | `request_eps_boost`, `add_edge`, etc. |
| `payload` | Command / change details |
| `trace` | message, reasoning, decision_source, parse_status |

Optional: `record_type` (`recovery`), `before_topology` / `after_topology` (for design changes).

Contract: `src/integrations/one_piece/ssot_schema.json`.

---

## Link to summary.json

```json
{
  "provenance_path": "experiments/eclss/results/scrubber_degradation_labeled_rule_base/provenance.jsonl",
  "provenance_record_count": 2,
  "design_proposals_path": ".../design_proposals.json",
  "design_proposal_count": 1
}
```

Baseline (`agents.mode: none`) also emits **`provenance.jsonl` with 0 records** to stabilize the file-existence contract.

---

## SSOS topology ingestion

| Path | Status |
| --- | --- |
| Mock ECLSS default topology | scrubber — `environment/scrubber/eclss_ops/design_state.py` |
| SSOS live ECLSS operations | ssos — `Ros2EclssBridge` + `EclssBackend` (Phase 0–7 complete) |
| One Piece connector [`ssos.py`](https://github.com/hirototamura/one-piece/blob/main/packages/connectors/one_piece_connectors/ssos.py) | Optional — seed initial `SystemElement` + ICD graph from real SSOS |

Phase 8 (ROS launch remap + gateway): [backlog BL-003](memo/backlog.md#bl-003).

---

## Dependency strategy

- **JSON files + future connector** — avoid hard dependency on One Piece packages until provenance format stabilizes
- When ingestion is needed: git submodule or `pip install -e ../one-piece/packages/connectors`
- Policy details: [memo/scrubber_degradation/mvp_plan.md](memo/scrubber_degradation/mvp_plan.md)

---

## Status summary

| Item | Status |
| --- | --- |
| `export_run_provenance()` | Done |
| scrubber EPS recovery provenance | Done |
| ssos operational provenance | Done |
| Runtime design_change provenance | Protocol ready; 0 records in current scenarios |
| post-run `design_proposals` → provenance | **Not implemented** |
| `provenance_index.json` (cross-run) | **Not implemented** |
| One Piece Web UI | Out of scope |

---

## Related documentation

- [api-contracts.md](api-contracts.md) — all JSONL schemas
- [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) — how to read outputs
- [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) — how to read ssos outputs
- [architecture.md](architecture.md) — execution flow
- [development-plan.md](development-plan.md) — Day 9–10 plan
