# API Contracts — SimulatorProtocol & Event Logs

Living document. Update when protocol, agent modes, or log schemas change.

## SimulatorProtocol

Implementations: `MockEclssSimulator` (current), `SsosAdapter` (deferred).

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

Supported `kind` values: `set_fan_speed`, `enable_bypass`, `reduce_load`.

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
| `labeled_shadow` | Same team | Rules (unchanged) | Rule + LLM shadow messages |

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
| `/eclss/events/design_change` | event | DesignChange dict |

## JSONL event streams

All runs write under `src/experiments/results/<run_id>/`.

### messages.jsonl

Written when `agents.mode` is `labeled` or `labeled_shadow`.

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

**LLM shadow message** — same step may also include:

```json
{
  "step": 33,
  "from_role": "operator",
  "to_role": "team",
  "message": "...",
  "message_type": "llm_shadow_operator",
  "reasoning": "...",
  "decision_source": "llm_shadow",
  "parse_status": "ok",
  "parse_error": null,
  "raw_response_excerpt": "..."
}
```

`message_type` values:

| Type | Source |
| --- | --- |
| `alert`, `diagnosis`, `recovery_command`, `design_change` | Rule |
| `llm_shadow_monitor`, `llm_shadow_diagnosis`, `llm_shadow_operator`, `llm_shadow_design` | LLM shadow |

### telemetry.jsonl

Raw physics snapshot per step (same fields as `TelemetrySnapshot`).

### health_metrics.jsonl

```json
{"step": 5, "co2_status": "safe", "power_status": "safe", "overall": "safe"}
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
  "simulator": "mock_eclss",
  "agents_mode": "labeled",
  "steps": 50,
  "peak_co2_ppm": 1016.34,
  "final_co2_ppm": 967.2,
  "final_health": {"step": 50, "co2_status": "safe", "power_status": "critical", "overall": "critical"},
  "anomaly_seen": true,
  "co2_above_threshold_step": 33,
  "co2_recovered_below_threshold_step": 40,
  "message_count": 59,
  "design_change_count": 1
}
```

One Piece integration may add `provenance_path` or similar fields when provenance logging lands.

## Running scenarios

```bash
# Baseline (agents.mode: none) — default in scenario.yaml
python src/scripts/run_mock_eclss.py

# Labeled rule team
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}})"

# LLM shadow (requires Ollama; actions still rule-based)
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_shadow'}})"
```

Programmatic recovery smoke test:

```python
from environment.protocol import CommandKind, RecoveryCommand
from environment.ssos.mock_eclss import MockEclssSimulator

sim = MockEclssSimulator()
sim.apply_command(RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=1.0))
```
