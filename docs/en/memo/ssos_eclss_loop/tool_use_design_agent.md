# Design agent — sizing ARS / OGS / WRS throughput

> **Scope**: the **post-run designer only** in `ssos_eclss_loop`. Runtime operations (the actor) are in [labeled_rule_base.md](labeled_rule_base.md).
> The older summary-reading designer stays as it was: [post_run_design_agent.md](post_run_design_agent.md).
> **Origin**: the design note "Tool-use-centred redesign of the SSOS ECLSS design agent" (2026-08-28) and the improvement spec (2026-08-29).

## Why it was rebuilt

### First time: it stopped reading only the summary

The original designer wrote `design_proposals.json` from the post-run `summary` and a little state. None of what a human expert does was present — fetching what you need, reading the time series, computing the theoretical demand, verifying a candidate by re-simulating it — and `set_parameter` could not change plant_sim's **throughput** at all.

### Second time: the model stopped choosing the procedure

The first rebuild handed the model a tool catalog and let it pick the next tool every turn. Measured on a real run:

- twenty-one turns, one candidate
- `evaluate_design_constraints` called seven times, twice in runs of three
- both designs that kept the whole crew alive came from the deterministic fallback, after the model stopped replying
- past tool results were replayed into every prompt, so what it did on turn six was forgotten by turn fifteen

The cause was asking one model to decide both *what to design* and *how to run the review*. The split is now:

```text
LLM     = design judgement only
Python  = investigation, verification, simulation, evaluation, comparison, workflow
```

## The three design variables

| Variable | Meaning | Unit |
| --- | --- | --- |
| `plant_sim.ars.capacity_kg_day` | ARS CO₂ removal capacity | kg/day |
| `plant_sim.ogs.max_o2_kg_day` | OGS O₂ generation capacity | kg/day |
| `plant_sim.wrs.max_feed_l_per_operation` | WRS batch size per operation | L/operation |

**Not design variables**: recovery efficiencies (`ars.capture_efficiency`, `wrs.urine_recovery`, `wrs.grey_recovery`), Sabatier conversion, crew metabolism, health thresholds. Those are questions of materials, catalysts, safety standards and operating policy; mixing them into "sizing hardware that costs mass, volume and money" blurs the design problem.

Implemented in `src/scenario/ssos_eclss_loop/design_variables.py`. A `capacity_profile` proposal naming anything else is **rejected**.

### Operating payloads are re-synced (important)

A larger OGS does nothing while `ogs_goal.input_water_mass` stays small: the request throttles it. WRS behaves the same way through `wrs_goal.urine_volume`. Applying a `capacity_profile` therefore raises the operating payloads with it.

```text
ogs_goal.input_water_mass >= ogs.max_o2_kg_day * ogs_operation_seconds / 86400 * WATER_PER_O2
wrs_goal.urine_volume     >= urine produced per step (clamped to the batch cap)
```

The sync only raises. A payload set high by hand is never shrunk. `payload.sync_action_payloads: false` disables it.

## One command per subsystem per step, and the busy guard

Two operating constraints exist so the sizing problem is real (design note §7).

1. **One command per subsystem per step.** ARS, OGS and WRS may each be commanded once in the same step; ARS twice may not. Extras become `/eclss/events/operational_rejected` with `reason=duplicate_command_this_step`. Enforced in `SsosEclssLoopTeam.apply_outcome()`, independent of mode.
2. **Operation duration / busy guard.** With `ars_operation_seconds = 4800` and `step_seconds = 1200`, one accepted ARS command occupies it for `ceil(4800/1200) = 4` steps; commands arriving meanwhile are refused with `reason=subsystem_busy`. OGS and WRS take one step. An operation that processed nothing does not occupy anything (WRS `no_feed`, OGS `no_water`). Implemented in `PlantSimEclssBackend`; revert with `plant_sim.operations.busy_guard_enabled: false`.

The consequence is that ARS delivers `capacity_kg_day × goal_scale` at most eighteen times a day, nowhere near the `52 kg/day` fifty people produce — and now that shortfall **shows up in the run**.

## The design decision loop

Implemented in `src/scenario/agents/ssos_tool_use_design.py`.

```text
deterministic evidence gathering (always, every run)
   artifacts -> time series -> features -> theoretical capacity -> plots
        |
        v
   +--> assemble the DesignState
   |        |
   |        v
   |   ask the model once
   |        |
   |        +-- propose_candidate -> candidate pipeline (below) --+
   |        |                                                     |
   |        +-- finish -> done                                    |
   |                                                              |
   +--------------------------------------------------------------+
        |
        v
   deterministic final ranking
```

