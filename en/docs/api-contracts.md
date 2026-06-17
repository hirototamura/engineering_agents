> Japanese: [../../ja/docs/api-contracts.md](../../ja/docs/api-contracts.md)

# API Contracts — SimulatorProtocol and Event Logs

Reference for **ECLSS** (Environmental Control and Life Support System) and **EPS** (Electrical Power System) simulator boundaries, recovery commands, and JSONL schemas. When you change the protocol or log format, **update this document at the same time**.

> Scenario narrative: [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md)

---

## SimulatorProtocol

Implementations:

| Class | Purpose |
| --- | --- |
| `StationSimulator` | **Default** — ECLSS + EPS |
| `MockEclssSimulator` | Plant only (unit tests) |
| `SsosAdapter` | Future real SSOS bridge (stub) |

| Method | Returns | Description |
| --- | --- | --- |
| `step()` | `TelemetrySnapshot` | Advance the life-support plant by one tick |
| `apply_command(cmd)` | `CommandResult` | Temporary recovery action |
| `apply_design_change(change)` | `DesignState` | Permanent change (**not used at runtime in the current scenario**) |
| `get_topology()` | `TopologyGraph` | Nodes / edges |
| `get_design_parameters()` | `dict[str, float]` | Mutable parameters |
| `get_design_state()` | `DesignState` | Topology + parameters |
| `inject_anomaly(spec)` | `None` | Anomaly schedule |

---

## scenario.yaml configuration

`src/scenario/runner.py` builds `StationSimulator` from `scenario.yaml`. Overrides passed to `run_scenario(..., overrides={...})` are deep-merged into the loaded YAML.

### design_parameters

Mutable ECLSS plant coefficients (`DesignStateManager`). Omitted keys fall back to `default_parameters()` in `src/environment/eclss_ops/design_state.py`.

| Key | Default | Description |
| --- | --- | --- |
| `scrubber_base_efficiency` | 0.95 | Nominal scrubber removal efficiency |
| `co2_production_ppm_per_step` | 32.0 | CO2 rise per step at full metabolic load |
| `scrub_rate_coefficient` | 0.06 | Scrub rate scaling with fan speed |
| `fan_power_w` | 80.0 | Additional power draw at full fan |
| `bypass_power_w` | 40.0 | Power draw when temporary bypass is enabled |
| `bypass_flow_bonus` | 0.15 | Flow bonus from temporary bypass |
| `permanent_bypass_power_w` | 20.0 | Power draw for a permanent bypass edge (post-run proposals) |
| `load_reduction_factor` | 0.6 | CO2 production multiplier after `reduce_load` |
| `base_power_draw_w` | 200.0 | Baseline ECLSS power draw |
| `eps_support_duration_steps` | 5.0 | Steps that `request_eps_boost` support lasts (`StationSimulator` reads this from design parameters) |

### eps (optional)

Passed to `build_eps_stack()`. When omitted, SARJ uses `beta_angle_deg: 45.0` and no eclipse window.

```yaml
eps:
  sarj:
    beta_angle_deg: 45.0
    eclipse_window: [10, 15]   # optional inclusive step range; solar voltage drops during eclipse
```

| Key | Default | Description |
| --- | --- | --- |
| `eps.sarj.beta_angle_deg` | 45.0 | Solar beta angle for generation model (`MockSarj`) |
| `eps.sarj.eclipse_window` | none | Two-element `[start_step, end_step]`; steps inside use eclipse voltage |

`eps_boost_w` in `agents.yaml` `policy` is separate — it sets the watts requested by `request_eps_boost`, not the SARJ eclipse schedule.

---

## TelemetrySnapshot

One line of `telemetry.jsonl`.

```json
{
  "step": 20,
  "co2_ppm": 1240.5,
  "scrubber_efficiency": 0.72,
  "power_margin_w": 45.0,
  "fan_speed": 0.7,
  "bypass_enabled": false,
  "load_reduced": false,
  "eps_support_w": 120.0,
  "eps_support_steps_remaining": 4,
  "anomaly_flags": ["scrubber_degradation"]
}
```

