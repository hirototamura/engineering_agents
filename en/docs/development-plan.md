> Japanese: [../../ja/docs/development-plan.md](../../ja/docs/development-plan.md)

# Development Plan (In Progress and Not Started)

This document aggregates **features not yet complete** and the **research backlog**. For available functionality, see [README.md](../README.md) and the design documentation under `en/docs/`.

---

## Current milestone

### Complete (available as MVP)

| Area | Contents |
| --- | --- |
| SSOS mock | `StationSimulator` (ECLSS + EPS), `SimulatorProtocol`, ROS2-style topic definitions |
| Scenario | `scrubber_degradation` — 50 steps, anomaly injection from step 20 |
| Agents | `none` / `labeled_rule_base` / `llm`, N homogeneous engineers (default 4) |
| Recovery | Fan acceleration, load reduction, EPS boost, temporary bypass |
| Post-run design | `design_proposals.json` (no topology change at runtime) |
| provenance | `provenance.jsonl` — **runtime recovery** (mainly `request_eps_boost`) |
| Dashboard | Overview / Step replay / 2-run compare / design proposal topology visualization |
| Tests | Baseline, labeled, and llm (mock LLM) regression |

### In progress

| Item | Description | Reference |
| --- | --- | --- |
| LLM comparison experiments | Trajectory comparison across models, temperature, and run_id (dashboard compare) | [architecture.md](architecture.md) |
| Documentation | Updating `ja/docs/` and `en/docs/` in this repository | — |

### Next implementation (priority order)

1. **CLI integration** — single entry point such as `python -m tools.cli run --scenario scrubber_degradation --agents-mode llm` ([memo/eps_implementation_plan.md](../memo/eps_implementation_plan.md) Day 8)
2. **provenance extension** — export `design_proposals.json` to One Piece records (currently only runtime `design_change` events; post-run proposals not linked)
3. **provenance index** — cross-run `provenance_index.json` (for dashboard / CLI comparison)
4. **Real SSOS adapter** — contract tests and ROS2 bridge for `SsosAdapter` (Day 10)

### Later (near out of scope)

| Item | Status |
| --- | --- |
| One Piece Web / SSOT UI | Not connected (JSON provenance only) |
| Real SSOS orbital connection | Stub only |
| `agents.mode: base` | Not implemented (unlabeled emergent roles) — [memo/backlog.md](../memo/backlog.md) BL-001 |
| Evolving persona research | Backlog — BL-002 |

---

## Roadmap (timeline)

```text
[Complete]
  Day 1–2  Layer separation, SimulatorProtocol, telemetry
  Day 3–4  scrubber_degradation scenario, labeled team
  Day 5B   One Piece provenance (recovery)
  Day 6    Streamlit dashboard
  EPS-1–4  SARJ/BCDU mock, StationSimulator, eps_telemetry
  Homogeneous N-agent LLM team (homogeneous agent team refactor)

[Next]
  Day 8    CLI
  Day 9    provenance index + design_proposals export
  Day 10   SSOS adapter contract tests

[Research]
  BL-001   base mode (emergent roles)
  BL-002   evolving persona
```

Detailed task breakdown: [memo/mvp_plan.md](../memo/mvp_plan.md), EPS milestones: [memo/eps_implementation_plan.md](../memo/eps_implementation_plan.md).

---

## Research notes (`ja/memo/` / `en/memo/`)

Implementation plans, workshop drafts, and backlog. These are **records of the design process**, not living documentation.

| Memo | Contents |
| --- | --- |
| [mvp_plan.md](../memo/mvp_plan.md) | Week roadmap, Day 1–10 retrospective |
| [homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md) | Design agreement for N homogeneous agents + representative action + post-run design |
| [persona_llm_core_oop_plan.md](../memo/persona_llm_core_oop_plan.md) | Persona / Team / LLM Core OOP (Day 1–8 completion record) |
| [eps_implementation_plan.md](../memo/eps_implementation_plan.md) | EPS-1–4, CLI and SSOS adapter day boundaries |
| [persona_workshop_draft.md](../memo/persona_workshop_draft.md) | Persona workshop agreement draft |
| [backlog.md](../memo/backlog.md) | BL-001 emergent roles, BL-002 evolving persona, etc. |

---

## SSOS / One Piece integration (in progress)

```text
[ This repository MVP ]
  MockEclssSimulator + EpsStack
       ↑ SimulatorProtocol
  ScrubberDegradationTeam
       ↓ JSONL + design_proposals.json
  Streamlit dashboard

[ Not connected ]
  SSOS adapter (ROS2)     … stub, contract tests planned
  One Piece Web UI        … provenance JSON only
  design_proposals → provenance … export not implemented
```

Current One Piece integration: [one-piece-integration.md](one-piece-integration.md).

---

## Contributor checklist

When adding a feature:

1. If you change `SimulatorProtocol` or JSONL schema, update [api-contracts.md](api-contracts.md)
2. If you add agent modes, update [architecture.md](architecture.md) and the scenario doc
3. Regression: `pytest tests/scenario/test_scrubber_baseline.py` (always), `test_scrubber_with_agents.py` (with agents)
4. Move completed items to “Complete” in this file and keep the README roadmap short
