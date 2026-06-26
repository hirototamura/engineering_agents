# Engineering Agents — ECLSS Resilience Loop

Research repository that simulates **agent teams** detecting, responding to, and proposing design changes after **ECLSS** (Environmental Control and Life Support System) anomalies. Two scenario tracks: Python mock (`scrubber_degradation`) and SSOS live ECLSS (`ssos_eclss_loop`, Phase 0–7).

---

## Documentation / ドキュメント

| Language | README | Engineering guide (AGENTS) |
| --- | --- | --- |
| **English** | [en/README.md](en/README.md) | [en/AGENTS.md](en/AGENTS.md) |
| **日本語** | [ja/README.md](ja/README.md) | [ja/AGENTS.md](ja/AGENTS.md) |

### Design docs / 設計ドキュメント

| | English | 日本語 |
| --- | --- | --- |
| Architecture | [en/docs/architecture.md](en/docs/architecture.md) | [ja/docs/architecture.md](ja/docs/architecture.md) |
| API contracts | [en/docs/api-contracts.md](en/docs/api-contracts.md) | [ja/docs/api-contracts.md](ja/docs/api-contracts.md) |
| Development plan | [en/docs/development-plan.md](en/docs/development-plan.md) | [ja/docs/development-plan.md](ja/docs/development-plan.md) |
| One Piece integration | [en/docs/one-piece-integration.md](en/docs/one-piece-integration.md) | [ja/docs/one-piece-integration.md](ja/docs/one-piece-integration.md) |
| Scenario: scrubber_degradation | [en/docs/scenario-scrubber-degradation.md](en/docs/scenario-scrubber-degradation.md) | [ja/docs/scenario-scrubber-degradation.md](ja/docs/scenario-scrubber-degradation.md) |
| Scenario: ssos_eclss_loop | [en/docs/scenario-ssos-eclss-loop.md](en/docs/scenario-ssos-eclss-loop.md) | [ja/docs/scenario-ssos-eclss-loop.md](ja/docs/scenario-ssos-eclss-loop.md) |

Research memos live under [en/memo/](en/memo/) and [ja/memo/](ja/memo/).

Shared dashboard screenshots: [docs/images/](docs/images/).

---

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}}))"
```

See [en/README.md](en/README.md) or [ja/README.md](ja/README.md) for full setup, LLM mode, and the Streamlit dashboard.

---

## License

[Apache License 2.0](LICENSE.txt) — Copyright 2026 Hiroto Tamura
