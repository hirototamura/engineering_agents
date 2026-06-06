# API Contracts — SimulatorProtocol & Event Logs

Living document. Update when protocol, agent modes, or log schemas change.

## SimulatorProtocol

Implementations: `StationSimulator` (ECLSS + EPS, default for scenarios), `MockEclssSimulator` (plant-only), `SsosAdapter` (deferred).

| Method | Returns | Description |
| --- | --- | --- |
| `step()` | `TelemetrySnapshot` | Advance physics one tick |
| `apply_command(cmd)` | `CommandResult` | Temporary recovery action |
| `apply_design_change(change)` | `DesignState` | Permanent topology/parameter mutation |
| `get_topology()` | `TopologyGraph` | Current node/edge graph |
| `get_design_parameters()` | `dict[str, float]` | Mutable design parameters |
| `get_design_state()` | `DesignState` | Topology + parameters snapshot |
| `inject_anomaly(spec)` | `None` | Schedule composite anomaly |

### TelemetrySnapshot

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

### RecoveryCommand

```json
{
  "kind": "set_fan_speed",
  "value": 1.0,
  "issued_by": "operator"
}
```

Supported `kind` values: `set_fan_speed`, `enable_bypass`, `reduce_load`, `request_eps_boost`.

### DesignChange

```json
{
  "kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "proposed_by": "design_engineer"
}
```

Supported `kind` values: `add_edge`, `set_parameter`.

### Health thresholds

| Metric | safe | warning | critical |
| --- | --- | --- | --- |
| CO2 (ppm) | < 1000 | 1000–2000 | ≥ 2000 |
| Power margin (W) | > 0 | 0 to −100 | ≤ −100 |

## Agent modes

Set in `src/scenario/scrubber_degradation/scenario.yaml` (`agents.mode`). Role thresholds in `agents.yaml`.

| `agents.mode` | Team | Actions source | Messages |
| --- | --- | --- | --- |
| `none` | — | — | — |
| `labeled` | `ScrubberDegradationTeam` | Rules | Rule messages only |
| `labeled_llm_guarded` | Same team | LLM with guards + rule fallback | LLM or `rule_fallback` messages |

Future: `base` (unlabeled emergent roles) — see [memo/backlog.md](../memo/backlog.md) BL-001.

## ROS2-like topics (`environment/ssos/topics.py`)

| Topic | Direction | Payload |
| --- | --- | --- |
| `/eclss/telemetry/co2_ppm` | pub | float |
| `/eclss/telemetry/scrubber_efficiency` | pub | float |
| `/eclss/telemetry/power_margin_w` | pub | float |
| `/eclss/command/set_fan_speed` | sub | float 0–1 |
| `/eclss/command/enable_bypass` | sub | bool |
| `/eclss/command/reduce_load` | sub | bool |
| `/eclss/command/request_eps_boost` | sub | float watts (0, 500] |
| `/eclss/events/design_change` | event | DesignChange dict |

## ROS2-like EPS topics (`environment/ssos/eps_topics.py`)

