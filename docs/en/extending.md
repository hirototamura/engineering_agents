# Extending

Five things people actually want to change, and where each seam is. Every one of them is a file added or a config key edited — none of them requires touching the loop.

| I want to… | Touch | Do **not** touch |
| --- | --- | --- |
| Swap the plant for a different simulator | one new class satisfying `EclssBackend` | agents, tools, evaluation |
| Add a new scenario | one new directory under `src/scenario/` | the CLI, the runner |
| Change how agents decide | `agents.yaml` `mode:` | any Python |
| Change the world's rules | `scenario.yaml` | any Python |
| Give the designer a new variable to size | `design_variables.py` + `design_constraints.py` | the decision loop |

---

## 1. A new plant

`EclssBackend` (`src/environment/ssos/eclss/backend.py`) is a nine-method `Protocol` — poll telemetry, three action goals, four services, one failure switch. Three implementations ship, and they are radically different from each other, which is the evidence that the seam is real:

| Backend | What it is | Lines |
| --- | --- | --- |
| `mock` | arithmetic dynamics, no chemistry | `loop_mock_backend.py`, 160 lines |
| `plant_sim` | deterministic mass balance on BVAD metabolic rates | `plant_sim/`, four modules |
| `ros2` | a live Space Station OS instance in Docker over ROS 2 actions/services/topics | `ros2/bridge.py`, 362 lines |

Nothing above the backend knows which one is running. The agents issue `air_revitalisation`; whether that becomes an arithmetic subtraction, a stoichiometric ledger entry, or a ROS 2 action goal is decided in `build_eclss_backend` (`scenario_run.py:160`) and nowhere else.

To add a fourth:

```python
class MyBackend:                                  # Protocol — no base class to inherit
    def poll_telemetry(self) -> EclssTelemetrySnapshot: ...
    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult: ...
    # … six more
```

then one `if backend_kind == "mine":` branch. `--backend mine` works from that point on, including inside candidate re-simulations.

## 2. A new scenario

Scenarios are discovered from the filesystem, not registered (`runner.py` `list_scenarios`): any directory under `src/scenario/` containing a `scenario.yaml` is a scenario, and `ea scenarios` lists it. A scenario directory holds:

```
src/scenario/<name>/
  scenario.yaml     world rules, thresholds, physics constants, evaluation
  agents.yaml       team sizes, personas, LLM provider/model, policy
  scenario_run.py   the step loop
```

`Scenario` (`src/core/scenario.py`) is a five-method ABC: `name`, `load_config`, `build_simulator`, `build_team`, `run`. `scrubber_degradation` and `ssos_eclss_loop` share no code below the CLI — the second was added without editing the first.

## 3. Different agents

`mode:` in `agents.yaml`, per side, no code:

| Mode | Behaviour | Use for |
| --- | --- | --- |
| `none` | no agents; the plant runs open-loop | isolating physics from policy |
| `labeled_rule_base` | deterministic threshold policy | reproducible regression, and a cheap crew inside candidate re-simulations |
| `llm` | Ollama or vLLM | the actual experiment |

The operator side and the designer side are independent. The shipped default runs **labeled operators with an LLM designer**: the crew is deterministic so the design loop's measurements are attributable to the design, not to a different crew improvising. Set both to `llm` and you get an LLM crew under an LLM designer; the config supports it and `candidate_actor_mode` exists precisely for that case (score candidates with the cheap crew while the baseline keeps the expensive one).

Personas are archetype lenses (`persona.py:30`) — *ways of thinking*, deliberately free of scenario names, thresholds and action catalogues, so the same roster transfers to a scenario it has never seen.

## 4. Different world rules

`scenario.yaml` is the world, and it is annotated line by line with units and provenance. Every one of these is a live knob:

```yaml
plant_sim:
  crew:
    size: 50                        # occupants
    co2_kg_day_person: 1.04         # BVAD
    activity_factor: 1.0            # 1 nominal, 4 exercise, 0.7 sleep
  time:
    step_seconds: 1200              # how long a decision is worth
    ars_operation_seconds: 4800     # how long a machine is unavailable after you use it
thresholds:
  co2_storage_high_kg: 2.0          # where "warning" starts
design_constraints:
  budgets: {max_total_mass_kg: 4000.0, max_total_cost_musd: 500.0}
  subsystem_bounds:
    ars: {min_capacity_kg_day: 4.5, max_capacity_kg_day: 80.0}
inject_failures: false              # timed ARS/OGS/WRS outages
iteration:
  count: 50                         # rounds in a chain
  exploration: {stagnation_window: 4, min_score_delta: 0.25}
```

Each changes the *character* of the problem rather than its parameters. Raise `activity_factor` to 4 and the crew is exercising: demand quadruples and a design that was comfortable stops being one. Drop `step_seconds` and agents decide more often but each decision is worth less. Raise `ars_operation_seconds` and committing the machine becomes the real decision. Set `crew.size` to 4 and the whole problem inverts — the shipped baseline becomes survivable and the design question turns from "how much bigger" into "how much smaller".

Anything here can also be overridden per run without editing the file:

```bash
ea run ssos_eclss_loop --set plant_sim.crew.size=120 --set plant_sim.crew.activity_factor=4.0
```

## 5. A new design variable

Today the designer sizes three things, and the restriction is deliberate — `design_variables.py`'s docstring: *"Recovery efficiencies, Sabatier conversion, crew metabolism and health thresholds are explicitly NOT design variables — they are material / safety / policy choices that would blur the sizing problem."*

To add a fourth, e.g. cabin volume:

1. `design_variables.py` — one `CapacityVariable` entry: key, subsystem, dotted config path, unit, description.
2. `design_constraints.py` / `scenario.yaml` `sizing_model` — its mass, volume and cost coefficients, and its engineering bounds.
3. If a bigger machine needs a bigger operating payload to be usable, extend `sync_action_payloads` (the OGS/WRS precedent: raising nameplate capacity alone does nothing if the actor keeps requesting the old batch size).

The decision loop, the tools, the physics gate and the evaluation all read `CAPACITY_KEYS` and need no change. The contract shown to the model is generated from it (`DECISION_CONTRACT` interpolates `list(CAPACITY_KEYS)`), so the model is told about the new variable automatically.

---

## What is deliberately hard to change

Honest counterweight to the table above.

- **The scorecard's axes** are wired into `evaluation.py`, not configured. Weights and anchor lines are config; adding an eighth axis is a code change, and it should be — the integrity guard exists to notice when the bar moves, so moving it must be visible.
- **The three-tier memory shape** (private / discourse / chain) is structural. Sizes are config, tiers are not.
- **`scenario.yaml`'s objective is validated on load**: `primary: require_full_survival` is checked against the objective `design_eval` actually implements, and any other value is rejected. Config cannot drift away from behaviour by being edited.

---

## See also

- [Architecture](architecture.md) — the layer diagram in full
- [API contracts](api-contracts.md) — the JSONL schemas every layer writes
- [Agent design](agent-design.md) — where agent autonomy begins and ends
- [Roadmap](roadmap.md) — what is planned next, and what has been measured as needed
