> Japanese: [../../ja/docs/architecture.md](../../ja/docs/architecture.md)

# Architecture — ECLSS (Environmental Control and Life Support System) Resilience Loop

Reference for layer structure, execution flow, and agent design in a simulation that mocks **ECLSS** (Environmental Control and Life Support System) and **EPS** (Electrical Power System).

> Usage instructions: [README.md](../README.md). Incomplete features: [development-plan.md](development-plan.md).

---

## Terminology (first use)

| Abbrev. | English name | Meaning in this repository |
| --- | --- | --- |
| **ECLSS** | Environmental Control and Life Support System | **Life-support equipment** required for crew survival (CO2 removal, air circulation, environmental control). Not a physical lab apparatus; the closed-environment plant is represented as a graph |
| **EPS** | Electrical Power System | Space-station generation, storage, and distribution. Supplies power to loads such as ECLSS |
| **SARJ** | Solar Alpha Rotary Joint | Solar-array pointing and generation. Mocked as solar voltage via `MockSarj` in the MVP |
| **BCDU** | Battery Charge/Discharge Unit | Battery charge/discharge unit. Discharges to support ECLSS on `request_eps_boost` |
| **MBSU** | Main Bus Switching Unit | Main bus switching. A real EPS component (not individually implemented in this MVP mock) |
| **DDCU** | Direct Current-to-Direct Current Converter Unit | DC-DC conversion. A real EPS component (not individually implemented in this MVP mock) |

---

## Mission

Verify, in a reproducible Python environment, that an **agent team can detect and respond to anomalies in space-station life-support equipment (ECLSS)** and **propose design changes afterward**.

Rather than high-fidelity numerical physics or 3D graphics, the priorities are:

- **Structured agent relationships** (homogeneous team, representative action, deliberation logs)
- **Simulator API contract** (`SimulatorProtocol`, JSONL, ROS2-style topics)
- **SSOS mock** (connection to real orbital software is a separate phase)

This repository runs on a **simulator that mocks Space Station OS (SSOS)**. It does not connect to real ROS2 topics on hardware.

---

## System overview

```text
┌─────────────────────────────────────────────────────────────┐
│  tools/          Streamlit dashboard, (future) CLI              │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  scenario/       runner, YAML, ScrubberDegradationTeam        │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  environment/    StationSimulator, MockEclssSimulator, EPS    │
│                  SsosAdapter (stub)                           │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  core/           PersonaAgent, Team, memory, Ollama client    │
└─────────────────────────────────────────────────────────────┘

  integrations/one_piece/  ← provenance export at scenario end
```

**Dependency direction** (imports are one-way only):

```text
tools → scenario → environment → core
src/integrations/   (invoked from scenario)
```

---

## Layer responsibilities

| Layer | Path | Responsibility |
| --- | --- | --- |
| Core | `src/core/` | Persona, Team ABC, memory (`DiscourseBuffer` / `AgentMemory`), LLM client, event log |
| Environment | `src/environment/` | `SimulatorProtocol`, ECLSS life-support plant, EPS (SARJ/BCDU mock), SSOS topic definitions, adapter stub |
| Scenario | `src/scenario/` | Scenario YAML, registry, `ScrubberDegradationTeam` |
| Experiments | `src/experiments/results/` | Run output (gitignore recommended) |
| Tools | `src/tools/dashboard/` | Streamlit UI |
| Integrations | `src/integrations/one_piece/` | Provenance JSON export |

---

## Implementation status

| Feature | Status | Main artifacts |
| --- | --- | --- |
| Repository layout | Done | `src/` layers, `core/agents/`, `scenario/` |
| Simulator | Done | `SimulatorProtocol`, `StationSimulator`, `MockEclssSimulator` |
| Baseline scenario | Done | `scrubber_degradation/scenario.yaml`, regression tests |
| labeled_rule_base team | Done | `policy`-driven recovery commands, post-run `design_proposals.json` |
| llm team | Done | Ollama, one deliberation round + representative action |
| EPS coupling | Done | `eps_telemetry.jsonl`, BCDU discharge, `request_eps_boost` |
| Dashboard | Done | Overview, Step replay, 2-run compare, design proposal graph |
| One Piece provenance | Partial | Runtime **recovery** only. Post-run design proposals not exported |
| CLI | Not started | [development-plan.md](development-plan.md) |
| Real SSOS adapter | Stub | `SsosAdapter` |

