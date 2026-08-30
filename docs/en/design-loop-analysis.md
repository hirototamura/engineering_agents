# Design-loop analysis

`tools.analysis` treats an Engineering Agents campaign as a **dynamical system on a design space** and provides the statistics, experiments and figures needed to characterise it: identify the order parameter, locate the transition, measure the response, and only then judge the controller.

It answers questions the per-run dashboard cannot, because they are properties of the *ensemble* rather than of any single run:

- Which design variable actually governs the outcome, and where is its critical value?
- Can the design agent's proposals move the outcome at all, and by how much per unit of effort?
- Is the mission achievable inside the declared budget?
- Is the response surface smooth enough for greedy search to work?

---

## Quick start

```bash
# execute the experiment battery (about 340 simulations, ~1 minute on 4 workers)
python3 -m tools.analysis run

# analyse the datasets and write the English and Japanese HTML reports
python3 -m tools.analysis report
python3 -m tools.analysis report --lang ja   # Japanese only

# both, in order
python3 -m tools.analysis all
```

Outputs land under `src/experiments/analysis/`:

| Path | Contents |
| --- | --- |
| `design_loop_analysis.html` | English report, one file, no external assets |
| `design_loop_analysis.ja.html` | Japanese report (same numbers, translated prose) |
| `design_loop_analysis.findings.json` | every computed number, for diffing and regression |
| `datasets/*.json` | one flat row per run, per experiment block |
| `datasets/chain_dynamics.json` | serialised loop trajectories (`ChainDynamics`); `report` reconstructs order parameters from this file when raw `chains/` dirs are absent |
| `<block>/<run_id>/` | the raw run directories (git-ignored, regenerable) |

`run` caches by run directory, so an interrupted campaign resumes instead of restarting, and `report` can be re-run as often as needed without touching the simulator. A fresh checkout does not need the git-ignored `chains/` directories: loop archetypes, step norms and figures come from `datasets/chain_dynamics.json`.

`--iterate` chains cannot take `--apply-proposals`. A campaign that starts a chain from a non-shipped design bakes the starting nameplate into `--set plant_sim.ars.capacity_kg_day=…` (and the OGS / WRS equivalents) instead.

Useful flags: `--quick` thins every grid to three points for a smoke test, `--workers N` sets parallelism, `--steps N` changes the mission length, `--no-cache` forces re-simulation, and `--root DIR` moves the whole tree.

---

## The order parameter

The three sizing variables (`plant_sim.ars.capacity_kg_day`, `plant_sim.ogs.max_o2_kg_day`, `plant_sim.wrs.max_feed_l_per_operation`) carry different units and baselines that differ by an order of magnitude, so they cannot be compared directly. Dividing each by the crew's daily demand for the same quantity gives a dimensionless **coverage ratio** whose unit point is physically meaningful:

$$
\rho_{\text{ARS}} = \frac{\text{CO}_2\ \text{removal capacity}}{N \cdot \dot m_{\text{CO}_2}}, \qquad
\rho_{\text{OGS}} = \frac{\text{O}_2\ \text{generation capacity}}{N \cdot \dot m_{\text{O}_2}}, \qquad
\rho_{\text{WRS}} = \frac{\text{WRS throughput}}{N \cdot (\dot m_{\text{urine}} + \dot m_{\text{cond}})}
$$

`ρ = 1` is the smallest station that services the crew in steady state. The shipped `ssos_eclss_loop` station sits at **ρ_ARS = 0.087** and **ρ_OGS = 0.220** for 50 crew — undersized by a factor of eleven and five.

Distances in design space are measured in `log ρ`, because sizing is multiplicative: the sizing model is affine in the capacity *ratio*, and the rule designer applies a constant multiplicative gain, so a doubling should cost the same wherever it starts.

```python
from tools.analysis.design_space import coverage_ratios, crew_demand

coverage = coverage_ratios(scenario_config)
coverage.minimum            # the binding coverage
coverage.binding_subsystem  # "ars" | "ogs" | "wrs"
```

### The actuation space

A designer may move more than hardware, and the three places it can push behave very differently:

| Subspace | Example axis | Stored in | What it changes |
| --- | --- | --- | --- |
| `capacity` | `plant_sim.ogs.max_o2_kg_day` | scenario config | installed nameplate throughput |
| `action` | `agents.actor.policy.ogs_goal.input_water_mass` | agents config | the payload the crew sends to existing hardware |
| `policy` | `thresholds.co2_storage_high_kg` | scenario config | the band edge that decides when the crew acts |

`actuation_vector()` returns a log coordinate spanning all three, with the shipped configuration at the origin. Keeping them in one vector is what makes *"the loop did not move"* and *"the loop moved somewhere useless"* distinguishable — they look identical in an outcome plot and have opposite fixes.