The model returns one of exactly two JSON objects.

```json
{"decision": "propose_candidate",
 "rationale": "ARS and OGS are both short, so raise both",
 "fields": {"plant_sim.ars.capacity_kg_day": 23.92,
            "plant_sim.ogs.max_o2_kg_day": 48.3}}
```

```json
{"decision": "finish",
 "rationale": "candidate_002 keeps everyone alive and is the smallest that does",
 "selected_candidate_id": "candidate_002"}
```

**Tool names, the next step, and self-reported evidence completeness are all gone from the model's output.**

## DesignState — current state, not history

Implemented in `src/scenario/ssos_eclss_loop/design_state.py`. Rebuilt in Python before every decision; it is the only thing the model is given.

```json
{
  "baseline": {"crew_initial": 50, "crew_remaining": 0,
               "critical_step_count": 4, "physics_gate": "passed",
               "bottlenecks": ["ogs", "ars"]},
  "installed_capacity": {"plant_sim.ars.capacity_kg_day": 4.5},
  "theoretical_capacity": {"ars": {"required_kg_day": 52.0,
                                   "effective_capacity_kg_day": 4.5,
                                   "coverage_ratio": 0.0865}},
  "candidates": [{"candidate_id": "candidate_001", "crew_remaining": 50,
                  "critical_step_count": 0, "mass_kg": 4689.9,
                  "constraint_status": "over_budget", "physics_gate": "passed"}],
  "current_best": "candidate_001",
  "decisions_left": 3,
  "remaining_candidate_budget": 3,
  "decision_needed": "refine_or_finish"
}
```

No transcript of earlier turns. **There is no past to re-read, so there is nothing to forget.** Measured prompt length went 4,333 characters on the first decision to 5,334 on the third: it does not grow with the turn count.

Each run keeps its last state as `design_decision_state.json` — named apart from the per-step `design_state.jsonl` the run already writes.

## The candidate pipeline runs itself

The moment the model returns `fields`, the code runs all of this, in this order.

```text
design variable validation -> constraints -> integrity guard -> re-simulation
                           -> physics gate -> evaluation -> comparison -> state update
```

The model can neither call the constraint check nor forget to: it is not offered the choice.

**The same machine is simulated once.** Fields are normalised (known keys only, sorted, rounded to six decimals) and hashed with SHA-256. Two proposals naming the same machine are one candidate; the second **costs a decision** — one was spent — but not a second simulation.

## Decision budget

```yaml
tool_use:
  enabled: true
  max_candidate_runs: 4
  decision_loop:
    max_decisions: 5      # four candidates plus one decision to stop
    max_parse_retries: 1
```

`max_tool_iterations: 24` is **gone**. It counted tool calls, so a model re-checking the same constraint could spend twenty turns without the design moving.

## When the reply cannot be read

```text
empty response / malformed JSON
    -> one short repair prompt
    -> still unreadable: deterministic fallback
```

**The fallback keeps every candidate already verified.** Throwing away verified work because a link dropped would be wrong, so it continues from `current_best` and the remaining budget. Evidence was gathered before the first decision, so it is not gathered again. With budget left it sizes candidates from theoretical demand at margins 1.15, 1.0 and 1.35.

`decision_source` carries `tool_use_rule_fallback:<reason>`, so a fallback design is never mistaken for one the model reached.

## Scoring Integrity Guard — did the run move its own bar?

Implemented in `src/scenario/ssos_eclss_loop/integrity_guard.py` (spec §11).

Loosening the scoring bar is cheaper than designing anything: raise the thresholds, start with a full oxygen tank, carry fewer people. The physics would be unchanged and the score would improve. So **before the first step**, the config the run actually uses is compared against the pristine scenario on disk.

| Class | Contents | Treatment |
| --- | --- | --- |
| `scoring_bar` | thresholds, survival rules, crew size, opening inventories, evaluation settings, adoption budgets | **`invalid` as evaluation or design evidence** |
| `operating_point` | ARS / OGS / WRS capacity, backend | recorded (it is the point of the design loop) |
| `arm` | agent operating policy | recorded |
| `other` | anything else | recorded, so nothing vanishes by not fitting a class |

Differences are found by **walking subtrees** (spec §11.4). A list of field names silently misses the neighbour added next to it, and the neighbour of a threshold is usually another threshold.

**Two deliberate deviations, both guarding more than the spec lists.**

- §11.1 names only `simulation.initial_o2_storage_kg`; the CO₂ and water opening inventories beside it are the same kind of quantity — how hard the run starts out — so they are guarded too
- the `evaluation` block and the `design_constraints` budgets are guarded: a design that cannot fit the budget must not be able to widen it

