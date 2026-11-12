# Set up a development checkout

Use Python 3.11 or newer; the documentation workflow uses Python 3.12. The declared requirements and optional dependency groups live in [pyproject.toml](https://github.com/hirototamura/engineering_agents/blob/main/pyproject.toml).

## Install and identify the checkout

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -c "import scenario.runner; print(scenario.runner.__file__)"
python -m tools.cli --help
```

The printed module path must point into this checkout's `src/`. An editable installation from another clone can silently inspect or run different code. If necessary, use `PYTHONPATH=src python ...` while diagnosing that mismatch. The `ea` console entry point and `python -m tools.cli` reach the same Typer application.

## Verify the baseline

```bash
python -m pytest --ignore=tests/e2e
python -m mkdocs build --strict
```

The first command covers the ordinary test suite. Live SSOS tests under `tests/e2e` need Docker, ROS2, and `SSOS_E2E=1`; they are a separate environment. Simulator-dependent tests may skip when optional packages or hardware are absent. Inspect skips when they affect your change.

Install only the dependencies required by your change: `.[mujoco]` for native MuJoCo, `.[gpu]` for the pinned MJX/JAX stack, and `.[onepiece]` for the One Piece package. These groups have distinct numerical requirements; use a suitable separate environment when needed. LLM modes also require a reachable configured provider. Routine source and documentation work does not require running an experiment.

Read [architecture](architecture.md) before moving modules. Choose the regression checks for your task from [contributing](contributing.md), then use the relevant [scenario implementation guide](scenarios/index.md). End-user prerequisites and run procedures remain in the [user documentation](../users/index.md).