---

## Experiment blocks

| Block | Varies | Answers |
| --- | --- | --- |
| `seed_replicates` | `--seed` only | is the plant stochastic? |
| `response_surface` | ARS × OGS nameplate (11 × 11) | phase diagram, criticality, cost of survival |
| `one_at_a_time` | one axis, shipped operating point | controllability where the loop starts |
| `one_at_a_time_relieved` | one axis, OGS sized to 42 kg/day | controllability once O2 is not binding |
| `crew_scaling` | crew size, station fixed | denominator half of the collapse test |
| `iso_ray` | all capacities by a common factor | numerator half of the collapse test |
| `chains` | `--iterate` length | the closed loop actually running |

A design is imposed by writing a one-change `capacity_profile` proposal and passing it to `--apply-proposals`, which is the same path the tool-use designer uses to adopt a candidate. The experiment grid and the agent's own proposals therefore move through identical code.

!!! note "Capacity changes carry their payload"
    Applying a capacity change also runs `sync_action_payloads`, which raises the crew's request to what the new hardware can honour. Every response-surface point is therefore a *well-operated* station rather than new hardware driven by stale procedures. The one-at-a-time sweeps deliberately do not sync, so they isolate the payload axis on its own.

---

## Where the uncertainty is

With rule-based actors and designers the whole pipeline is **deterministic**: replaying one configuration under six different seeds reproduces the evaluation score and the surviving crew count exactly (spread `0.0`). There is no replicate noise to bootstrap over.

Every interval the analysis reports is therefore taken across **design points and scenario conditions**, which is where the variation genuinely lives. Susceptibility is the *derivative* of the response, not a variance over replicates. Stochasticity would enter only through an LLM designer, which needs a reachable provider.

---

## What the shipped configuration measures

Results below come from 341 simulations on the `plant_sim` backend with `labeled_rule_base` actors and designers, 72 steps, 50 crew.

### Conservation holds

The physics gate recomputes each mass ledger independently of the state it audits and passed in 341 of 341 runs. The worst residual is `1e-12` L of water against a `2e-6` tolerance; the O2 and CO2 ledgers are identically zero.

### The mission is infeasible under its own budget

Of 121 designs on the grid, 18 keep the whole crew alive and **zero** of those fit inside `design_constraints.budgets`. The lightest surviving station masses 4,683 kg against a 4,000 kg ceiling and costs 696 MUSD against 500 MUSD. No design agent can satisfy both. Under this repository's stated hierarchy — the mission is paramount and design requirements may be revised beneath it — the budget is the requirement that has to move.

### A compact predictive law

Fitted on half the grid and scored on the other half:

| Model | Held-out R² | Balanced accuracy |
| --- | ---: | ---: |
| constant | −0.012 | 0.500 |
| ARS only | −1.384 | 0.627 |
| OGS only | 0.633 | 0.833 |
| Liebig on coverage — `min(ρ_ARS, ρ_OGS)` | 0.396 | 0.881 |
| Liebig on margin — `min(ρ_i / ρ*_i)` | 0.886 | 0.902 |
| series (product of responses) | 0.902 | 0.912 |
| **Liebig on response — `min` of the two responses** | **0.936** | 0.902 |

The law of the minimum *as usually stated* does badly, because the two subsystems do not become critical at the same coverage (ρ*_ARS ≈ 0.17, ρ*_OGS ≈ 0.74). Taking the raw minimum names the wrong bottleneck wherever the numerically smaller coverage is the one with the lower threshold. **The quantity that matters is each subsystem's margin against its own threshold, not its raw coverage.**

### Controllability is state-dependent

At the shipped operating point, only `plant_sim.ogs.max_o2_kg_day` has non-zero gain. Every action and policy axis measures exactly zero: sweeping them over a 20-fold range leaves the surviving crew unchanged, because the plant delivers `min(request, nameplate)` and reports `limited_by: ["ogs_capacity"]` on 100 % of operations at or above the shipped request.

Relieve the oxygen famine (OGS = 42 kg/day) and several of those axes come alive:

| Axis | Subspace | Gain at shipped point | Gain with O2 relieved |
| --- | --- | ---: | ---: |
| `ars_action_co2_mass` | action | 0 | 1.076 |
| `ars_capacity_kg_day` | capacity | 0 | 1.076 |
| `o2_threshold_low` | policy | 0 | 1.076 |
| `co2_threshold_high` | policy | 0 | 0.538 |
| `ogs_max_o2_kg_day` | capacity | 1.165 | 1.165 |

The shipped designer's preferred axis is not useless in general — it is useless *until a different subsystem is fixed first*. One-at-a-time sensitivity measured at a single operating point would have concluded the axis was dead; the second sweep is what distinguishes the two cases.

### The closed loop saturates

