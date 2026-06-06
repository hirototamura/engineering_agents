# Documentation index

Living docs for the ECLSS resilience-loop simulation platform.

| Document | Audience | Contents |
| --- | --- | --- |
| [architecture.md](architecture.md) | Contributors | Layers, dependency rules, agent modes, run flow |
| [api-contracts.md](api-contracts.md) | Integrators | `SimulatorProtocol`, JSONL schemas, ROS2-like topics |
| [scenario-scrubber-degradation.md](scenario-scrubber-degradation.md) | Demo / ops | Scenario narrative, roles, where to read outputs |
| [one-piece-integration.md](one-piece-integration.md) | Design tracking | One Piece provenance implementation + next extension plan |

Planning and research notes live outside `docs/`:

- [memo/mvp_plan.md](../memo/mvp_plan.md) — week roadmap and task checklist
- [memo/eps_implementation_plan.md](../memo/eps_implementation_plan.md) — EPS-1〜4 and Day 8–10 (Week-2 entry)
- [memo/backlog.md](../memo/backlog.md) — BL-001 labeled vs emergent roles, etc.

## Quick commands

```bash
pip install -e ".[dev]"
pytest

# Physics-only baseline (agents.mode: none)
python src/scripts/run_mock_eclss.py

# Rule-based labeled team
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}})"

# LLM applied with guards (monitor/diagnostician/operator + guarded design engineer)
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_llm_guarded'}})"

# Day6 dashboard
python -m streamlit run src/tools/dashboard/app.py
```

## Current milestone (through EPS-4)

- Done: baseline + labeled agents, LLM guarded mode, One Piece provenance (design + EPS recovery), dashboard with SARJ/BCDU, `StationSimulator` / `mock_station`
- Next: [Day 8 CLI](../memo/eps_implementation_plan.md#day-8-cli1日) — then provenance index and SSOS adapter contract tests

Requires `pip install -e ".[dev]"` before `from scenario.runner import ...` (packages live under `src/`).
