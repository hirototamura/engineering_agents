# Diagnose an unsuccessful run

Preserve the output directory, command, repository revision, and model-service settings before retrying. Use a fresh run ID so a retry cannot replace the evidence you need.

## The command or configuration is rejected

Use `PYTHONPATH=src python -m tools.cli --help` from the checkout root. An installed package can differ from the current source. Python 3.11 or newer is required. `--set` rejects unknown keys for ECLSS/scrubber; use the exact path from the scenario and agent configurations. An override file is a mapping, not a full external scenario definition.

If an ECLSS command unexpectedly starts a chain or needs an LLM, inspect [its defaults](../scenarios/ssos_eclss_loop/configuration.md). Pin backend, actor mode, design mode, and `--set iteration.enabled=false` for a single local run. Dry-run checks planning, not all runtime prerequisites.

## A service or backend is unavailable

Run `PYTHONPATH=src python -m tools.cli doctor`. Inspect reachability and the exact URL/model in the saved plan. Lab vLLM needs the relevant network; local Ollama must be running with the requested model. See [LLM setup](llm.md).

ROS2 ECLSS needs the SSOS container and mounts; `mock` and `plant_sim` do not. Cube needs an existing SSOT store plus [optional simulation dependencies](../scenarios/balancing_cube/configuration.md). Missing GPU validation is an explicit `not_run` result, not permission to report CPU validation as a GPU comparison.

## A result is missing or inconclusive

Check `summary.json` before opening a viewer. ECLSS's full scorecard requires `plant_sim` and survival tracking; mock results are not fully scored. Inspect `evaluation_status`, physics-gate and integrity records, and each axis's status. Cube's workflow can finish with `status: inconclusive`; inspect its reason and dependency/synchronization records.

A refused proposal may be unsupported by the backend, rejected, or awaiting supervisor approval. Do not bypass the gate merely to obtain a completion message. Read the owning [scenario results](../scenarios/index.md) and rerun only after deciding what conditions to change.

## An output directory cannot be used

ECLSS/scrubber normally replace recognized run directories. Arbitrary non-run directories need `--force`, which authorizes deletion. For a single run, `--no-recreate` avoids initial deletion but can append streams and overwrite summaries. For a chain it preserves only the parent: memory is cleared and child runs/replays are recreated. It is not resume or an evidence-retention guarantee. Cube rejects nonempty run directories. Use a new directory for clean evidence. See [output rules](../reference/configuration.md#output-directories).

## Triage from the first trustworthy record

| Symptom | Inspect first | Next action |
| --- | --- | --- |
| No output directory | CLI error and dry-run plan | Correct input or prerequisites before retrying |
| Directory exists but summary is missing/malformed | Partial streams and last phase/error | Preserve the partial run; do not label it completed |
| Proposal exists but did not change the next run | Approval reasons and consumed input | Check supported application and status gates |
| Full score missing on mock/ROS2 | Evaluation applicability | Choose evidence appropriate to the backend |
| Cube stopped before a new proposal | Reference result and synchronization state | Resolve the recorded failure/pending delivery |
| Viewer and hand calculation differ | Row selection, time window, units, denominator | Reproduce the owning scenario's interpretation |

Use a fresh destination for each retry. This preserves the failed record alongside the corrected one and makes the reason for the change reviewable.