All three `labeled_rule_base` chains land in the **saturating** archetype: the loop moves steadily and the outcome never changes.

- Step size is constant at `0.386` log units (= √3 · ln 1.25, a fixed +25 % gain on three action axes), never decaying.
- Turning cosine is pinned at `+1.000` — a perfectly straight march, never a search.
- 100 % of step magnitude lands in the `action` subspace, 0 % in `capacity`.
- 40 % of proposals are discarded before simulation: the chain strips every `set_parameter` change to keep verification requirements frozen, but the designer is never told, so it re-proposes the identical threshold change on every iteration.

### The landscape is not monotone

16 % of capacity increases along the ARS axis make the outcome *worse*, with a worst single descent of 0.24 crew fraction. Adding hardware can cost lives because operations are scheduled against a busy guard: a larger batch occupies the subsystem for longer and can miss the window in which the next one was needed. Single-evaluation hill climbing is unreliable here, which is an argument for the tool-use designer's multi-candidate re-simulation rather than for a larger step size.

---

## Trajectory archetypes

Chains are classified into a mutually exclusive, exhaustive taxonomy, tested in order:

| Archetype | Meaning |
| --- | --- |
| `frozen` | no design change is proposed after the first run |
| `saturating` | the loop keeps moving but the outcome never changes |
| `converging` | the outcome improves and the step size decays |
| `overshooting` | the outcome improves after at least one reversal in direction |
| `oscillating` | direction reverses repeatedly without a sustained improvement |

The first split is the important one. A loop that proposes nothing and a loop that proposes something ineffective are different failures with opposite fixes.

---

## Module map

| Module | Responsibility |
| --- | --- |
| `design_space` | coverage ratios, actuation vector, footprint, budgets, bounds |
| `artifacts` | read run and chain directories into flat rows |
| `statistics` | bootstrap, permutation, Cliff's delta, logistic fit, Kaplan-Meier, log-rank, balanced accuracy |
| `loop_dynamics` | chain order parameters, archetypes, controllability, effective gain |
| `experiments` | `RunSpec`, the CLI-driving executor, and the spec builders |
| `campaign` | the standard battery and its grids |
| `figures` | matplotlib figures rendered to inline SVG |
| `report` | findings dictionary and the HTML document |

Dependencies stay inside the project's existing set — numpy, matplotlib, PyYAML — so the analysis runs in the same environment as the simulator. The estimators are implemented directly rather than pulled from SciPy; each is small enough to read and is unit-tested against a closed-form case.

The layering rule (`tools → scenario → environment → core`) holds: this package reads scenario modules and run artifacts, and nothing reads it.

---

## Extending it

**Add an experiment block.** Write a spec builder in `experiments.py` returning `list[RunSpec]`, register it in `campaign.build_specs`, and add its rows to `CampaignResult`.

**Add an actuation axis.** Add an entry to `design_space.ACTUATION_AXES` with its subspace, config source, dotted path and shipped value. Displacement, step norms and subspace shares pick it up automatically. Add it to `experiments.OAT_AXES` to have its controllability measured.

**Add a figure.** Write a `fig_*` function in `figures.py` taking flat rows and returning an SVG string via `to_svg`, then call it from `report.render` with a caption.

**Run against an LLM designer.** With a provider reachable, `chain_specs(..., design_mode="llm")` exercises the tool-use designer that can emit `capacity_profile` changes. The controllability and phase-diagram results characterise the plant and apply to any designer; the loop-dynamics results characterise whichever designer produced the chains.

---

## Limits

- Both agent sides run in `labeled_rule_base` mode in the shipped battery. The tool-use designer that *can* resize hardware is not exercised without an LLM provider.
- All runs use `plant_sim`. The `mock` backend produces no survival or scorecard data; `ros2` needs SSOS Docker.
- Failure injection is off in the sweeps so that coverage is the only thing varying. The chains keep the shipped default, which enables it.
- The grid holds WRS fixed, justified by its measured zero gain and a baseline coverage of 6.4.

The self-contained HTML reports at `src/experiments/analysis/design_loop_analysis.html` (English) and `design_loop_analysis.ja.html` (日本語) are the numbered documents; this page is the operator's guide to regenerating them.

## See also

- [ssos_eclss_loop scenario](scenario-ssos-eclss-loop.md) — the simulation being analysed
- [CLI guide](cli.md) — the commands the harness drives
- [Tool-use design agent](memo/ssos_eclss_loop/tool_use_design_agent.md) — the designer that can act in the capacity subspace
- [技術説明 ver.04](/ja/eclss_ai_agent_technical_report_04/) — Japanese hackathon report; chapter 8 is the emergence visualization
- [技術説明 ver.03](/ja/eclss_ai_agent_technical_report_03/) — same report plus the quantitative analysis chapters
