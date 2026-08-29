# Tool-use design agent — sizing ARS / OGS / WRS throughput

> **Scope**: the **post-run designer only** in `ssos_eclss_loop`. Runtime operations (actors) are in [labeled_rule_base.md](labeled_rule_base.md).
> The classic summary-reading designer is still there: [post_run_design_agent.md](post_run_design_agent.md).
> **Source**: design document “Tool-use-centred redesign of the SSOS ECLSS design agent” (2026-08-28).

## Why the rebuild

The classic designer built `design_proposals.json` from the post-run `summary` plus a slice of state. It never did what a human expert does:

- go and fetch the information it needs
- read the time series
- compute the theoretical demand
- **verify a candidate design by re-simulating it**

and `set_parameter` could not change plant_sim throughput at all. Raising `ars_goal.initial_co2_mass` through `action_profile` tunes the *operational payload*, not the size of the machine.

The new designer is **tool-use centred**. The model is not handed the run; it is handed a tool catalog. Arithmetic, aggregation, plotting and re-simulation live in deterministic tools.

## The design variables (exactly three)

| Design variable | Meaning | Unit |
| --- | --- | --- |
| `plant_sim.ars.capacity_kg_day` | ARS CO₂ removal throughput | kg/day |
| `plant_sim.ogs.max_o2_kg_day` | OGS O₂ generation cap | kg/day |
| `plant_sim.wrs.max_feed_l_per_operation` | WRS batch size | L/operation |

**Not design variables**: recovery efficiencies (`ars.capture_efficiency`, `wrs.urine_recovery`, `wrs.grey_recovery`), Sabatier conversion, crew metabolism, health thresholds. Those are material, catalyst, safety and policy choices; mixing them into a “size the hardware” problem blurs it.

Implemented in `src/scenario/ssos_eclss_loop/design_variables.py`. A `capacity_profile` proposal touching anything else is **rejected**.

### Automatic action-payload sync (important)

OGS is throttled by `ogs_goal.input_water_mass`: with a small request, a bigger nameplate does nothing. WRS has the same failure mode through `wrs_goal.urine_volume`. Applying a `capacity_profile` therefore raises those payloads:

```text
ogs_goal.input_water_mass >= ogs.max_o2_kg_day * ogs_operation_seconds / 86400 * WATER_PER_O2
wrs_goal.urine_volume     >= urine produced per step (clamped by the batch size)
```

Sync only ever **raises** a payload, so a hand-tuned operator profile is never silently shrunk. Disable per proposal with `payload.sync_action_payloads: false`.

## Per-step command rule and the busy guard

Two runtime constraints back the sizing problem (design doc §7):

1. **At most one command per subsystem per step.** ARS + OGS + WRS in the same step is fine; two `air_revitalisation` in one step is not. Extra commands become `/eclss/events/operational_rejected` with `reason=duplicate_command_this_step`.
   The gate lives in `SsosEclssLoopTeam.apply_outcome()` and is mode-independent. `max_actions_per_step` keeps its meaning (how many representatives join the action round).
2. **Operation duration / busy guard.** With `ars_operation_seconds = 4800` and `step_seconds = 1200`, an accepted ARS action occupies the subsystem for `ceil(4800/1200) = 4` steps. Commands during that window are rejected with `reason=subsystem_busy` and details `subsystem` / `remaining_steps` / `busy_until_step`. OGS and WRS run for one step, so they are available again next step. An action that processed nothing never ran, so it does not occupy the subsystem: WRS with no feed (`reason=no_feed`) and OGS with no water or a zero request (`reason=no_water`) both leave the machine free. An action that processed nothing never ran, so it does not occupy the subsystem: WRS with no feed (`reason=no_feed`) and OGS with no water or a zero request (`reason=no_water`) both leave the machine free.
   Implemented in `PlantSimEclssBackend`; revert with `plant_sim.operations.busy_guard_enabled: false`.

Consequence: ARS effective throughput is bounded by 18 actions/day, so the 4.5 kg/day nameplate visibly cannot meet the 52 kg/day that 50 occupants generate.

## Tool catalog

`src/scenario/ssos_eclss_loop/design_tools.py`. Every tool returns JSON and never raises; failures come back as `{"error": ...}`.

