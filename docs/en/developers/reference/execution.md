# Internal execution contracts

This reference describes current Python/job behavior. Public options and defaults are owned by the [CLI reference](../../users/reference/cli.md).

## Run requests and results

[RunSpec](https://github.com/hirototamura/engineering_agents/blob/main/src/scenario/jobs/spec.py) carries `scenario`, optional `overrides`, output location (`output_dir`, `run_id`, `results_root`), `recreate_output`, `seed`, `apply_proposals_path`, `approve_provisional`, `design_history`, and `force`. Serialization converts the three path fields to strings and reconstructs `Path` objects on read. It is a dataclass representation, not a versioned external scenario manifest or comprehensive validation layer.

`approve_provisional` defaults to `False` on `RunSpec`. CLI policy may supply a different resolved value; do not infer job defaults from an interactive command. `RunResult` contains `run_dir`, `summary`, elapsed `duration_s`, `exit_code`, and optional `error`.

## Serialized request example

This constructed request illustrates the internal dataclass serialization; it is not an external scenario manifest and is not executed by this documentation.

```json
{
  "scenario": "scrubber_degradation",
  "overrides": {"simulation": {"steps": 3}, "agents": {"mode": "none"}},
  "output_dir": "/tmp/ea-contract-example",
  "run_id": null,
  "results_root": null,
  "recreate_output": false,
  "seed": null,
  "apply_proposals_path": null,
  "approve_provisional": false,
  "design_history": null,
  "force": false
}
```

| Field group | Serialization | Execution responsibility |
| --- | --- | --- |
| `scenario`, `overrides` | String and nested JSON-compatible mapping | Registry admission and scenario-owned validation |
| `output_dir`, `results_root`, `apply_proposals_path` | Paths become strings; reconstructed as `Path` | Supported dispatch branch interprets each path |
| `recreate_output`, `force` | Booleans retained | Generic output resolution; cube deliberately keeps immutable output |
| `seed` | Optional number retained | Executor overlays simulation seed; cube rejects it in favor of the frozen plan |
| `approve_provisional`, `design_history` | Retained in the request | Explicit scenario branches; not a generic adoption guarantee |

A request's ability to round-trip is independent of whether that scenario supports its fields. `from_dict()` constructs the dataclass; it does not negotiate capabilities or validate every nested configuration.

## Dispatch and completion

`execute_run(spec, on_step=None, on_phase=None)` uses the merged fixed registry. Unknown scenarios return code 2. Exceptions during scenario execution return code 1 and an error string. SSOS and cube have explicit dispatch branches; the generic branch does not receive all the fields in `RunSpec`.

After execution, `summary.json` must exist and parse as a non-empty object. A missing, truncated, array-valued, or empty-object summary returns code 1 without overwriting that file. Non-cube summaries gain elapsed time and an optional seed. Cube summaries remain synchronized immutable artifacts; final sync status can enrich the returned result separately. Cube `status: inconclusive` returns code 2. A zero execution code alone does not establish engineering acceptance.

ROS2 telemetry-reader teardown is attempted in `finally` after dispatch and tolerates cleanup failure. Scenario-specific cleanup, such as clearing injected failures, remains the scenario's responsibility.

## Entrypoints and limits

`python -m scenario.jobs SPEC.json` accepts one serialized request and returns its execution code. The Typer CLI also distinguishes user and environment errors (`0/1/2/3` in `tools/cli/exit_codes.py`); those categories do not redefine each scenario's result statuses. `run_scenario()` wraps execution and raises on nonzero results.

`Scenario` declares name, configuration loading, simulator/team construction, and `run()`. Actual runners extend that signature; cube is not its subclass. SSOS chain iteration supports only `ssos_eclss_loop`; cube rounds are a separate design-loop contract. Tests: `tests/scenario/test_run_spec.py`, `test_iterate.py`, `test_balancing_cube.py`, and `tests/tools/test_cli.py`.
