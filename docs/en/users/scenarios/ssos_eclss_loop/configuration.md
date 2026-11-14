# Configure the ECLSS loop

The bundled inputs are `src/scenario/ssos_eclss_loop/scenario.yaml` and `agents.yaml`. [Common configuration](../../reference/configuration.md) explains merge rules and output replacement.

## Defaults that affect execution

A bare `run ssos_eclss_loop` selects `plant_sim`, labeled runtime actors, LLM post-run design, and an enabled 50-round chain with paired replay. It is not a small offline test. For one local run, specify the backend and both modes and add `--set iteration.enabled=false`.

Actor and design modes are `none`, `labeled_rule_base`, or `llm`. `--agents-mode` is an alias for actor mode; do not combine it with `--actor-mode`. If an actor mode is explicitly selected and design mode is omitted, design inherits actor mode. Set both for repeatable procedures. LLM provider/model flags affect only LLM sides. The shipped actor/designer configurations target separate lab vLLM endpoints; see [LLM setup](../../guides/llm.md).

## System and backend

Default observation length is 50 steps. Initial inventories are CO₂ 1.3 kg, O₂ 8 kg, and potable water 80 L. Storage mass is in kilograms; the ROS2 bridge converts SSOS gram values. Water volumes are liters.

`mock` uses the configured `mock_dynamics`; `plant_sim` and `ros2` ignore that block. `plant_sim` advances 1200 s per observation, with 50 crew. When actors are active, `plant_sim.crew.size` must match `agents.actor.team.count`. The actor command cap is 6 per step. ARS is occupied for 4 steps by default (4800/1200 s); commands during busy time are rejected. Subsystem fault injection is off by default; `--inject-failures` enables the configured ARS/OGS/WRS schedule.

`ros2` needs SSOS Docker/ROS2 and configured mounts. Default action/topic/startup waits are 120/15/45 s. Automatic chains support `mock` and `plant_sim`, not `ros2`.

## Design variables and constraints

Capacity sizing may change exactly `plant_sim.ars.capacity_kg_day` (4.5 kg/day initially), `plant_sim.ogs.max_o2_kg_day` (9.25 kg/day), and `plant_sim.wrs.max_feed_l_per_operation` (10 L/operation). OGS/WRS action requests are synchronized upward so added capacity can be used. Recovery efficiency, crew metabolism, chemistry, and verification thresholds are not capacity design variables.

The objective requires full survival before maximizing evaluation score. Bounds and soft budgets are in `design_constraints`: 4000 kg installed mass, 500 MUSD total cost, and 14 m³ volume. Over-budget candidates may be simulated and a winner may need supervisor approval. Out-of-bounds candidates are not automatically final-eligible, but can be returned as provisional choices. Manual approval is not a hard bounds guard; read the [adoption limitations](../../guides/design-iterations.md). The affine rack sizing model and cost coefficients are exploration assumptions, not flight-hardware estimates.

Health bands and evaluation semantics are owned by [results](results.md). Iteration controls and provisional adoption are explained in [design iterations](../../guides/design-iterations.md).

## Read hardware sizing separately from an action request

| Item | Example field | Meaning |
| --- | --- | --- |
| Installed capacity | `plant_sim.ogs.max_o2_kg_day` | Nameplate throughput of the modeled machine |
| Operating request | `agents.actor.policy.ogs_goal.input_water_mass` | Water requested in one operation |
| Observation clock | `plant_sim.time.step_seconds` | Time advanced between observations |
| Operation duration | `plant_sim.time.ars_operation_seconds` | How long an accepted subsystem operation occupies it |
| Verification bar | `thresholds.*`, `evaluation.*` | Conditions used to judge the result |

A higher operating request does not create capacity, and a higher nameplate does not help if requests never use it. Capacity application synchronizes relevant action requests, while evaluation requirements remain separate.

The rack sizing model makes those changes costly:

```text
subsystem_quantity = fixed + variable_at_baseline × (capacity / baseline_capacity)
total_cost_musd = hardware_cost_musd + launch_cost_musd_per_kg × total_mass_kg
```

Mass, volume, and hardware cost each have their own coefficients. Raising capacity can improve resource behavior while worsening footprint and budget labels; this is why the [result](results.md) includes both survival and resource/footprint axes.