| Field | Description |
| --- | --- |
| `co2_ppm` | Habitable-space CO2 concentration |
| `scrubber_efficiency` | Effective removal efficiency (degraded under anomaly) |
| `power_margin_w` | ECLSS net power margin (positive = surplus, negative = deficit) |
| `eps_support_w` | Temporary support watts from EPS |
| `eps_support_steps_remaining` | Remaining support steps |
| `anomaly_flags` | List of active anomaly names |

---

## RecoveryCommand

Temporary operation applied at runtime via `apply_command`.

```json
{
  "kind": "set_fan_speed",
  "value": 1.0,
  "issued_by": "engineer_2"
}
```

| `kind` | `value` type | Description |
| --- | --- | --- |
| `set_fan_speed` | float 0–1 | Fan speed |
| `enable_bypass` | bool | Enable temporary bypass |
| `reduce_load` | bool | Reduce metabolic load |
| `request_eps_boost` | float W (0, 500] | Request EPS discharge support |

`issued_by` is the action representative engineer ID (`engineer_*`) or legacy `operator`.

---

## DesignChange (protocol type)

Permanent change understood by the simulator. **In the current scrubber_degradation flow it is not applied at runtime.** Post-run proposals are expressed in `design_proposals.json`; the dashboard applies them virtually for preview.

```json
{
  "kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "proposed_by": "engineer_4"
}
```

| `kind` | Purpose |
| --- | --- |
| `add_edge` | New edge (flow / bypass / power) |
| `add_node` | New node (valve, electrical, etc.) |
| `set_parameter` | Design parameter change |

---

## design_proposals.json (post-run proposal)

One file after the run ends. The simulation result topology is **not changed**.

```json
{
  "proposed_by": "engineer_2",
  "decision_source": "rule",
  "message": "Propose permanent bypass plumbing between manifold and scrubber.",
  "reasoning": "Repeated anomaly and high CO2 during the run; ...",
  "changes": [
    {
      "change_kind": "add_edge",
      "payload": {
        "node_a": "manifold",
        "node_b": "scrubber",
        "kind": "bypass"
      }
    }
  ],
  "baseline_topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}, "..."],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}, "..."]
  },
  "parse_notes": []
}
```

| Field | Description |
| --- | --- |
| `proposed_by` | Action rep at the final step |
| `decision_source` | `rule` or `llm` |
| `changes` | List of proposed permanent changes |
| `baseline_topology` | Graph at run end (before changes) |
| `parse_notes` | LLM parse warnings (optional) |

Corresponds to `design_proposals_path` and `design_proposal_count` in `summary.json`.

---

## Health thresholds