The full classification lands in `run_integrity.json`; the summary is embedded in `evaluation.json` under `integrity`.

## Telemetry-only physics gate

Implemented in `src/scenario/ssos_eclss_loop/physics_gate.py` (spec §12).

Nine checks that read `telemetry.jsonl` **and nothing else** — no scenario config, no agent config, no action log. A run that can only be judged by consulting the settings that produced it is not independently audited, and a design agent free to change those settings would keep a way to move the bar.

```text
simulator -> telemetry -> physics gate     (never the other way)
```

| # | Check | What it asks |
| --- | --- | --- |
| 1 | `readings_present_and_finite` | are the required readings there and finite |
| 2 | `inventories_non_negative` | did any inventory go negative |
| 3 | `totals_monotonic` | did a cumulative total run backwards |
| 4 | `carbon_ledger` | does carbon close |
| 5 | `oxygen_ledger` | does oxygen close |
| 6 | `water_ledger` | does water close |
| 7 | `stoichiometric_residual` | do electrolysis and Sabatier obey their ratios |
| 8 | `failure_quiescence` | did a failed subsystem process work |
| 9 | `capacity_bounds` | did a subsystem exceed its installed capacity |

**Each ledger's opening inventory comes from the run's own first telemetry row**, not from the scenario's declared initial conditions. That is what makes it config-free. On a 30-step run all three ledgers close to rounding error, around 10⁻¹⁴.

The verdict has three values. **A check that could not be measured reports `skipped`, and `skipped` is not a pass.**

```text
failed      any check failed
incomplete  none failed, some skipped
passed      every check passed
```

Only `passed` may be adopted. Runs recorded before the audit fields existed read as `incomplete`.

### Telemetry additions

To keep the gate config-free, what it checks against travels with the measurement (spec §13). Cumulative totals, busy steps and crew counts were already there; three things were added.

- `installed_capacity` — the capacity and cadence snapshot
- `failure_state` — per-subsystem failure flags
- `operations_this_step` — what each subsystem actually processed during the step

`operations_this_step` is cleared at the **step boundary**, not on poll. A step is polled more than once, so clearing on the first poll dropped the operations before the post-ops row was written (found by measurement while implementing). Rejected commands record nothing, so an audit cannot credit an operation the hardware never performed.

## Constraint model (`rack_affine_linear_v1`)

`design_constraints:` in `scenario.yaml`, explicitly **an exploratory first model, not a hardware estimate**.

```text
capacity_ratio = candidate_capacity / baseline_capacity
subsystem_mass   = fixed + variable_at_baseline * capacity_ratio
subsystem_volume = fixed + variable_at_baseline * capacity_ratio
subsystem_cost   = fixed + variable_at_baseline * capacity_ratio      # hardware only
launch_cost      = total_mass_kg * launch_cost_musd_per_kg
total_cost       = hardware_cost + launch_cost
```

The baseline footprint is 1800 kg / 6.8 m³ / 259 MUSD (160 hardware + 99 launch). `launch_cost_musd_per_kg = 0.055` sits a little under the NASA OIG CRS audit range (63.2–71.8 kUSD/kg) and is **for exploration**.

Constraints are checked in two stages (design note §8.1).

- **Preflight**: broken schema, NaN/Inf/negative, anything outside the design variables → `invalid`, and **it is not simulated**.
- **Constraint evaluation**: budget and bounds overruns do not stop a candidate; they are **labelled** `over_budget` or `out_of_bounds`. "Over-designed but survivable" is worth learning. They differ at adoption: `out_of_bounds` cannot be built, so it is never adopted (`require_in_bounds_final: true`); `over_budget` is a money question, so it is adoptable and reported as `provisional_final` (`require_feasible_final: false`).
- A partial candidate is still priced as a whole station. Subsystems it did not name are priced at **currently installed** capacity, and `capacity_source` records which was used.

## Ranking: clear the bar, then calm, then small

Survival is not a ranking key but a **clearance condition**. A design that loses one occupant cannot be adopted, so saved mass never sits opposite a human life.

```python
final_eligible = (
    preflight_valid                     # schema, numbers, design-variable scope
    and simulated                       # re-simulated, not asserted
    and evidence_complete
    and crew_remaining == crew_initial  # the clearance line
    and constraint_status != "out_of_bounds"   # it can actually be built
)

rank_key = (
    not final_eligible,     # adoptable candidates first
    -crew_remaining,        # only orders the ineligible among themselves
    critical_step_count,    # among eligible: less CRITICAL dwell wins
    warning_step_count,
    total_mass_kg,          # then the smallest machine
    total_volume_m3,
    total_cost_musd,
)
```

