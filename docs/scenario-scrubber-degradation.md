# Scenario: scrubber_degradation

Reference scenario for the ECLSS virtual-ops resilience loop MVP.

## Narrative

| Phase | Steps | What happens |
| --- | --- | --- |
| Equilibrium | 1–19 | CO2 ~800 ppm, scrubber at baseline efficiency |
| Anomaly | 20+ | `scrubber_degradation`: efficiency drops, power margin shrinks, CO2 production rises |
| Danger band | ~33+ | CO2 exceeds 1000 ppm (baseline / labeled runs) |
| Response | 33–40 | Operator recovery commands (fan, load shed, bypass) |
| Design change | ≥35 | DesignEngineer adds permanent bypass edge (labeled modes) |
| Recovery | ~40+ | CO2 returns below 1000 ppm (labeled mode) |

Physics-only runs (`agents.mode: none`) demonstrate anomaly and CO2 rise but **do not** apply recovery or design changes.

## Configuration files

| File | Purpose |
| --- | --- |
| [scenario.yaml](../src/scenario/scrubber_degradation/scenario.yaml) | Steps, initial state, design parameters, anomalies, `agents.mode`, output run IDs |
| [agents.yaml](../src/scenario/scrubber_degradation/agents.yaml) | Role thresholds and LLM settings (used when `agents.mode` ≠ `none`) |

### Key simulation parameters

- Initial CO2: 800 ppm
- Anomaly start: step 20
- Scrubber efficiency decay: 0.02 / step after anomaly
- CO2 production multiplier during anomaly: 1.4×

### Agent modes

```yaml
# scenario.yaml
agents:
  mode: none  # none | labeled | labeled_llm_guarded
```

Override at runtime:

```python
from scenario.runner import run_scenario

run_scenario("scrubber_degradation", overrides={"agents": {"mode": "labeled"}})
```

## Labeled roles

Scenario-specific — not reusable across other scenarios without a new team class.

| Role | Config key | Behavior |
| --- | --- | --- |
| Monitor | `roles.monitor.co2_alert_ppm` (900) | Emits `alert` when CO2 high |
| Diagnostician | — | Emits `diagnosis` when anomaly flags set |
| Operator | `co2_recovery_ppm`, `fan_speed`, `eps_boost_w`, etc. | Issues recovery commands including EPS boost on power-critical |
| DesignEngineer | `min_step`, `bypass_edge` | Proposes `add_edge` bypass |

Research note: these labels are human division-of-labor conventions. Unlabeled emergent roles are tracked in [memo/backlog.md](../memo/backlog.md) BL-001.

## labeled_llm_guarded mode

Persona-based two-round deliberation (8 LLM calls per step) with guardrails:

| Round | Agents | Output |
| --- | --- | --- |
| 1 — open forum | monitor, diagnostician, operator, design_engineer | message + reasoning (+ optional `memory`) |
| 2 — react + act | monitor, diagnostician (react); operator, design_engineer (commands / design) | same contracts; action keys in round 2 only |

**Persona vs scenario**: `personas` in `agents.yaml` define professional voice and debate style only. Scenario briefing, thresholds, and telemetry live under `## Situation` (injected by `ScrubberDegradationTeam._situation_context()`). Command and design shapes live in output contracts.

**Memory**: team `DiscourseBuffer` (shared) + per-agent `AgentMemory` (private). See `memory_limit` / `discourse_window` in `agents.yaml`.

Message metadata includes `deliberation_phase`, `main_role`, and `decision_source` (`llm`, `rule_fallback`, `llm_guard_reject`).

On parse/guard failure, rule fallback applies. Requires Ollama and a pulled model (default `qwen3.5:2b`, `temperature: 0.45`, `max_tokens: 320`).

## Where to read outputs

After a run, open `src/experiments/results/<run_id>/`:

| Question | File | What to look for |
| --- | --- | --- |
| What did agents say? | `messages.jsonl` | `from_role`, `message_type`, `decision_source` |
| What changed in the plant? | `telemetry.jsonl` | `co2_ppm`, `scrubber_efficiency`, flags |
| What commands ran? | `events.jsonl` | `recovery_applied`, `design_change` |
| What was the design graph? | `design_state.jsonl` | `topology.edges` — bypass appears step after change |
| What is One Piece provenance? | `provenance.jsonl` | actor, change_kind, before/after topology, trace linkage |
| Run KPIs? | `summary.json` | `peak_co2_ppm`, `co2_recovered_below_threshold_step`, `design_change_count` |

### design_change example

**Structured change** (`events.jsonl`):

```json
{"step": 35, "kind": "/eclss/events/design_change", "change": {"kind": "add_edge", "payload": {"node_a": "manifold", "node_b": "scrubber", "kind": "bypass"}, "proposed_by": "design_engineer"}}
```

**Human-readable proposal** (`messages.jsonl`):

```json
{"step": 35, "from_role": "design_engineer", "message_type": "design_change", "message": "Proposing permanent bypass plumbing between manifold and scrubber.", "decision_source": "rule"}
```

**Topology effect** (`design_state.jsonl`): compare step 35 vs 36 — new edge `{"source": "manifold", "target": "scrubber", "kind": "bypass"}`.

## Tests

| Test | Mode | Asserts |
| --- | --- | --- |
| `tests/scenario/test_scrubber_baseline.py` | `none` | Anomaly fires, CO2 > 1000, no agents |
| `tests/scenario/test_scrubber_with_agents.py` | `labeled` | 4 roles, recovery, design change, final CO2 < 1000 |

Always keep baseline green when changing agent or physics code.

## Day6 visualization

```bash
python -m streamlit run src/tools/dashboard/app.py
```

Dashboard features:

- Run selector (`src/experiments/results/<run_id>`)
- Step slider synchronized with telemetry, messages, events, and provenance rows
- CO2 / power margin trend plots with current-step marker
- Run comparison mode for provenance and final design-parameter diffs (e.g. `labeled` vs `labeled_llm_guarded`)