Inspired by [space_station_eps](https://github.com/space-station-os/space_station_os/tree/main/space_station_eps). Mock implementations: `MockSarj`, `MockBcdu`, `EpsStack` (EPS-3 couples to ECLSS).

| Topic | Direction | Payload |
| --- | --- | --- |
| `/solar/voltage` | pub | float V (SARJ estimate) |
| `/bcdu/operation` | sub | discharge goal: `{support_w, duration_steps}` |
| `/bcdu/status` | pub | `BcduStatus` dict — `mode`, `bus_voltage_v`, `support_w`, `fault`, … |
| `/eps/diagnostics` | pub | `EpsDiagnostics` dict |
| `/eps/eclss/load_request_w` | pub | float W (bridge topic; EPS-3) |

**BCDU `mode` values**: `idle`, `charging`, `discharging`, `fault`, `safe`.

**Discharge contract** (`MockBcdu.request_discharge`): `support_w` in (0, 500], `duration_steps` ≥ 1, bus voltage in [70, 120] V. On fault, mode latches `fault` and further discharge requests fail.

## JSONL event streams

All runs write under `src/experiments/results/<run_id>/`.

### messages.jsonl

Written when `agents.mode` is `labeled` or `labeled_llm_guarded`.

**Rule message:**

```json
{
  "step": 33,
  "from_role": "monitor",
  "to_role": "team",
  "message": "CO2 at 1016 ppm exceeds alert threshold 900.",
  "message_type": "alert",
  "reasoning": "Telemetry threshold crossed.",
  "decision_source": "rule"
}
```

**LLM guarded message** (`labeled_llm_guarded`):

```json
{
  "step": 33,
  "from_role": "operator",
  "to_role": "team",
  "message": "...",
  "message_type": "recovery_command",
  "reasoning": "...",
  "decision_source": "llm",
  "parse_status": "ok",
  "parse_error": null,
  "raw_response_excerpt": "..."
}
```

`message_type` values:

| Type | Source |
| --- | --- |
| `alert`, `diagnosis`, `recovery_command`, `design_change` | Rule or LLM guarded |

### telemetry.jsonl

Raw physics snapshot per step (same fields as `TelemetrySnapshot`).

### health_metrics.jsonl

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
```

### eps_telemetry.jsonl

Written for `mock_station` runs (EPS-4). One row per step from SARJ + BCDU.

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

### events.jsonl

Anomalies, recovery commands, design changes.

```json
{"step": 20, "kind": "/eclss/events/anomaly", "flags": ["scrubber_degradation"]}
{"step": 33, "kind": "/eclss/events/recovery_applied", "command": {"kind": "set_fan_speed", "value": 1.0, "issued_by": "operator"}, "message": "fan_speed set to 1.0"}
{"step": 35, "kind": "/eclss/events/design_change", "change": {"kind": "add_edge", "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}, "proposed_by": "design_engineer"}}
```

### design_state.jsonl

Topology + parameters snapshot **before** agent actions at each step.

```json
{
  "step": 36,
  "topology": {
    "nodes": [{"id": "cabin", "name": "Cabin", "kind": "volume"}, "..."],
    "edges": [
      {"source": "manifold", "target": "scrubber", "kind": "flow"},
      {"source": "manifold", "target": "scrubber", "kind": "bypass"}
    ]
  },
  "parameters": {"scrubber_base_efficiency": 0.95, "...": "..."}
}
```

Compare step *N* vs *N+1* after a design change event at step *N*.

### summary.json

Run-level KPIs written once at end.

```json
{
  "scenario": "scrubber_degradation",
  "simulator": "mock_station",
  "agents_mode": "labeled",
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
  "design_change_count": 1,
  "provenance_path": "src/experiments/results/scrubber_degradation_labeled/provenance.jsonl",
  "provenance_record_count": 2
}
```

### provenance.jsonl (Day 5B+ / EPS-4)

One Piece-compatible provenance records: **design changes** and **EPS recovery** (`request_eps_boost`).

```json
{
  "record_id": "scrubber_degradation_labeled:design_change:1",
  "run_id": "scrubber_degradation_labeled",
  "scenario": "scrubber_degradation",
  "step": 35,
  "actor": "design_engineer",
  "actor_kind": "ai_agent",
  "change_kind": "add_edge",
  "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"},
  "before_topology": {"nodes": [{"id": "cabin"}], "edges": [{"source": "manifold", "target": "scrubber", "kind": "flow"}]},
  "after_topology": {"nodes": [{"id": "cabin"}], "edges": [{"source": "manifold", "target": "scrubber", "kind": "bypass"}]},
  "trace": {"event_kind": "/eclss/events/design_change", "decision_source": "rule"}
}
```

**Recovery record** (`record_type: recovery`):

```json
{
  "record_id": "scrubber_degradation_labeled:recovery:2",
  "record_type": "recovery",
  "change_kind": "request_eps_boost",
  "step": 28,
  "actor": "operator",
  "payload": {"support_w": 120.0, "eps": {"bcdu_mode": "discharging"}},
  "trace": {"event_kind": "/eclss/events/recovery_applied", "decision_source": "rule"}
}
```

## Running scenarios

```bash
# Baseline (agents.mode: none) — default in scenario.yaml
python src/scripts/run_mock_eclss.py

# Labeled rule team
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}})"

# LLM guarded (requires Ollama)
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_llm_guarded'}})"
```

Programmatic recovery smoke test:

```python
from environment.protocol import CommandKind, RecoveryCommand
from environment.ssos import StationSimulator, MockEclssSimulator

station = StationSimulator(MockEclssSimulator())
station.apply_command(RecoveryCommand(kind=CommandKind.REQUEST_EPS_BOOST, value=120.0))
```