---

## Execution flow (scrubber_degradation)

```text
scenario.yaml + agents.yaml
        │
        ▼
  scenario/runner.py → ScrubberDegradationScenario
        │
        ├─ build_simulator() → StationSimulator(ECLSS + EPS)
        ├─ build_team()      → ScrubberDegradationTeam (mode ≠ none)
        │
        ▼
  for step in 1..N:
    1. sim.step()                         → TelemetrySnapshot
    2. log telemetry, health, design_state (before agent action)
    3. team.run_step(sim, obs)            → messages, commands
    4. team.apply_outcome(sim, outcome)   → apply_command only (no design changes)
    5. log messages, sim events
        │
        ▼
  team.propose_post_run_design()          → design_proposals.json
  export_run_provenance()               → provenance.jsonl
  write summary.json
        │
        ▼
  experiments/results/<run_id>/
```

### Important design separation

| Phase | What happens | Output |
| --- | --- | --- |
| **Runtime** | Temporary recovery commands only (fan, load, EPS, bypass) | `events.jsonl` (`recovery_applied`), `messages.jsonl` |
| **After run** | **Proposal** of permanent design (not applied to simulator) | `design_proposals.json` |

`design_state.jsonl` is the topology **before agent action** at each step. Nodes/edges do not change at runtime, so the same graph continues for all steps (temporary parameter changes appear on the telemetry side).

The dashboard **After (if proposals applied)** is a preview that **virtually applies** `design_proposals.json` to the baseline; it is not a simulation result.

---

## Agent modes (`agents.mode`)

`agents.mode` in `scenario.yaml`. When not `none`, `agents.yaml` is loaded.

| Mode | Team | Runtime | Post-run design | Tests |
| --- | --- | --- | --- | --- |
| `none` | none | Life-support sim only (no agents) | none | `test_scrubber_baseline.py` |
| `labeled_rule_base` | N homogeneous | `policy` thresholds for recovery | rule-based bypass proposal | `test_scrubber_with_agents.py` |
| `llm` | N homogeneous | LLM deliberation + action | LLM proposes `changes` | same (Fake LLM) |
| `base` | — | not implemented | — | BL-001 |

### Homogeneous engineer team

- IDs: `engineer_1` … `engineer_N` (`team.count`, default 4)
- **Representative action**: `engineer_{(step-1) % N}` issues recovery commands for that step
- **Post-run design**: the representative at the final step runs `propose_post_run_design()`

Rather than rigid roles (fixed operator / design_engineer), the executor rotates each step. Details: [memo/homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md).

### labeled_rule_base

Only this mode reads `policy` from `agents.yaml`. The LLM code path does not read `policy`.

| Behavior | Trigger (summary) |
| --- | --- |
| alert | CO2 ≥ `co2_recovery_ppm` (default 1000) |
| diagnosis | `anomaly_flags` non-empty |
| `set_fan_speed` | CO2 ≥ threshold, not yet applied |
| `reduce_load` | power critical, not yet applied |
| `request_eps_boost` | power critical and EPS support steps remaining = 0 |
| `enable_bypass` | CO2 ≥ threshold, fan already applied, bypass not yet |
| post-run bypass proposal | peak CO2 ≥ threshold or `anomaly_seen` |

### llm

LLM calls per step (up to N+1):

1. **Deliberation** — all N agents produce `message` + `reasoning` (`deliberation_phase: deliberation`)
2. **Action** — representative produces `commands` array (`deliberation_phase: action`)
3. **Post-run** (once after run) — representative writes `changes` to `design_proposals.json`

**Situation injection** (prompt):

- `### Telemetry` — CO2, efficiency, power margin, EPS support, and other numeric values
- `### World state` — descriptive safe / warning / critical health
- **`policy` thresholds are not included** (do not leak rule answers)

