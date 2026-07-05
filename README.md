# Engineering Agents — ECLSS Resilience Loop

Research repository that simulates **agent teams** detecting, responding to, and proposing design changes after **ECLSS** (Environmental Control and Life Support System) anomalies on a mock **Space Station OS (SSOS)** simulator.

---

## Documentation / ドキュメント

| Language | Quick start | Overview | Engineering guide (AGENTS) |
| --- | --- | --- | --- |
| **English** | [docs/en/index.md](docs/en/index.md) | [docs/en/overview.md](docs/en/overview.md) | [docs/en/AGENTS.md](docs/en/AGENTS.md) |
| **日本語** | [docs/ja/index.md](docs/ja/index.md) | [docs/ja/overview.md](docs/ja/overview.md) | [docs/ja/AGENTS.md](docs/ja/AGENTS.md) |

### Design docs / 設計ドキュメント

| | English | 日本語 |
| --- | --- | --- |
| Architecture | [docs/en/architecture.md](docs/en/architecture.md) | [docs/ja/architecture.md](docs/ja/architecture.md) |
| API contracts | [docs/en/api-contracts.md](docs/en/api-contracts.md) | [docs/ja/api-contracts.md](docs/ja/api-contracts.md) |
| Development plan | [docs/en/development-plan.md](docs/en/development-plan.md) | [docs/ja/development-plan.md](docs/ja/development-plan.md) |
| One Piece integration | [docs/en/one-piece-integration.md](docs/en/one-piece-integration.md) | [docs/ja/one-piece-integration.md](docs/ja/one-piece-integration.md) |
| Scenario: scrubber_degradation | [docs/en/scenario-scrubber-degradation.md](docs/en/scenario-scrubber-degradation.md) | [docs/ja/scenario-scrubber-degradation.md](docs/ja/scenario-scrubber-degradation.md) |
| Scenario: ssos_eclss_loop | [docs/en/scenario-ssos-eclss-loop.md](docs/en/scenario-ssos-eclss-loop.md) | [docs/ja/scenario-ssos-eclss-loop.md](docs/ja/scenario-ssos-eclss-loop.md) |
| SSOS integration (MkDocs) | [docs/en/ssos/index.md](docs/en/ssos/index.md) | [docs/ja/ssos/index.md](docs/ja/ssos/index.md) |

MkDocs preview: `mkdocs serve` → English [http://127.0.0.1:8000/](http://127.0.0.1:8000/) · 日本語 [http://127.0.0.1:8000/ja/](http://127.0.0.1:8000/ja/)  
Catalog: [docs/en/catalog.md](docs/en/catalog.md) · [docs/ja/catalog.md](docs/ja/catalog.md)

---

## Quick start (macOS / Linux)

This quick start is for macOS / Linux-style shells. For Windows setup, use the
full Windows instructions in [docs/en/index.md](docs/en/index.md) (Windows tab)
or [docs/ja/index.md](docs/ja/index.md), or [Overview §2B](docs/en/overview.md#2b-windows-powershell--docker-desktop).

Requires **Python 3.11+** on the host (`requires-python` in `pyproject.toml`). SSOS Docker jobs use the container’s own Python.

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ea doctor
pytest
python -c "from scenario.runner import run_scenario; print(run_scenario('scrubber_degradation', overrides={'agents': {'mode': 'labeled_rule_base'}}))"
```

See [docs/en/overview.md](docs/en/overview.md) or [docs/ja/overview.md](docs/ja/overview.md) for full setup, LLM mode, and the Streamlit dashboard.

---

## License

[Apache License 2.0](LICENSE.txt) — Copyright 2026 Hiroto Tamura
