# AGENTS.md — Engineering Agents Guide

This file is the entry point for **human contributors** and **coding agents** (Cursor, etc.).

**Read the full guide in your language:**

| Language | Guide |
| --- | --- |
| **English** | [docs/en/AGENTS.md](docs/en/AGENTS.md) |
| **日本語** | [docs/ja/AGENTS.md](docs/ja/AGENTS.md) |

---

## One-line summary

**The paramount requirement is the mission itself. Design and verification requirements can be revised under One Piece. Design and verification must follow physics and must not violate the mission.**

---

## Quick reference (layers)

```text
tools → scenario → environment → core
integrations/one_piece ← called from scenario
```

Do not import upward across layers. Do not put LLM or Persona logic in `environment/`.

After changes, run `pytest`.

---

## Cursor Cloud specific instructions

Pure Python project (Python 3.12). The update script installs the package editable via `pip install -e ".[dev]"` into the **system** Python (no virtualenv), so `python3 -m pytest`, `python3 -m streamlit`, etc. work in any fresh shell.

- Console scripts (`ea`, etc.) land in `~/.local/bin`, which is not on `PATH`. Prefer `python3 -m tools.cli …` (e.g. `python3 -m tools.cli run scrubber_degradation --agents-mode labeled_rule_base`) or add `~/.local/bin` to `PATH` and use `ea run …`. See [docs/en/cli.md](docs/en/cli.md).
- Tests: `python3 -m pytest --ignore=tests/e2e` (matches CI). Most of `tests/e2e` needs a live SSOS Docker + ROS2 container (`SSOS_E2E=1`) which is **not** available here; only `tests/e2e/test_ssos_regression.py::test_regression_tier1_pytest_only` runs offline.
- Run scenarios without external services: `python3 -m tools.cli run scrubber_degradation --agents-mode labeled_rule_base` or `python3 -m tools.cli run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base` (no Ollama, no ROS2).
- `agents.mode: llm` requires a running Ollama daemon; `ssos_eclss_loop` default `ros2` backend requires SSOS Docker — neither is set up here. Prefer rule-based/mock for verification.
- Dashboard reads runs from `src/experiments/results/<run_id>/`; generate a run first, then `python3 -m streamlit run src/tools/dashboard/app.py --server.headless true`.
