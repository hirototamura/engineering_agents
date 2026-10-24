# Isaac campaign analysis tools

The [private analysis Release](https://github.com/hirototamura/balancing-cube-simulation/releases/tag/isaac-analysis-20261024)
provides the standalone 3,300-word technical report, all eight-corner figures and
a 194 MB pack containing the prepared data, quantile CSV/JSON, source hashes and
analysis code. The [checksum receipt](https://github.com/hirototamura/engineering_agents/blob/e8b84b0db8cf12466912f5a8e6819a8ff101b819/deploy/eng-agents-008/isaac-analysis-20261024.json)
pins the archive. Source review is [PR #86](https://github.com/hirototamura/engineering_agents/pull/86).

For this host, the viewer uses `.runtime/isaac-analysis-20261024-003` and listens
at `http://127.0.0.1:8526`. After restoring the private pack on another host,
pass its extracted `.runtime/isaac-analysis-20261024-003` directory to `serve`;
the original GPU runtime is not required to analyze the prepared tilt data.

## Reading the report and using the viewer

The [reading edition and viewer evidence](https://github.com/hirototamura/balancing-cube-simulation/releases/tag/isaac-analysis-readable-20261024)
provides the updated standalone HTML and a 6.3 MB presentation/validation pack.
The [reading-edition checksum receipt](https://github.com/hirototamura/engineering_agents/blob/codex/isaac-campaign-analysis-20261024/deploy/eng-agents-008/isaac-analysis-readable-20261024.json)
pins its source and hashes. The original release and prepared dataset remain
available at the link above.

The reading edition follows the typography, paper colors and section navigation
of `website/content/balancing-cube/index.html`. It brings the paired findings and
eight-corner plots ahead of the detailed protocol, retains all twelve technical
sections, and embeds every figure for offline reading. The generated Markdown,
quantile data, numerical statistics and source catalog are unchanged.

The viewer has four tabs: **Tilt trajectories**, **Test setup**, **Cases & exports**
and **Full technical report**. Choose a reference design, candidate design or
comparison, then a tilt preset or custom initial-condition range. Advanced
filters remain available for geometry, rotation direction, identities and
outcomes. Fixed gains and delays appear as recorded settings rather than
disabled controls. Comparison pass rates retain separate design denominators.
Eight larger plots use two columns; full-range and near-upright views use the
same unchanged quantiles. The setup tab shows mechanical properties in mm/g,
observation timing, readable gain matrices and expandable exact source records.

Attach a generated report when launching the viewer:

```bash
python -m tools.isaac_analysis report --dataset DATASET --output NEW_REPORT_DIR
python -m tools.isaac_analysis serve --dataset DATASET \
  --report NEW_REPORT_DIR/technical-report.html --port 8526
```

From your PC, forward the server port using your usual SSH destination:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 18526:127.0.0.1:8526 one-piece@10.10.0.108
```

Keep the terminal open, visit `http://127.0.0.1:18526`, and select
**Full technical report** to read it or download the self-contained HTML to
your PC. The full report covers the complete historical campaigns; sidebar
filters affect the trajectory and case tabs, not the historical report.

The analysis package reads existing evidence. It does not launch physics,
change requirements, tune a controller, or rewrite historical results.

The 2026-10-24 analysis covers both 24,576-case campaigns (49,152 recorded
episodes), with 3,072 cases per corner per configuration. The full technical
report identifies resolved mechanics, the exact 2×6 controller matrix and yaw
gain, initial states and seeds, observation timing, solver overrides, screening
gates, telemetry limitations, and the paired architecture comparison.

## Monte Carlo interpretation

The plots show central **68.3%, 95.5%, 99.7% and 100% empirical coverage** plus
the median at each time. Quantiles use all selected cases, with linear sample
interpolation. The bands are pointwise state distributions, not confidence
intervals or Gaussian assumptions. Distinct mechanical configurations are
plotted separately rather than silently pooled.

Two explicit stopping policies are available:

- `all-recorded`: every case contributes at all 401 timestamps, including free
  evolution after its controller is stopped. A fallen cube settling at 57° is
  recorded motion, not successful balancing.
- `evaluation-only`: each case contributes through its recorded stop sample,
  inclusively. Later bands condition on survivors. Per-time sample counts and
  evaluated-at-six-seconds counts are supplied. Missing values are not filled.

For reference corner 001 at 3 s, the upper 97.75 percentile is approximately
57.245° for all recorded cases, versus 0.176° for cases still in their recorded
evaluation interval. Ignoring that denominator change hides the failed cases.

The planned release radius is uniform from 0 to 5°, not uniform over disk area.
Azimuth and yaw rate are also randomized; mechanics, gains and observation delay
are fixed within each campaign. The two designs share the exact initial/noise
plan. There is no communication-network latency or delay sensitivity sweep.

## Agent CLI

Run from the workspace's `engineering_agents` checkout using the development
Python environment. Always choose fresh output directories.

```bash
../.venv/bin/python -m tools.isaac_analysis inventory \
  --campaign reference=../.runtime/isaac-cube/reference-24576-002

../.venv/bin/python -m tools.isaac_analysis prepare \
  --campaign reference=../.runtime/isaac-cube/reference-24576-002 \
  --campaign candidate=../.runtime/isaac-cube/candidate-24576-001 \
  --output ../.runtime/new-analysis-cache

../.venv/bin/python -m tools.isaac_analysis select \
  --dataset ../.runtime/new-analysis-cache --where selection.json \
  --output ../.runtime/new-case-selection

../.venv/bin/python -m tools.isaac_analysis quantiles \
  --dataset ../.runtime/new-analysis-cache --where selection.json \
  --mode all-recorded --all-trajectories --output ../.runtime/new-quantile-export

../.venv/bin/python -m tools.isaac_analysis report \
  --dataset ../.runtime/new-analysis-cache --output ../.runtime/new-report

../.venv/bin/python -m tools.isaac_analysis serve \
  --dataset ../.runtime/new-analysis-cache --port 8526
```

The viewer binds only to `127.0.0.1`. It provides eight axes, percentile tooltips,
mechanical and control/timing factor selectors, initial-state ranges, exact
seeds/case IDs, GPU and outcome selection, two post-stop policies, near-upright
vertical zooms, all-case trajectory exports, and downloadable filters/case
lists/percentile CSV. Controls with one recorded value identify that fixed value;
they cannot fabricate a parameter sweep. Selecting a recorded outcome is
explicitly labeled as conditional descriptive analysis.

Example `selection.json`:

```json
{
  "campaign": ["reference"],
  "initial_tilt_radius_deg": [0, 2],
  "initial_yaw_rate_rad_s": [-0.5, 0.5],
  "observation_delay_s": [0.015, 0.015],
  "gpu_indices": [0, 1, 2, 3, 4, 5]
}
```

Numeric filters use inclusive `[minimum,maximum]`. Category filters use lists.
Use `seed_values` for exact seeds and `seed` for a numeric seed interval.
Unknown fields, invalid intervals, duplicate case indices, differing time grids,
missing cases, and mixed-design quantile pooling fail visibly. Empty selections
retain all eight corner slots with zero counts and null quantiles.

## Model-facing tool collection

`tools.isaac_analysis.agent_tools.TOOL_SCHEMAS` describes four bounded tools:

| Tool | Result |
|---|---|
| `isaac_inventory` | Recorded factors, exact gains and dataset coverage |
| `isaac_select` | Selection counts, eight-corner summaries and at most 100 preview IDs |
| `isaac_tilt_quantiles` | All-case percentiles for one campaign, at most 32 requested time indices |
| `isaac_paired_outcomes` | Paired screening changes, exact McNemar tests and Holm adjustment |

```python
from tools.isaac_analysis.agent_tools import IsaacAnalysisTools, TOOL_SCHEMAS

tools = IsaacAnalysisTools("../.runtime/new-analysis-cache")
result = tools.call("isaac_tilt_quantiles", {
    "where": {"campaign": ["reference"], "initial_tilt_radius_deg": [0, 2]},
    "mode": "evaluation-only",
    "time_indices": [0, 67, 200, 400]
})
```

The caller chooses an audited dataset at construction. The tool calls cannot
read arbitrary additional paths, run a model, launch physics, or alter a gate.
Preview IDs are explicitly marked incomplete when truncated. Full-resolution
CSV/JSON and all case IDs are available through CLI exports.

The detailed `report` narrative is intentionally pinned to the original two
input digests and the frozen 24,576-case plan. It refuses other protocols instead
of printing the original settings for changed physics. The inventory, selection,
quantile and viewer tools operate on other compatible recorded campaigns.

## Evidence audit and limitations

Preparation checks plan/input/source-copy hashes, source/design/GPU identifiers,
case order and completeness, dimensions, timestamps, finite raw telemetry,
stop/status consistency, initial tilt consistency and historical peak summaries.
The near-upright float32 `acos` calculation is quantized: one planned 0.003108°
release is recorded as 0.027976°. The declared 0.06° initial-state consistency
tolerance accommodates this arithmetic effect; it is not an acceptance margin.

All source files read and derived cache files receive SHA-256 hashes. The old
large-campaign manifests did not individually hash telemetry. New analysis hashes
identify the bytes analyzed without retroactively changing that limitation.

The tilt channels are geometric truth, not the noisy controller feedback.
Post-stop motor channels contain a hypothetical computed request even though
actual sent effort was zero. Do not infer post-stop actuation from them. Raw
quaternions, root positions, wheel angles and per-physics-step effort were not
archived, so full case videos cannot be exactly reconstructed from tilt alone.

These are numerical exploration results. MuJoCo/PhysX agreement remains
inconclusive; physical acceptance and fresh held-out design confirmation remain
unestablished. See the full report for the exact scope and assumptions.