**Metadata** (`messages.jsonl`): `decision_source` (`llm` / `llm_parse_fail` / `llm_no_action`), `parse_status`, `raw_response_excerpt`, etc.

---

## Life support (ECLSS) and power (EPS) stack

```text
StationSimulator
  ├─ MockEclssSimulator   Life-support plant (CO2, scrubber, fan, bypass, load)
  └─ EpsStack             EPS (Electrical Power System)
       ├─ MockSarj        SARJ equivalent — solar voltage (orbital mock)
       └─ MockBcdu        BCDU equivalent — charge/discharge, request_eps_boost response
```

Real ISS-class EPS also includes **MBSU** (Main Bus Switching Unit) and **DDCU** (Direct Current-to-Direct Current Converter Unit). This MVP focuses on SARJ/BCDU coupling required for the scrubber scenario.

On successful `request_eps_boost`, `eps_support_w` is added to the ECLSS power margin for a fixed number of steps. `eps_telemetry.jsonl` records BCDU `mode` (`discharging`, etc.).

### Health thresholds (`compute_health_metrics`)

Defined in `src/environment/eclss_ops/telemetry.py` (`CO2_SAFE_PPM`, `CO2_WARNING_PPM`, `POWER_LOW_W`, `POWER_CRITICAL_W`).

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 800 | 800 to < 1200 | ≥ 1200 |
| Power margin (W) | > 0 | 0 to < −150 | ≤ −150 |

`overall` is the **worse** of CO2 and power (safe < warning < critical).

**Note**: Agent recovery policy (`co2_recovery_ppm: 1000` in `agents.yaml`, etc.) is separate from health thresholds. labeled_rule_base fires commands on policy thresholds; health is recorded independently from telemetry in `health_metrics.jsonl`.

---

## Output layout

`src/experiments/results/<run_id>/`

| File | Contents |
| --- | --- |
| `telemetry.jsonl` | Life-support telemetry every step |
| `health_metrics.jsonl` | CO2 / power / overall |
| `eps_telemetry.jsonl` | SARJ + BCDU (with `StationSimulator`) |
| `design_state.jsonl` | Topology at step start (invariant) |
| `events.jsonl` | Anomalies, recovery application |
| `messages.jsonl` | Agent utterances (labeled / llm) |
| `design_proposals.json` | Post-run permanent design proposal |
| `provenance.jsonl` | One Piece compatible (currently mainly EPS recovery) |
| `summary.json` | Full KPI set |

Default run IDs (`scenario.yaml`):

| mode | run_id |
| --- | --- |
| `none` | `scrubber_degradation_baseline` |
| `labeled_rule_base` | `scrubber_degradation_labeled_rule_base` |
| `llm` | `scrubber_degradation_llm` |

Schema: [api-contracts.md](api-contracts.md). Scenario narrative: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md).

---

## Dashboard (`src/tools/dashboard/app.py`)

| View | Function |
| --- | --- |
| **Overview** | Single run or two runs side by side. Telemetry plots, step slider, topology, design proposal preview |
| **Step replay** | Event timeline, cached plots + step vertical line, utterance / reasoning feed |
| **Run comparison** (when comparing) | Metrics table with run names, Δ (primary − compare), recovery command comparison |

Sidebar: run selection, `Compare with another run`, Overview / Step replay toggle.

Screenshots: [README.md](../README.md#dashboard-at-a-glance).

---

## External systems

| System | MVP |
| --- | --- |
| SSOS | Python mock. `SsosAdapter` is a stub |
| LLM | Ollama (`core/llm/ollama.py`), default `gemma4:e4b` |
| One Piece | `provenance.jsonl` only. Web UI and post-run design export not yet |

---

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Minimum regression set:

```bash
pytest tests/scenario/test_scrubber_baseline.py -q
pytest tests/scenario/test_scrubber_with_agents.py -q
```

LLM live runs require Ollama. CI validates the `llm` path with Fake LLM.

Next implementation: [development-plan.md](development-plan.md).