| Tool | What it does |
| --- | --- |
| `load_run_artifacts` | summary / configs / row counts and head+tail of each JSONL |
| `summarize_timeseries` | per column min/max/final, steps in warning / critical, first excursion, slope, cumulative shortfall |
| `compute_eclss_features` | subsystem stress, applied vs rejected commands by reason, crew loss causes, failure windows, final inventories |
| `compute_theoretical_capacity` | crew demand vs nameplate, **always accounting for the busy cadence and the ARS goal scale**; returns shortfalls and the required nameplate |
| `plot_eclss_timeseries` | PNG under `design_plots/`; **image understanding is never required** — the same features come back as numbers |
| `propose_capacity_candidate` | build a capacity set from theory + margin (no simulation) |
| `evaluate_design_constraints` | mass / volume / cost / bounds / budget labels |
| `run_design_candidate` | **re-simulate** the candidate (post-run design disabled inside it) |
| `compare_design_runs` | rank baseline and candidates by the objective and select the final one (no arguments — evidence completeness is read from the ledger, never from the model) |

## Constraint model (`rack_affine_linear_v1`)

`design_constraints:` in `scenario.yaml`. Explicitly an **exploration model, not flight hardware estimates**.

```text
capacity_ratio = candidate_capacity / baseline_capacity
subsystem_mass   = fixed + variable_at_baseline * capacity_ratio
subsystem_volume = fixed + variable_at_baseline * capacity_ratio
subsystem_cost   = fixed + variable_at_baseline * capacity_ratio      # hardware only
launch_cost      = total_mass_kg * launch_cost_musd_per_kg
total_cost       = hardware_cost + launch_cost
```

Baseline footprint: 1800 kg / 6.8 m³ / 259 MUSD (160 hardware + 99 launch). `launch_cost_musd_per_kg = 0.055` sits just below the 63.2–71.8 kUSD/kg range in the NASA OIG CRS audits and is an **exploration parameter**.

Checking happens in two stages (design doc §8.1):

- **Preflight** — broken schema, NaN/Inf/negative, or a variable outside the three → `invalid`, **never simulated**.
- **Constraint evaluation** — budget / bound violations only *label* the candidate (`over_budget`, `out_of_bounds`); it still runs, because “over-designed but everyone survives” is a useful lesson. The two labels are then treated differently at adoption: an `out_of_bounds` machine cannot be built, so it is never adopted (`require_in_bounds_final: true`); an `over_budget` one is money, so it *is* selected and comes back as `provisional_final` for a human (`require_feasible_final: false`, set it to `true` to make budgets a hard gate too).
- A candidate that names only some subsystems is priced as a whole station: the unnamed ones weigh what the **installed** machine weighs, not the sizing-model baseline. `capacity_source` in the evaluation says which is which.

## Objective: a clearance line, then the calmest machine, then the smallest

Survival is **not** a ranking key. A design that loses an occupant is not adoptable at
all, so no amount of saved mass can be traded against a life. Among the designs that
clear the line, less CRITICAL dwell wins before a lighter footprint: a heavy but
calm station beats a light one that lives in a dangerous band.

```python
final_eligible = (
    preflight_valid                     # schema / numeric / in-scope variables
    and simulated                       # re-simulated, not asserted
    and evidence_complete               # the review did its homework
    and crew_remaining == crew_initial  # the clearance line
    and constraint_status != "out_of_bounds"   # it can actually be built
)

rank_key = (
    not final_eligible,     # adoptable candidates first
    -crew_remaining,        # only orders the ineligible ones among themselves
    critical_step_count,    # among adoptable designs: less CRITICAL dwell first
    warning_step_count,
    total_mass_kg,          # then the smallest machine
    total_volume_m3,
    total_cost_musd,
)
```

Because the ranking *is* the objective, the model cannot override it: naming another
`candidate_id` in `final_proposal` is recorded in `parse_notes` and changes nothing.
The designer decides which candidates get built and simulated; which verified candidate
wins is arithmetic.

`design_constraints.objective` in `scenario.yaml` documents this objective and is
validated when the scenario loads — an unimplemented value fails the run before the
simulation starts, so config and behaviour cannot drift apart.

`design_penalty` (normalised mass / cost / volume) stays **descriptive**; it never decides adoption.

