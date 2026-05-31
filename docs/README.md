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
- [memo/backlog.md](../memo/backlog.md) — BL-001 labeled vs emergent roles, etc.

## Quick commands

```bash
pip install -e ".[dev]"
pytest

# Physics-only baseline (agents.mode: none)
python src/scripts/run_mock_eclss.py

# Rule-based labeled team
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled'}})"

# LLM shadow messages + rule actions
python -c "from scenario.runner import run_scenario; run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_shadow'}})"
```

## Current milestone (through Day5B)

- Done: baseline scenario, labeled rule-team, labeled_shadow, One Piece provenance export
- Next: Day6 dashboard, Day7 CLI + E2E, Week-2 connector / SSOS adapter prep
