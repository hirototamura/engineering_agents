# Architecture

## Mission

Multi-agent simulation for ECLSS anomaly detection through design change (resilience loop). The platform prioritizes **structured agent relationships** and **simulator API contracts** over high-fidelity physics or graphics.

## Dependency direction

Imports must flow in one direction only:

```text
tools → scenario → environment → core
materials/  (isolated — not imported by new code)
integrations/  (called from scenario/tools only)
```

| Layer | Responsibility |
| --- | --- |
| `src/core/` | Agent base, simulation loop, LLM clients, event logging |
| `src/environment/` | Simulator boundary (`SimulatorProtocol`, SSOS mock/adapter, ECLSS ops) |
| `src/scenario/` | Scenario YAML, runner, role-specific agents |
| `src/experiments/` | Run configs and results (results are gitignored) |
| `src/tools/` | CLI, Streamlit dashboard, batch utilities |
| `src/materials/` | Legacy reference sims (2D bar simulation). Do not import from new layers. |
| `integrations/one_piece/` | Design-change provenance (JSON SSOT; full One Piece UI deferred) |

## Two simulation lines

1. **Legacy (materials)**: `src/materials/2d-bar-simulation/` — original LLM bar/fire sim. Self-contained; run from that directory.
2. **ECLSS (new)**: `src/scenario/scrubber_degradation/` — virtual ops phase anomaly → recovery → design change. Uses `core` + `environment` + mock SSOS.

## Output layout

Each run writes to `src/experiments/results/<run_id>/`:

- `messages.jsonl`, `telemetry.jsonl`, `health_metrics.jsonl`
- `events.jsonl`, `design_state.jsonl`, `memory_reasoning.jsonl`
- `summary.json`

See `docs/api-contracts.md` (Day 2+) for schema details.

## External systems

| System | MVP approach |
| --- | --- |
| SSOS | Mock adapter first (`environment/ssos/mock_eclss.py`); real ROS2 adapter later |
| One Piece | JSON file provenance via `integrations/one_piece/`; no web UI in Week 1 |
| LLM | Ollama via `core/llm/ollama.py`; Week-1 agents are rule-based first |

### scrubber_degradation baseline (Day 3)

```bash
python src/scripts/run_mock_eclss.py
pytest tests/scenario/test_scrubber_baseline.py -q
```

See [api-contracts.md](api-contracts.md) for protocol and JSONL schemas.

## Agent roles (Day 4+)

Week-1 implements **scenario-specific labeled roles** for `scrubber_degradation` only (Monitor, Diagnostician, Operator, DesignEngineer)—not a generic role framework.

Research backlog **BL-001**: compare labeled roles vs unlabeled Base Role agents and whether situational roles emerge. See [memo/backlog.md](../memo/backlog.md).

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```
