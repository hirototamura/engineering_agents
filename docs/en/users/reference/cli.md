# CLI reference

Run from a prepared checkout with `PYTHONPATH=src python -m tools.cli`. The installed `ea` script calls the same application when it belongs to this checkout. `--help` on a command shows its current options; `--version` prints the package version.

## Commands

- `scenarios`: list the three bundled scenario IDs and descriptions.
- `run [scenario]`: execute a scenario. With no argument, select `scrubber_degradation`; with `--iterate` and no scenario, select `ssos_eclss_loop`.
- `results [run_id]`: list recent summaries or print one. `--track eclss|balancing_cube` selects the default track; `--limit` defaults to 10.
- `doctor`: report Python, dependencies, Docker/SSOS, output root, and model-service reachability. It is not a full scenario validation.
- `job run SPEC.json`: execute one saved RunSpec. A saved single-run spec does not replay the orchestration of an automatic design chain.
- `reports [build|serve|translate|capture|verify]`: inspect and maintain a workspace report library; default action is `build`. See [reports](../guides/reports.md).
- `isaac prepare|run|analyze|plot|propose`: prepare and inspect cube experiments with Isaac. See [cube running](../scenarios/balancing_cube/running.md).

## Run controls

`--run-id`, `--output-dir`, and `--results-root` select destinations. `--override-file` loads a YAML/JSON patch; repeatable `--set key=value` and named flags override it. `--dry-run` builds a plan; `--write-spec PATH` writes execution input even during a dry-run. `--json` selects machine-readable output and `--quiet` reduces normal output. See [configuration](configuration.md) for precedence and directory behavior.

ECLSS/scrubber use `--steps`, agent modes, and `--seed` as applicable. ECLSS has separate `--actor-mode` and `--design-mode`, `--backend`, `--inject-failures`, `--apply-proposals`, `--iterate 1..50`, paired replay, and provisional-approval controls. Its exact defaults and supported combinations are owned by [ECLSS configuration](../scenarios/ssos_eclss_loop/configuration.md).

Cube dispatches through `run balancing_cube` but has a separate backend, SSOT, iteration, and mode contract. Generic help is ECLSS-oriented; use [cube configuration](../scenarios/balancing_cube/configuration.md) before applying these flags. Scrubber supports [its own agent modes](../scenarios/scrubber_degradation/configuration.md) and has no proposal reinjection.

## Exit status

`0` means execution completed, `1` a run failure, `2` a user/configuration error, and `3` an environment error. Cube also uses `2` for an inconclusive workflow. A zero exit status does not mean an engineering constraint passed; inspect the scenario's evaluation.

## Match the command to the artifact you need

| Task | Command form | Main result |
| --- | --- | --- |
| Check a single-run plan | `run SCENARIO … --dry-run --json` | RunSpec-style execution input; no simulation |
| Preserve a single execution specification | `run SCENARIO … --write-spec PATH` | JSON controls/overrides, not all merged defaults |
| Execute that specification | `job run PATH` | One scenario run |
| Read a completed default-root run | `results RUN_ID --track TRACK` | Existing `summary.json` |
| Discover workspace reports | `reports build --workspace PATH` | Derived catalog |
| Prepare/inspect Isaac experiments | `isaac ACTION …` | Stage-specific cube evidence |

For ECLSS chains, console dry-run output shows the count and parent directory; JSON/spec output describes the child RunSpec and is not a complete chain replay recipe. Preserve the chain command and repository revision as well.