The ranking is the objective, so **the model cannot overrule it**. Naming a different `candidate_id` in `finish` is recorded in `parse_notes` and changes nothing. Which candidates get built is the designer's judgement; which verified candidate wins is arithmetic.

`design_penalty` is descriptive. **The evaluation score out of 100 is not used for ranking either.**

### Recording what decided the order

The objective is lexicographic, so the first criterion where two candidates differ settles it and everything below is never consulted. Measured:

```json
{"decided_by": "warning_step_count",
 "winner": "candidate_001", "winner_value": 65,
 "runner_up": "candidate_002", "runner_up_value": 69,
 "not_compared": ["total_mass_kg", "total_volume_m3", "total_cost_musd"]}
```

Four fewer warning steps bought a machine **494 kg heavier and 75 MUSD dearer, and its mass was never compared at all**. The objective is unchanged, but that is a trade a person should see, so it is recorded in `candidate_rankings.json` under `selection.rank_rationale`.

### Final status

| status | meaning |
| --- | --- |
| `approved_final` | everyone alive, evidence complete, in bounds, within budget, ranked first |
| `provisional_final` | selected, but either not everyone survived or a budget is exceeded; reported with `requires_supervisor_approval: true` |
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

## One evaluation per run

A run used to be evaluated twice. The unified evaluation wrote `evaluation.json` before the design pass, and afterwards the evaluator ran again on the raw config and **overwrote** it, so the numbers the designer reasoned from were not the numbers a human opened. On the 72-step baseline: `actor_decision` 10.000 against 6.744, `physical_response` 3.469 against 9.945, total 23.17 against 26.39.

It is now written once. `summary.evaluation_score`, `summary.evaluation_compact.score` and `evaluation.json`'s `scores.total` always agree.

## Artifacts

```text
<run_dir>/
  summary.json
  scenario_config.yaml / agents_config.yaml

  run_integrity.json           # every config difference, classified
  physics_gate.json            # nine telemetry-only checks

  evaluation.json              # embeds the integrity and physics summaries
  evaluation.html

  design_decision_state.json   # the last DesignState
  design_proposals.json        # the capacity_profile proposal
  design_review_report.json    # the whole review
  candidate_rankings.json      # baseline, all candidates, and what decided the order
  tool_trace.jsonl             # human audit log, not model input
  design_plots/*.png
  candidate_runs/candidate_001/…   # one independent run per candidate, same artifacts
```

`tool_trace.jsonl` is no longer the designer's memory — the DesignState is. It stays as the record a person reads afterwards.

## Configuration

```yaml
design:
  team:
    count: 1                      # a single engineer; multi-designer debate is a future phase
  tool_use:
    enabled: true                 # false returns to the summary-reading designer
    max_candidate_runs: 4
    decision_loop:
      max_decisions: 5
      max_parse_retries: 1
    candidate_actor_mode: inherit # actor mode inside candidate runs
    plots_enabled: true
```

| `design.mode` | `tool_use.enabled` | Behaviour |
| --- | --- | --- |
| `none` | — | designer off |
| `labeled_rule_base` | — | rule proposal |
| `llm` | `false` | classic post-run LLM proposal |
| `llm` | `true` | **design decision loop** |

## Running it

```powershell
ea run ssos_eclss_loop --backend plant_sim --steps 72 --actor-mode labeled_rule_base --design-mode llm
```

`design.mode = llm` connects to the lab vLLM at `design.llm.base_url` in `agents.yaml`, which needs the VPN. **The CLI probes the endpoint before starting and stops with `ENVIRONMENT_ERROR` if it is unreachable** — the deterministic fallback is not reachable from the CLI that way.

A decision takes tens of seconds to two minutes (27B with thinking). With at most five decisions a review runs around five minutes; a candidate re-simulation itself takes about a second.

## Known consequence

At fifty occupants, under the current budgets (4000 kg / 500 MUSD / 14 m³), **no design that supports everyone fits**. ARS alone must remove 52 kg/day, which `rack_affine_linear_v1` prices at roughly 3000 kg. So `provisional_final` with `requires_supervisor_approval: true` is the correct answer, reported for a human to weigh (design note §9). Raising the budget or reducing the crew is a human decision; both preflight and the Integrity Guard block the agent from loosening a threshold instead.

**The conclusion reproduces; the path and the exact capacities do not.** Any evaluation use needs repeated runs and a look at the median and the worst case.
