# CLI Guide

The unified CLI is the recommended way to run simulations. After installation:

```bash
pip install -e ".[dev]"
ea run
```

## Golden path

`ea run` with no arguments runs:

- scenario: `scrubber_degradation`
- agents: `labeled_rule_base` (no Ollama required)
- steps: from `scenario.yaml` (default 50)

To match the physics-only baseline in `scenario.yaml`, pass `--agents-mode none`.

## Commands

| Command | Purpose |
| --- | --- |
| `ea run [SCENARIO]` | Run one simulation |
| `ea scenarios` | List available scenarios |
| `ea results [RUN_ID]` | List recent runs or show one `summary.json` |
| `ea doctor` | Check Python, dependencies, and Ollama reachability |
| `ea job run SPEC.json` | Execute a serialized `RunSpec` (cluster-worker compatible) |
| `ea --version` | Show CLI version |

Equivalent module form:

```bash
python3 -m tools.cli run scrubber_degradation --agents-mode none
```

## Common flags

```bash
ea run scrubber_degradation --agents-mode labeled_rule_base --steps 30
ea run ssos_eclss_loop --backend mock --agents-mode none --steps 4
ea run scrubber_degradation --set simulation.steps=10 --set agents.mode=none
ea run scrubber_degradation --override-file my_patch.yaml
ea run scrubber_degradation --output-dir /tmp/my-run
ea run scrubber_degradation --run-id sweep-001
ea run --dry-run --write-spec /tmp/job.json
ea job run /tmp/job.json
```

| Flag | Description |
| --- | --- |
| `--agents-mode` | `none`, `labeled_rule_base`, or `llm` |
| `--steps` | Override `simulation.steps` |
| `--run-id` | Override output run id when using the default results root |
| `--output-dir` | Write directly to a directory path |
| `--results-root` | Override `src/experiments/results` (also `EA_RESULTS_ROOT`) |
| `--set KEY=VALUE` | Dot-notation deep override |
| `--override-file` | YAML/JSON patch merged into scenario config |
| `--backend` | `mock` or `ros2` (`ssos_eclss_loop` only) |
| `--apply-proposals` | Apply prior `design_proposals.json` (`ssos_eclss_loop`) |
| `--seed` | Record a seed in `summary.json` for future sweeps |
| `--no-recreate` | Keep an existing output directory |
| `--dry-run` | Resolve the plan without executing |
| `--write-spec` | Write the resolved `RunSpec` JSON |
| `--json` | Machine-readable result on stdout |
| `--quiet` | Print only the output path |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Simulation execution failed |
| 2 | Invalid arguments or unknown scenario |
| 3 | Environment error (for example Ollama unreachable in `llm` mode) |

## Viewing results

```bash
ea results
python3 -m streamlit run src/tools/dashboard/app.py
```

## Parallel runs (future)

Each simulation is described by a `RunSpec` JSON file. A future batch runner can fan out many specs to workers that all call:

```bash
ea job run /worker/jobs/job-0042.json
```

Draft batch manifest (not implemented):

```yaml
batch_id: sweep_2026_06_27
jobs:
  - scenario: scrubber_degradation
    overrides:
      agents:
        mode: labeled_rule_base
      simulation:
        steps: 50
    run_id: sweep_0001
```

## Legacy entry points

These still work and delegate to the same execution path:

- `python3 src/scripts/run_mock_eclss.py`
- `python3 -m scenario.ssos_eclss_loop.scenario_run`
- `from scenario.runner import run_scenario`
