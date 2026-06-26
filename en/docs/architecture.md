> Japanese: [../../ja/docs/architecture.md](../../ja/docs/architecture.md)

# Architecture — ECLSS Resilience Loop

Reference for layer structure, execution flow, and agent design. API schemas: [api-contracts.md](api-contracts.md). Scenario narratives: see each scenario document.

> Usage: [README.md](../README.md) · Incomplete features: [development-plan.md](development-plan.md)

---

## Mission

Verify in a reproducible environment that an **agent team can detect and respond to anomalies in space-station life-support equipment (ECLSS)** and **propose design changes afterward**.

Priorities:

- **Structured agent relationships** (homogeneous team, representative action, deliberation logs)
- **Clear API contracts** (backend protocols, JSONL)
- **Two scenario tracks** — independent backends and output schemas (do not mix)


| | `scrubber_degradation` | `ssos_eclss_loop` |
| --- | --- | --- |
| Narrative | [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | [scenario-ssos-eclss-loop.md](scenario-ssos-eclss-loop.md) |
| Backend | `SimulatorProtocol` / `StationSimulator` | `EclssBackend` / `Ros2EclssBridge` |
| Team | `ScrubberDegradationTeam` | `SsosEclssLoopTeam` |
| Rep IDs | `engineer_*` | `eclss_operator_*` |
| Runtime | Recovery commands | Operational commands (ARS/OGS, etc.) |
| Post-run | Scrubber topology | `ssos_graph` |
| Environment | Host Python only | mock or SSOS Docker |


---

## Shared — layers and dependencies

### System overview

```text
┌─────────────────────────────────────────────────────────────┐
│  tools/          Streamlit dashboard, ea-loop (Docker)      │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  scenario/       scrubber_degradation  |  ssos_eclss_loop   │
│                  ScrubberDegradationTeam | SsosEclssLoopTeam│
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
    ┌───────────▼──────────┐      ┌───────────▼──────────────┐
    │ environment/         │      │ environment/ssos/        │
    │ StationSimulator     │      │ EclssBackend             │
    │ MockEclss + EPS mock │      │ Ros2EclssBridge          │
    └───────────┬──────────┘      └───────────┬──────────────┘
                │                             │
                └─────────────┬───────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│  core/           PersonaAgent, Team ABC, memory, Ollama     │
└─────────────────────────────────────────────────────────────┘

  integrations/one_piece/  ← provenance export at scenario end
```

**Dependency direction** (imports are one-way only):

```text
tools → scenario → environment → core
src/integrations/   (invoked from scenario)
```

### Layer responsibilities

| Layer | Path | Responsibility |
| --- | --- | --- |
| Core | `src/core/` | Persona, Team ABC, memory, LLM client |
| Environment | `src/environment/` | scrubber: `SimulatorProtocol`, EPS mock. ssos: `EclssBackend`, `graph_rewire` |
| Scenario | `src/scenario/` | Per-scenario YAML, Team, `design_proposals` |
| Experiments | `src/experiments/results/` | Run output |
| Tools | `src/tools/dashboard/` | Streamlit (view branches on `summary.scenario`) |
| Integrations | `src/integrations/one_piece/` | provenance JSON |

### Agent team (shared across both tracks)

Extends `Team` ABC. **Homogeneous N agents + representative action**, not rigid roles.

| Concept | Description |
| --- | --- |
| `team.count` | Operator count (scrubber default 4, ssos default 3) |
| deliberation | llm: one round for all. labeled: rule-driven fixed messages |
| action rep | Representative issues commands each step via `(step-1) % N` |
| post-run rep | Representative at final step outputs `design_proposals.json` |
| Design separation | **No permanent graph changes at runtime**. Post-run proposals only |

Details: [memo/homogeneous_agent_team_plan.md](../memo/homogeneous_agent_team_plan.md).

### `agents.mode` (shared values)

| Mode | Meaning |
| --- | --- |
| `none` | Backend only (no agents) |
| `labeled_rule_base` | `policy` / threshold driven |
| `llm` | Ollama deliberation + representative action |
| `base` | Not implemented ([BL-001](../memo/backlog.md)) |

**Do not include `policy` thresholds in LLM prompts** (fair comparison experiments).

### Implementation status

| Feature | scrubber | ssos |
| --- | --- | --- |
| Scenario + team | ✅ frozen | ✅ Phase 0–7 |
| labeled / llm | ✅ | ✅ |
| Dashboard | ✅ ppm / EPS / topology | ✅ storage / operational TL |
| provenance | ✅ EPS recovery | ✅ operational commands |
| Post-run proposals → provenance | 📋 pending | 📋 pending |
| CLI integration | 📋 pending | 📋 pending |
| launch remap (Phase 8) | — | 📋 [BL-003](../memo/backlog.md) |

---

## scrubber_degradation

CO₂ scrubber anomaly on Python mock. **Frozen** — new features go to `ssos_eclss_loop`.

### Terminology

| Abbrev. | Description |
| --- | --- |
| **ECLSS** | Life-support plant (scrubber, manifold, cabin) |
| **EPS** | Generation, storage, distribution. Supports ECLSS via `request_eps_boost` |
| **SARJ** / **BCDU** | Solar generation / battery discharge mocks (`MockSarj` / `MockBcdu`) |

### Execution flow

```text
scenario.yaml + agents.yaml
        │
        ▼
  scenario/runner.py → ScrubberDegradationScenario
        │
        ├─ build_simulator() → StationSimulator(ECLSS + EPS)
        ├─ build_team()      → ScrubberDegradationTeam
        │
        ▼
  for step in 1..N:
    1. sim.step()                    → TelemetrySnapshot
    2. log telemetry, health, design_state
    3. team.run_step(sim, obs)       → RecoveryCommand
    4. team.apply_outcome(sim, ...)  → apply_command only
    5. log messages, events
        │
        ▼
  propose_post_run_design() → design_proposals.json
  export_run_provenance()   → recovery records
```

### Runtime vs post-run

| Phase | Content | Output |
| --- | --- | --- |
| Runtime | Recovery commands (fan, load, EPS, bypass) | `recovery_applied` |
| Post-run | Scrubber topology proposal (not applied to simulator) | `design_proposals.json` |

`design_state.jsonl` topology is invariant during the run. Dashboard After preview is a **virtual apply** of proposals.

### ECLSS + EPS stack

```text
StationSimulator
  ├─ MockEclssSimulator   CO₂ ppm, scrubber, fan, bypass
  └─ EpsStack
       ├─ MockSarj
       └─ MockBcdu          request_eps_boost response
```

Topology:

```text
  cabin ──flow──► manifold ──flow──► scrubber ──flow──► cabin
                                        ▲
                                        │ power
                                   power_bus
```

### Health (ppm / power)

`compute_health_metrics()` — `src/environment/eclss_ops/telemetry.py`

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ (ppm) | < 800 | 800 to < 1200 | ≥ 1200 |
| Power margin (W) | > 0 | 0 to < −150 | ≤ −150 |

`policy.co2_recovery_ppm` (1000, etc.) are recovery triggers, separate from health bands.

### Agents

| `agents.mode` | Runtime | Post-run | Tests |
| --- | --- | --- | --- |
| `none` | Sim only | — | `test_scrubber_baseline.py` |
| `labeled_rule_base` | policy-driven recovery | bypass proposal | `test_scrubber_with_agents.py` |
| `llm` | deliberation + commands | LLM changes | same (Fake LLM) |

#### labeled_rule_base

| Behavior | Trigger |
| --- | --- |
| `set_fan_speed` | CO₂ ≥ `co2_recovery_ppm` |
| `reduce_load` / `request_eps_boost` | power critical |
| `enable_bypass` | high CO₂ + fan already applied |
| Post-run bypass proposal | peak CO₂ high or `anomaly_seen` |

#### llm

1. Deliberation (all N) → 2. Action (representative `commands`) → 3. Post-run (`changes`)

Prompt: `### Telemetry` + `### World state` (no policy)

### Output and dashboard

| Unique files | Content |
| --- | --- |
| `eps_telemetry.jsonl` | SARJ + BCDU |
| `events.jsonl` | anomaly, `recovery_applied` |

| View | Content |
| --- | --- |
| Overview | CO₂ ppm, power, EPS, topology Before/After |
| Step replay | Recovery timeline, reasoning |

run ID: `scrubber_degradation_{baseline|labeled_rule_base|llm}`

---

## ssos_eclss_loop

Real ROS2 ECLSS inside SSOS Docker (or `LoopMockEclssBackend`). **Does not use `SimulatorProtocol`.**

### Terminology

| Abbrev. | Description |
| --- | --- |
| **ARS** | Air Revitalisation — CO₂ removal (`air_revitalisation`) |
| **OGS** | Oxygen Generation — O₂ generation (`oxygen_generation`) |
| **WRS** | Water Recovery — water recovery (`water_recovery_systems`) |

### Execution flow

```text
scenario.yaml + agents.yaml (+ ssos_graph.rewires optional)
        │
        ▼
  scenario/ssos_eclss_loop/scenario_run.py
        │
        ├─ build_eclss_backend() → LoopMockEclssBackend | Ros2EclssBridge(topic_remap)
        ├─ build_team()            → SsosEclssLoopTeam
        │
        ▼
  for step in 1..N:
    1. backend.poll_telemetry()      → EclssTelemetrySnapshot
    2. log telemetry, health, design_state
    3. team.run_step(backend, obs)  → EclssOperationalCommand
    4. team.apply_outcome(...)      → Action/Service, re-arm logic
    5. log messages, operational events
        │
        ▼
  propose_post_run_design() → design_proposals.json (ssos_graph)
  export_run_provenance()   → operational records
```

### Runtime vs post-run

| Phase | Content | Output |
| --- | --- | --- |
| Runtime | ARS/OGS/WRS operational commands | `operational_applied` |
| Post-run | `action_profile` / `graph_rewire` proposals | `design_proposals.json` |

**graph_rewire (Phase 7)**: client `topic_remap` on next run's `Ros2EclssBridge`. Launch remap (Phase 8) is backlog.

### ECLSS stack

```text
SsosEclssLoopTeam
  └─ EclssBackend
       ├─ LoopMockEclssBackend   host dev (simple storage dynamics)
       └─ Ros2EclssBridge        SSOS Docker — ros2 CLI
            └─ topic_remap       graph_rewire
```

```text
  metabolic CO₂ ──► /co2_storage ──► ARS
  /o2_storage ◄── OGS ◄── request_co2 (Sabatier)
  /wrs/product_water_reserve ◄── WRS
```

`run_ssos_eclss_loop.sh` / `ea-loop` for container runs. ECLSS headless startup is required.

### Health (storage kg)

`compute_eclss_storage_health()` — `src/scenario/ssos_eclss_loop/health.py`

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO₂ (kg) | < 1500 | 1500 to < 2200 | ≥ 2200 |
| O₂ (kg) | > 450 | 337.5 to 450 | ≤ 337.5 |
| Product water (L) | > 50 | 25 to 50 | ≤ 25 |

`thresholds.co2_storage_high_kg`, etc. are operational triggers, separate from health bands.

### Agents

| `agents.mode` | Runtime | Post-run | Tests |
| --- | --- | --- | --- |
| `none` | poll only | — | `test_ssos_eclss_loop_scenario.py` |
| `labeled_rule_base` | thresholds → ARS/OGS | `ssos_graph` | `test_ssos_eclss_loop_team.py` |
| `llm` | deliberation + operational | LLM changes | same |

#### labeled_rule_base

`thresholds` (scenario.yaml) + `policy` profile (agents.yaml). Thresholds merged via `merge_labeled_policy_from_thresholds()`.

| Behavior | Trigger |
| --- | --- |
| `air_revitalisation` | CO₂ ≥ high, ARS not yet dispatched |
| `request_co2` | O₂ ≤ low, before OGS (policy default ON) |
| `oxygen_generation` | O₂ ≤ low, OGS not yet dispatched |
| re-arm | retry next step if no improvement |

#### llm

Same pattern as scrubber. Prompt includes storage kg and health state (no policy).

### Output and dashboard

| Unique fields | Content |
| --- | --- |
| `summary.backend` | `mock` / `ros2` |
| `summary.operational_command_count` | operational command count |
| `events.jsonl` | `operational_applied` |

**Not in ssos from scrubber**: `eps_telemetry.jsonl`, ppm-based KPIs.

| View (`ssos_views.py`) | Content |
| --- | --- |
| Overview | storage kg, health cards, 2-run compare |
| Step replay | operational timeline, `ssos_graph` proposals |

run ID: `ssos_eclss_loop_{baseline|labeled_rule_base|llm}`

Connection details: [memo/ssos_eclss_physical_phenomena_overview.md](../memo/ssos_eclss_physical_phenomena_overview.md).

---

## External systems

| System | Track | Status |
| --- | --- | --- |
| Python mock ECLSS + EPS | scrubber | ✅ `StationSimulator` |
| SSOS live ECLSS | ssos | ✅ `Ros2EclssBridge` |
| SSOS EPS (scrubber power) | scrubber | ✅ `Ros2EpsBridge` |
| Ollama | both | ✅ container uses `host.docker.internal` |
| One Piece Web UI | — | out of scope |

---

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Regression:

```bash
# scrubber
pytest tests/scenario/test_scrubber_baseline.py tests/scenario/test_scrubber_with_agents.py -q
# ssos
pytest tests/scenario/test_ssos_eclss_loop*.py tests/environment/test_graph_rewire*.py -q
```

SSOS container E2E: `./scripts/run_ssos_eclss_loop.sh`, `./scripts/run_graph_rewire_e2e.sh`

Next implementation: [development-plan.md](development-plan.md) · API details: [api-contracts.md](api-contracts.md)
