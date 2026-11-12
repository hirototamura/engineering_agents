# Run cube evaluations and campaigns

Prepare the [SSOT store and dependencies](configuration.md) first. Use a new run ID or destination for every execution. A nonempty cube run directory is rejected even if `--force` is supplied.

## Evaluate a frozen design

```bash
PYTHONPATH=src python -m tools.cli run balancing_cube \
  --design-mode none --backend mujoco_cpu \
  --set ssot.path=/path/to/onepiece-store \
  --run-id cube-reference-01 --dry-run --json
```

Dry-run requires a store path but does not establish that the store or simulator can execute. Inspect the plan, then remove `--dry-run --json`. The run screens the frozen reference and performs its validation work without requesting LLM proposals. To evaluate a reviewed proposal, use a fresh run ID and add `--apply-proposals /path/to/design_proposals.json`.

To search, select `--design-mode llm` with a reachable service and explicit budgets, for example `--iterate 3 --set iteration.max_candidates=8 --set iteration.max_wall_s=900`. Use `--backend mjx_gpu` only in the prepared GPU environment. Inspect the selected candidate and [verification status](results.md); a completed CPU run can still select only a provisional design.

## Prepare Isaac evidence

Isaac is a separate measured campaign path. Export uses the Engineering Agents environment; convert and audit use the explicitly selected Isaac Python. Replace `GPU-REPLACE_WITH_ALLOCATED_UUID` below with the UUID of one GPU allocated to your run. Conversion requires this UUID selection; pilot and batch also require exactly one visible CUDA GPU (batch checks its identity).

```bash
PYTHONPATH=src python -m tools.cli isaac prepare export \
  --store /path/to/onepiece-store --output /path/to/new-isaac-input \
  --snapshot-revision bottom-corner-000-20261017-3
CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID PYTHONPATH=src python -m tools.cli isaac prepare convert /path/to/new-isaac-input \
  --python /path/to/isaac-python
PYTHONPATH=src python -m tools.cli isaac prepare audit /path/to/new-isaac-input \
  --python /path/to/isaac-python
```

Export writes `cube.xml` and `input.json`; conversion and USD audit retain their own records. Export's `--proposal` takes a direct proposal, not a wrapper containing `selected_candidate`.

For pilot and batch, prefix each command with `CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID` (using the allocated UUID):

```bash
CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID PYTHONPATH=src python -m tools.cli isaac run pilot INPUT \
  --python ISAAC_PYTHON --output NEW_RUN
CUDA_VISIBLE_DEVICES=GPU-REPLACE_WITH_ALLOCATED_UUID PYTHONPATH=src python -m tools.cli isaac run batch INPUT \
  --python ISAAC_PYTHON --cases CASES_JSON --output NEW_RUN
```

Pilot checks wiring. Batch runs declared cases; video requires exactly eight cases. `isaac run campaign INPUT --python ISAAC_PYTHON --output NEW_CAMPAIGN` runs the campaign with an explicit Isaac runtime. Campaigns require balanced eight-corner coverage in each GPU shard and permit allocated GPUs 0–5. Use each command's `--help` for duration, count, seed, GPU allocation, and timeout.

## Inspect an Isaac campaign

`isaac analyze CAMPAIGN` writes `statistics.json` and `screened-trials.json` only after completeness and provenance checks. `isaac analyze CANDIDATE --reference REFERENCE --output NEW_COMPARISON_JSON` compares identical frozen trial plans. `isaac plot PATH` plots available telemetry. `isaac propose CAMPAIGN --output NEW_DIR` creates a bounded mechanical proposal from evidence; it does not validate it.

All export/run/proposal destinations must be new. A pilot, authored-USD audit, statistical comparison, and physically validated design are different outcomes. Interpret them using [cube results](results.md).

## Isolate mechanics from controller changes

The original study retains a four-cell comparison when both change:

| | Frozen controller | Proposed controller |
| --- | --- | --- |
| Frozen reference mechanics | `M0C0`: comparison reference | `M0C1`: control effect |
| Proposed mechanics | `M1C0`: mechanical effect | `M1C1`: joint change |

All cells use matched declared conditions. The reference is the run's frozen comparison design, not automatically the last proposal. Compare cells before attributing a benefit to geometry or gains; an apparent joint gain can hide a regression in one component.

## Analyze existing Isaac trajectories

The original campaign-analysis tools also read compatible archived data without the Isaac GPU runtime. After obtaining existing campaign evidence, use fresh output directories:

```bash
PYTHONPATH=src python -m tools.isaac_analysis prepare \
  --campaign reference=/path/to/reference-campaign \
  --campaign candidate=/path/to/candidate-campaign --output /path/to/new-analysis-cache
PYTHONPATH=src python -m tools.isaac_analysis serve \
  --dataset /path/to/new-analysis-cache --port 8526
```

The viewer binds to `127.0.0.1`. Its filters select recorded cases; they do not simulate a new gain, delay, or geometry. Inventory, selection, quantiles, and export commands are listed by `PYTHONPATH=src python -m tools.isaac_analysis --help`. The detailed historical `report` narrative is pinned to its original campaign protocol and refuses incompatible inputs. Read the [quantile and denominator rules](results.md#isaac-distributions) before comparing bands.