| Final status | Meaning |
| --- | --- |
| `approved_final` | full survival + Evidence Gate passed + in bounds + inside the budgets + rank 1 |
| `provisional_final` | the selected design, but it loses occupants or busts a budget — reported with `requires_supervisor_approval: true` |
| `rejected_final` | evidence missing, invalid, or no candidate was produced |

### Adoption is a separate act

`design_proposals.json` is written whatever the status, because the record is worth
keeping. Adopting it is gated: `--apply-proposals` **refuses** a document whose
`final_status` is not `approved_final`, or which carries
`requires_supervisor_approval`, and says why (library default). `ea run`
defaults to `--approve-provisional` so the simulation can auto-approve LLM
designs and close the loop without a human (it prints an INFO note). Pass
`--no-approve-provisional` to restore the supervisor gate. Being handed the
file is not approval; deciding to pay for an over-budget design is.

## Evidence Gate

A `final_proposal` is not accepted on the model’s say-so. Until all of the following exist, the proposal is **rejected, the missing items are handed back, and the loop continues**:

1. baseline artifacts read
2. time series inspected
3. theoretical capacity computed
4. a candidate produced
5. its constraint impact evaluated
6. the candidate re-simulated
7. baseline vs candidate compared

The check is deterministic (`DesignToolkit.missing_evidence()`). The prompt also carries an **Expert Context Pack**: the minimum domain facts, because 8B–32B models tend to answer straight from `summary.json`. It states premises, not a procedure — the order of work is the agent’s.

## Outputs

```text
<run_dir>/
  design_proposals.json      # capacity_profile change (design_family: capacity_sizing)
  design_review_report.json  # the whole review: evidence, candidates, selection
  candidate_rankings.json    # baseline + every candidate, ranked
  tool_trace.jsonl           # one line per turn, fully auditable
  design_plots/*.png
  candidate_runs/candidate_001/…   # each candidate is an isolated run
```

New root fields in `design_proposals.json`: `design_family`, `final_status`, `selected_candidate_id`, `requires_supervisor_approval`, `expected_outcome`, `constraint_evaluation`, `evidence`, `tool_trace_path`, `candidate_rankings_path`. The existing root fields are unchanged, so `--apply-proposals` still works.

## Configuration

`agents.yaml`:

```yaml
design:
  team:
    count: 1                      # one tool-use designer (design doc §4); debate is a future phase
  tool_use:
    enabled: true                 # false → classic summary-only designer
    max_tool_iterations: 24
    max_candidate_runs: 4
    candidate_actor_mode: inherit # actor mode inside candidate runs
    plots_enabled: true
```

| `design.mode` | `tool_use.enabled` | Behaviour |
| --- | --- | --- |
| `none` | — | designer disabled |
| `labeled_rule_base` | — | classic rule proposals |
| `llm` | `false` | classic post-run LLM proposal |
| `llm` | `true` | **tool-use designer** |

## Fallback

With no LLM client, three consecutive unparsable replies, or `max_tool_iterations` reached, a deterministic fallback performs the same evidence collection (theory → constraints → candidate run → comparison), so **a run always ends with a verified design**. `decision_source` records `tool_use_rule_fallback:<reason>`, so an LLM-reached design is never confused with a fallback.

## Running it

```powershell
ea run ssos_eclss_loop --backend plant_sim --steps 72 --actor-mode labeled_rule_base --design-mode llm
```

`design.mode = llm` talks to the lab vLLM in `agents.yaml` (`design.llm.base_url`) and needs the VPN. A turn costs tens of seconds to ~2 minutes (32B with thinking), so a review that uses its full 24-turn budget takes roughly 20–50 minutes. Each candidate re-simulation itself is about a second.

## Known consequence

For 50 occupants, the current budgets (4000 kg / 500 MUSD / 14 m³) **cannot** be met by a design that keeps everyone alive: ARS alone needs ~52 kg/day of removal, which is a ~3000 kg machine under `rack_affine_linear_v1`. Returning `provisional_final` with `requires_supervisor_approval: true` is therefore the correct behaviour (design doc §9, “report it as a reference solution”). Raising the budget or reducing the crew is a human decision; preflight forbids the agent from relaxing thresholds to make the problem go away.
