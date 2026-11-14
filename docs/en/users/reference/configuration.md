# Configuration reference

Each bundled scenario has a `scenario.yaml` under `src/scenario/<scenario>/`. ECLSS and scrubber also have `agents.yaml`; the scenario's `agents` section overrides it. These are configuration inputs for existing scenarios. The CLI does not load arbitrary external scenario packages.

## Merge and value rules

For ECLSS/scrubber, priority increases from bundled configuration to `--override-file`, repeated `--set`, and named options such as `--steps` or `--actor-mode`. Mappings merge recursively; other values, including lists, replace the previous value. `--set` parses booleans, null, integers, and decimal numbers; use a YAML/JSON patch for structured lists. Unknown `--set` paths are rejected against the merged scenario/agent keys, with a limited iteration-default exception.

Environment-backed settings are resolved separately: `SSOS_ECLSS_BACKEND` supplies an unselected ECLSS backend; LLM environment settings can override service configuration. [LLM setup](../guides/llm.md) states those rules. Explicit ECLSS backend configuration wins over the backend environment default. Cube performs its own [restricted override validation](../scenarios/balancing_cube/configuration.md).

`--write-spec` saves the RunSpec controls and override patch. It is not an immutable snapshot of every bundled default. Completed ECLSS/scrubber runs write `scenario_config.yaml` and, when agents are configured, `agents_config.yaml`. Cube saves its SSOT-derived inputs and evidence under its own contract.

## Output directories { #output-directories }

ECLSS/scrubber use `experiments/eclss/results/<run_id>/`; cube uses `experiments/balancing_cube/results/<run_id>/`. `EA_RESULTS_ROOT` overrides the default root for both tracks. An explicit `--output-dir` wins over root and run ID; otherwise `--results-root` wins over the environment/default root. Run IDs start with a letter or digit and contain letters, digits, `.`, `_`, or `-`; path separators and `..` are rejected.

Host-launched ECLSS `ros2` is an exception: it rejects `--output-dir` and requires the repository's `experiments/eclss/results` mounted at `/ea/results`. A custom root or `EA_RESULTS_ROOT` must resolve to that same mounted directory. Select a fresh `--run-id`; see [ROS2 setup](../scenarios/ssos_eclss_loop/running.md#prepare-ros2-ssos).

ECLSS/scrubber recreate an existing recognized run or chain directory by default. This deletes its old artifacts. Arbitrary non-run contents are protected unless `--force` is passed. For a single run, `--no-recreate` avoids initial deletion but does not implement resume: streams may append while configuration and summaries are overwritten. For an ECLSS chain it only preserves the parent directory; chain memory is cleared and numbered child runs and paired replays are recreated. Reusing a chain ID can therefore replace prior evidence even with this flag. Use a fresh run ID or new parent directory to retain the previous chain.

Cube always preserves prior evidence and rejects a nonempty destination; neither recreate defaults nor `--force` grants replacement. See its [running guide](../scenarios/balancing_cube/running.md).

## Scenario-specific values

Use [scrubber configuration](../scenarios/scrubber_degradation/configuration.md), [ECLSS configuration](../scenarios/ssos_eclss_loop/configuration.md), or [cube configuration](../scenarios/balancing_cube/configuration.md) for units, defaults, allowed design variables, and prerequisite services. A similarly named setting does not imply equivalent physics across scenarios.

## Worked merge example

Suppose the override file contains `simulation.steps: 20`, the command adds `--set simulation.steps=30`, and it also passes `--steps 40`:

| Layer applied | Value after that layer |
| --- | ---: |
| Override file | 20 |
| `--set simulation.steps=30` | 30 |
| `--steps 40` | 40 |

The effective run uses 40 steps. This illustrates precedence, not a recommended horizon. A list behaves differently from a mapping: replacing `anomalies` replaces that list, while patching one nested mapping key leaves its siblings intact. Inspect the saved effective configuration to verify the result.
