# Configure a repeatable run

Begin with the selected scenario's configuration page. Choose the backend, agent modes, horizon, and acceptance conditions before running. Keep a separate run ID for each comparison.

## Save a small configuration patch

For a single local ECLSS run, create `local-run.yaml`:

```yaml
backend:
  kind: mock
simulation:
  steps: 20
agents:
  actor:
    mode: labeled_rule_base
  design:
    mode: labeled_rule_base
iteration:
  enabled: false
```

Preview and save the execution input:

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --override-file local-run.yaml --run-id local-review-01 \
  --dry-run --json --write-spec /tmp/local-review-01.json
```

`--dry-run` does not run simulation or check model-service reachability. `--write-spec` still writes its file. The specification records overrides and execution controls, not a complete copy of every merged default. Preserve the repository revision with it; completed runs also save effective configurations.

Inspect the plan, then repeat without `--dry-run --json` to run it. For a one-off adjustment, add `--set simulation.steps=30`; a named option such as `--steps 40` has higher priority. Exact merge and output behavior belongs to the [configuration reference](../reference/configuration.md).

## Judge completion

Open the output summary and confirm the selected scenario, backend, modes, horizon, and paths. Check the saved configuration rather than assuming a CLI default. A command finishing successfully does not mean the design met its requirements; continue with [inspect results](inspect-results.md).

For a design comparison, hold requirements, starting conditions, fault schedule, and evaluation version fixed. ECLSS chains freeze their comparison requirements; cube conditions and seeds come from the frozen SSOT snapshot. See [design iterations](design-iterations.md) for the appropriate handoff procedure.

## Declare what varies before comparing runs

The original comparison guides separated world conditions from agent choices. Keep that separation in a small experiment note:

| Part of the experiment | Example declaration | Why record it? |
| --- | --- | --- |
| World and initial state | Same selected backend, initial inventories, anomaly/fault schedule | A different world is a different experiment |
| Verification | Same requirements, horizon, evaluator revision | Avoid changing the yardstick |
| Variable being tested | Designer mode, candidate sizing, or one controller campaign | Make the comparison interpretable |
| External services | Resolved model/provider and generation settings | Model replies need not reproduce exactly |
| Output identity | Distinct baseline and candidate directories | Keep both sides available for review |

For a mode comparison, do not also change capacities and call the difference an agent effect. For a design comparison, check the consumed inputs and effective configuration rather than the filename alone.
