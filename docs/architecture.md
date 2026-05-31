# Architecture

## Mission

Multi-agent simulation for ECLSS anomaly detection through design change (resilience loop). The platform prioritizes **structured agent relationships** and **simulator API contracts** over high-fidelity physics or graphics.

## Implementation status

| Capability | Status | Key artifacts |
| --- | --- | --- |
| Repository layout | Done | `src/` layers, `core/`, `materials/2d-bar-simulation/` |
| Simulator protocol | Done | `SimulatorProtocol`, `MockEclssSimulator`, `docs/api-contracts.md` |
| Baseline scenario | Done | `scrubber_degradation/scenario.yaml`, `scenario/runner.py`, baseline tests |
| Labeled agent team | Done | Rule-based 4 roles, `messages.jsonl`, recovery + design change |
| LLM shadow mode | Done / evolving | `agents.mode: labeled_shadow` — shadow chat, rule actions |
| One Piece provenance | Planned | `integrations/one_piece/` |
| Dashboard & CLI | Planned | Streamlit dashboard, `tools/cli.py` |

## Dependency direction

Imports must flow in one direction only:

```text
tools → scenario → environment → core
materials/          (isolated — not imported by new code)
integrations/       (called from scenario/tools only)
```

| Layer | Responsibility |
| --- | --- |
| `src/core/` | Agent base, simulation loop, LLM clients, event logging |
| `src/environment/` | Simulator boundary (`SimulatorProtocol`, SSOS mock/adapter, ECLSS ops) |
| `src/scenario/` | Scenario YAML, runner, scenario-specific agent teams |
| `src/experiments/` | Run configs and results (results gitignored) |
| `src/tools/` | CLI and Streamlit dashboard (planned) |
| `src/materials/` | Legacy 2D bar/fire sim — reference only |
| `integrations/one_piece/` | Design-change provenance JSON SSOT (planned) |

## Two simulation lines

1. **Legacy (materials)**: `src/materials/2d-bar-simulation/` — LLM bar/fire sim. Run from that directory; not part of the ECLSS stack.
2. **ECLSS (new)**: `src/scenario/scrubber_degradation/` — virtual ops anomaly → recovery → design change via Mock SSOS.

## Run flow (scrubber_degradation)

```text
scenario.yaml + agents.yaml
        │
        ▼
  scenario/runner.py
        │
        ├─ build_simulator() → MockEclssSimulator
        ├─ build_agent_team()  (if agents.mode ≠ none)
        │
        ▼
  for each step:
    1. sim.step()                    → telemetry
    2. log telemetry, health, design_state (pre-agent snapshot)
    3. team.run_step()               → messages, commands, design_changes
    4. team.apply_outcome()          → sim.apply_command / apply_design_change
    5. log messages + new events
        │
        ▼
  experiments/results/<run_id>/*.jsonl + summary.json
```

**Timing note:** `design_state.jsonl` at step *N* reflects topology **before** agent actions in that step. A design change applied during step 35 appears in `events.jsonl` at step 35 and in `design_state.jsonl` from step 36 onward.

## Agent modes (`agents.mode`)

Configured in `scenario.yaml`; role thresholds in `agents.yaml` when mode ≠ `none`.

| Mode | Physics | Actions | Messages | Tests |
| --- | --- | --- | --- | --- |
| `none` | Mock only | — | — | `test_scrubber_baseline.py` (required green) |
| `labeled` | Mock | Rule-based 4 roles | Rule messages, `decision_source: rule` | `test_scrubber_with_agents.py` |
| `labeled_shadow` | Mock | Same rules as `labeled` | Rule + LLM shadow per role, `decision_source: llm_shadow` | shadow-mode tests (when present) |
| `base` | — | Not implemented | BL-001 backlog | — |

Roles are **scenario-specific labels** for `scrubber_degradation` only (`ScrubberDegradationTeam`). Not a generic role framework. See [memo/backlog.md](../memo/backlog.md) BL-001 for unlabeled emergent-role research.

### Labeled roles

| Role | Responsibility | Rule trigger (summary) |
| --- | --- | --- |
| Monitor | Alert | CO2 ≥ 900 ppm |
| Diagnostician | Diagnose | `anomaly_flags` present |
| Operator | Recovery commands | CO2 ≥ 1000 → fan boost; power critical → load shed; then bypass |
| DesignEngineer | Permanent design change | step ≥ 35 and CO2 ≥ 1000 → add bypass edge |

### labeled_shadow mode

- **Actions remain rule-based** (deterministic recovery path unchanged).
- Each step, Ollama generates **parallel shadow messages** per role (`llm_shadow_*` message types).
- Shadow messages carry `decision_source: llm_shadow`, `parse_status`, `parse_error`, `raw_response_excerpt`.
- LLM config in `agents.yaml` under `llm:` (defaults to `llama3.2`, short timeout).
- Requires Ollama running locally for shadow runs; baseline and `labeled` do not.

## Output layout

Each run writes to `src/experiments/results/<run_id>/`:

| File | When |
| --- | --- |
| `telemetry.jsonl` | Every step |
| `health_metrics.jsonl` | Every step |
| `design_state.jsonl` | Every step (pre-agent topology) |
| `events.jsonl` | Anomalies, recovery commands, design changes |
| `messages.jsonl` | Agent modes with team (`labeled`, `labeled_shadow`) |
| `summary.json` | Once at end |

Default run IDs (from `scenario.yaml`):

- `scrubber_degradation_baseline` — `agents.mode: none`
- `scrubber_degradation_labeled` — `labeled`
- `scrubber_degradation_labeled_shadow` — `labeled_shadow`

Schema details: [api-contracts.md](api-contracts.md). Scenario narrative: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md).

## External systems

| System | MVP approach |
| --- | --- |
| SSOS | Mock adapter (`environment/ssos/mock_eclss.py`); real ROS2 via `SsosAdapter` stub |
| LLM | Ollama via `core/llm/ollama.py`; used in `labeled_shadow` mode only |
| One Piece | JSON provenance via `integrations/one_piece/` (planned); web UI deferred |

See [one-piece-integration.md](one-piece-integration.md) for the provenance plan.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Regression guards:

```bash
pytest tests/scenario/test_scrubber_baseline.py -q   # physics-only, always
pytest tests/scenario/test_scrubber_with_agents.py -q  # labeled recovery
```
