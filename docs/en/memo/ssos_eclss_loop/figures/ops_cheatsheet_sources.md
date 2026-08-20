# plant_sim cheatsheet — YAML → Dynamics → plotted value

- Scenario YAML: `src/scenario/ssos_eclss_loop/scenario.yaml`
- Agents YAML: `src/scenario/ssos_eclss_loop/agents.yaml`
- Dynamics: `PlantSimConfig.from_scenario_config` + `PlantModel` (`environment.ssos.eclss.plant_sim`)

`mock_dynamics` in the same YAML is the LoopMock backend. This cheatsheet does not use it.

## 1. YAML loaded into PlantSimConfig

| YAML path | YAML value | Dynamics field | loaded |
| --- | ---: | --- | ---: |
| `plant_sim.time.step_seconds` | 1200 | `step_seconds` | 1200 |
| `plant_sim.time.ars_operation_seconds` | 4800 | `ars_operation_seconds` | 4800 |
| `plant_sim.time.ogs_operation_seconds` | 1200 | `ogs_operation_seconds` | 1200 |
| `plant_sim.crew.activity_factor` | 1.0 | `activity_factor` | 1.0 |
| `plant_sim.crew.o2_kg_day_person` | 0.84 | `o2_kg_day_person` | 0.84 |
| `plant_sim.crew.co2_kg_day_person` | 1.04 | `co2_kg_day_person` | 1.04 |
| `plant_sim.crew.potable_water_kg_day_person` | 2.28 | `potable_water_kg_day_person` | 2.28 |
| `plant_sim.ars.capacity_kg_day` | 4.5 | `ars_capacity_kg_day` | 4.5 |
| `plant_sim.ars.reference_goal_co2_kg` | 1.8 | `ars_reference_goal_co2_kg` | 1.8 |
| `plant_sim.ogs.max_o2_kg_day` | 9.25 | `ogs_max_o2_kg_day` | 9.25 |
| `plant_sim.wrs.urine_recovery` | 0.98 | `wrs_urine_recovery` | 0.98 |
| `plant_sim.wrs.max_feed_l_per_operation` | 10.0 | `wrs_max_feed_l_per_operation` | 10.0 |
| `simulation.initial_co2_storage_kg` | 1.3 | `initial_cabin_co2_kg` | 1.3 |
| `simulation.initial_o2_storage_kg` | 0.48 | `initial_o2_kg` | 0.48 |
| `simulation.initial_product_water_l` | 51.0 | `initial_product_water_l` | 51.0 |
| `src/scenario/ssos_eclss_loop/agents.yaml` `policy.ars_goal.initial_co2_mass` | 1.8 | ARS goal | 1.8 |
| `src/scenario/ssos_eclss_loop/agents.yaml` `policy.ogs_goal.input_water_mass` | 0.15 | OGS request | 0.15 |
| `src/scenario/ssos_eclss_loop/agents.yaml` `policy.wrs_goal.urine_volume` | 2.0 | WRS request | 2.0 |

## 2. Crew metabolism (left column)

Formula (same as `PlantModel.advance_step`): `N × activity_factor × rate_kg_day × step_seconds / 86400`

PlantModel probe N=1 (oversized tanks): O2 demand `0.011666666666666667`, CO2 generated `0.014444444444444444`, water demand `0.03166666666666666` kg.

| N | YAML formula O2 | PlantModel / plot O2 | YAML formula CO2 | plot CO2 | YAML formula water | plot water |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.0116667 | 0.0116667 | 0.0144444 | 0.0144444 | 0.0316667 | 0.0316667 |
| 2 | 0.0233333 | 0.0233333 | 0.0288889 | 0.0288889 | 0.0633333 | 0.0633333 |
| 3 | 0.035 | 0.035 | 0.0433333 | 0.0433333 | 0.095 | 0.095 |
| 4 | 0.0466667 | 0.0466667 | 0.0577778 | 0.0577778 | 0.126667 | 0.126667 |
| 5 | 0.0583333 | 0.0583333 | 0.0722222 | 0.0722222 | 0.158333 | 0.158333 |
| 6 | 0.07 | 0.07 | 0.0866667 | 0.0866667 | 0.19 | 0.19 |
| 7 | 0.0816667 | 0.0816667 | 0.101111 | 0.101111 | 0.221667 | 0.221667 |
| 8 | 0.0933333 | 0.0933333 | 0.115556 | 0.115556 | 0.253333 | 0.253333 |

## 3. One subsystem action (middle column)

Probes call `PlantModel.run_ars` / `run_ogs` / `run_wrs` with inventory large enough not to bind.

| Machine | YAML + formula | YAML numeric | PlantModel probe (plotted) |
| --- | --- | ---: | ---: |
| ARS CO2 removed | `capacity_kg_day × ars_operation_seconds / 86400 × (initial_co2_mass / reference_goal_co2_kg)` | 0.25 | 0.25 |
| OGS O2 produced | `min(input_water_mass, ogs_max_o2_kg_day × ogs_operation_seconds / 86400 × WATER_PER_O2)` | 0.128472 | 0.128472 |
| OGS water used | same min() as water mass | 0.144663 | 0.144663 |
| WRS water recovered | `min(urine_volume, max_feed_l_per_operation) × urine_recovery` | 1.96 | 1.96 |

WATER_PER_O2 (stoichiometry, not YAML) = `1.1260253765860366`.

## 4. Tank inventory (right column)

Right column is PlantModel (final − initial) / metabolism_steps with survival off and one action per step. O2 consumption saturates when available_o2_kg hits 0.

| YAML path | initial tank |
| --- | ---: |
| `simulation.initial_co2_storage_kg` | 1.3 kg cabin CO2 |
| `simulation.initial_o2_storage_kg` | 0.48 kg O2 |
| `simulation.initial_product_water_l` | 51.0 L water |

| N | mode | ΔCO2 / step | ΔO2 / step | Δwater / step | O2 consumed (tank-limited) | O2 demand |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | none | 0.0144444 | -0.0116667 | -0.0316667 | 0.0116667 | 0.0116667 |
| 1 | ars | -0.0371429 | -0.0116667 | -0.0316667 | 0.0116667 | 0.0116667 |
| 1 | ogs | 0.0144444 | 0.120476 | -0.180463 | 0.0116667 | 0.0116667 |
| 1 | wrs | 0.0144444 | -0.0116667 | -0.001875 | 0.0116667 | 0.0116667 |
| 4 | none | 0.0577778 | -0.0137143 | -0.126667 | 0.0137143 | 0.0466667 |
| 4 | ars | -0.0371429 | -0.0137143 | -0.126667 | 0.0137143 | 0.0466667 |
| 4 | ogs | 0.0577778 | 0.0854762 | -0.275463 | 0.0466667 | 0.0466667 |
| 4 | wrs | 0.0577778 | -0.0137143 | -0.0075 | 0.0137143 | 0.0466667 |
| 8 | none | 0.115556 | -0.0137143 | -0.253333 | 0.0137143 | 0.0933333 |
| 8 | ars | -0.0371429 | -0.0137143 | -0.253333 | 0.0137143 | 0.0933333 |
| 8 | ogs | 0.115556 | 0.0388095 | -0.40213 | 0.0933333 | 0.0933333 |
| 8 | wrs | 0.115556 | -0.0137143 | -0.015 | 0.0137143 | 0.0933333 |