`health_metrics.jsonl` — `compute_health_metrics()` (`src/environment/eclss_ops/telemetry.py`):

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
```

| Constant | Value |
| --- | --- |
| `CO2_SAFE_PPM` | 800 |
| `CO2_WARNING_PPM` | 1200 |
| `POWER_LOW_W` | 0 |
| `POWER_CRITICAL_W` | −150 |

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 800 | 800 to < 1200 | ≥ 1200 |
| Power margin (W) | > 0 | 0 to < −150 | ≤ −150 |
| `overall` | both safe | worse of the two is warning | worse of the two is critical |

Agent `policy.co2_recovery_ppm` (default 1000), etc. are **recovery command triggers** and are separate from the health bands in the table above.

---

## Agent modes

| `agents.mode` | Team | Messages | Runtime commands | Post-run proposal |
| --- | --- | --- | --- | --- |
| `none` | — | — | — | — |
| `labeled_rule_base` | `ScrubberDegradationTeam` | `decision_source: rule` | policy-driven | rule |
| `llm` | same as above | `llm` / `llm_parse_fail` / `llm_no_action` | LLM `commands` | llm |

Future: `base` (emergent roles) — [memo/backlog.md](../memo/backlog.md) BL-001.

### messages.jsonl — rule example

```json
{
  "step": 33,
  "from_role": "engineer_2",
  "to_role": "team",
  "message": "CO2 at 1016 ppm exceeds recovery band 1000 ppm.",
  "message_type": "alert",
  "reasoning": "Telemetry threshold crossed.",
  "decision_source": "rule"
}
```

### messages.jsonl — LLM example

```json
{
  "step": 17,
  "from_role": "engineer_1",
  "to_role": "team",
  "message": "EPS boost critical for CO2 reduction.",
  "message_type": "recovery_command",
  "reasoning": "Power margin remains low, bypass ineffective.",
  "decision_source": "llm",
  "deliberation_phase": "action",
  "parse_status": "ok",
  "parse_error": null,
  "raw_response_excerpt": "{...}"
}
```

| `message_type` | Description |
| --- | --- |
| `alert` | Threshold exceeded notification |
| `diagnosis` | Finding based on anomaly flags |
| `recovery_command` | Recovery decision explanation |
| `comment` | Utterance in LLM deliberation |
| `skip` | Parse failure / empty action (`llm_no_action`, etc.) |

| `deliberation_phase` | Description |
| --- | --- |
| `deliberation` | All-hands discussion round |
| `action` | Representative command decision |
| `post_run_proposal` | Post-run design (when present in messages) |

`from_role` is `engineer_1` … `engineer_N`. Full Persona text and `policy` values are not logged.

---

## ROS2-style ECLSS topics

`environment/ssos/topics.py` — contract for mock / future adapter.

| Topic | Direction | Payload |
| --- | --- | --- |
| `/eclss/telemetry/co2_ppm` | pub | float |
| `/eclss/telemetry/scrubber_efficiency` | pub | float |
| `/eclss/telemetry/power_margin_w` | pub | float |
| `/eclss/command/set_fan_speed` | sub | float 0–1 |
| `/eclss/command/enable_bypass` | sub | bool |
| `/eclss/command/reduce_load` | sub | bool |
| `/eclss/command/request_eps_boost` | sub | float W |
| `/eclss/events/design_change` | event | DesignChange dict |
| `/eclss/events/recovery_applied` | event | Command application result |
| `/eclss/events/anomaly` | event | Anomaly flags |

---

## ROS2-style EPS topics

**EPS** (Electrical Power System) — generation, storage, distribution. The MVP mocks **SARJ** (Solar Alpha Rotary Joint) and **BCDU** (Battery Charge/Discharge Unit). Real systems also include **MBSU** (Main Bus Switching Unit) and **DDCU** (Direct Current-to-Direct Current Converter Unit).

`environment/ssos/eps_topics.py`. Reference: [space_station_eps](https://github.com/space-station-os/space_station_os/tree/main/space_station_eps).

| Topic | Direction | Payload |
| --- | --- | --- |
| `/solar/voltage` | pub | float V |
| `/bcdu/operation` | sub | `{support_w, duration_steps}` |
| `/bcdu/status` | pub | `BcduStatus` |
| `/eps/diagnostics` | pub | `EpsDiagnostics` |
| `/eps/eclss/load_request_w` | pub | float W |

**BCDU `mode`**: `idle`, `charging`, `discharging`, `fault`, `safe`.

---

## JSONL output directory

`src/experiments/results/<run_id>/`

### EventLog streams

`EventLog.STREAMS` in `src/core/event_log.py` defines valid stream names. Each stream writes to `<stream>.jsonl` when records are appended.

| Stream | Written in MVP | Description |
| --- | --- | --- |
| `telemetry` | yes | Per-step ECLSS `TelemetrySnapshot` |
| `health_metrics` | yes | Deterministic CO2 / power / overall status |
| `eps_telemetry` | yes | SARJ + BCDU state (`StationSimulator` only) |
| `design_state` | yes | Topology + parameters before agent action each step |
| `events` | yes | Anomalies, recovery application |
| `messages` | yes | Agent utterances (when `agents.mode` ≠ `none`) |
| `memory_reasoning` | **no** | Reserved for future per-agent memory traces; stream name is registered but no writer exists yet |

`summary.json`, `design_proposals.json`, and `provenance.jsonl` are written outside `EventLog.append()`.

### events.jsonl

```json
{"step": 20, "kind": "/eclss/events/anomaly", "flags": ["scrubber_degradation"]}
{"step": 33, "kind": "/eclss/events/recovery_applied", "command": {"kind": "set_fan_speed", "value": 1.0, "issued_by": "engineer_2"}, "message": "fan_speed set to 1.0"}
```

In the current flow, **`/eclss/events/design_change` does not occur at runtime** (post-run proposals are in `design_proposals.json`).

### design_state.jsonl

Every step, snapshot **before** agent action. Because topology is invariant at runtime, `topology` is identical for the entire run.

```json
{
  "step": 36,
  "topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}],
    "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]
  },
  "parameters": {"scrubber_base_efficiency": 0.95}
}
```

### eps_telemetry.jsonl

Only when `StationSimulator` runs. One line per step.

```json
{
  "step": 22,
  "solar_voltage_v": 113.14,
  "beta_angle_deg": 45.0,
  "in_eclipse": false,
  "bcdu_mode": "discharging",
  "bus_voltage_v": 110.0,
  "support_w": 120.0,
  "support_steps_remaining": 3,
  "fault": false,
  "fault_message": ""
}
```

### summary.json

```json
{
  "scenario": "scrubber_degradation",
  "simulator": "mock_station",
  "agents_mode": "labeled_rule_base",
  "team_count": 4,
  "agent_ids": ["engineer_1", "engineer_2", "engineer_3", "engineer_4"],
  "steps": 50,
  "peak_co2_ppm": 1016.34,
  "final_co2_ppm": 967.2,
  "final_power_margin_w": -42.5,
  "min_power_margin_w": -128.0,
  "eps_boost_applied_step": 28,
  "power_recovered_above_critical_step": 32,
  "final_health": {"step": 50, "co2_status": "safe", "power_status": "warning", "overall": "warning"},
  "anomaly_seen": true,
  "co2_above_threshold_step": 33,
  "co2_recovered_below_threshold_step": 40,
  "message_count": 59,
  "design_change_count": 0,
  "design_proposal_count": 1,
  "design_proposals_path": "src/experiments/results/.../design_proposals.json",
  "provenance_path": "src/experiments/results/.../provenance.jsonl",
  "provenance_record_count": 2
}
```

---

## provenance.jsonl (One Piece compatible)

Generated at run end by `src/integrations/one_piece/client.py`.

### Currently exported

| Source | Condition |
| --- | --- |
| Runtime `design_change` events | **0 records** in the current scenario |
| `request_eps_boost` recovery | `recovery_applied` in `events.jsonl` |

### Recovery record example

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
  "payload": {"support_w": 120.0, "eps": {"bcdu_mode": "discharging"}},
  "trace": {
    "event_kind": "/eclss/events/recovery_applied",
    "decision_source": "rule",
    "message": "Requesting EPS support boost of 120 W."
  }
}
```

### Not yet exported (planned)

Post-run proposals from `design_proposals.json` → provenance records. Details: [one-piece-integration.md](one-piece-integration.md), [development-plan.md](development-plan.md).

Schema reference: `src/integrations/one_piece/ssot_schema.json`.

---

## Examples

```bash
pip install -e ".[dev]"

# Baseline
python src/scripts/run_mock_eclss.py

# labeled_rule_base
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}})"

# llm (requires Ollama)
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'llm'}})"
```

EPS smoke test from code:

```python
from environment.protocol import CommandKind, RecoveryCommand
from environment.ssos import StationSimulator, MockEclssSimulator

station = StationSimulator(MockEclssSimulator())
station.apply_command(RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=120.0))
```
