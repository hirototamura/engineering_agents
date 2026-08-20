"""Tests for the offline plant_sim ops cheatsheet."""

from __future__ import annotations

from dataclasses import replace

import pytest

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from environment.ssos.eclss.plant_sim.model import PlantModel
from tools.plant_sim_ops_cheatsheet import (
    CheatsheetRow,
    _policy_action_goals,
    ars_nameplate_kg,
    build_source_report,
    format_source_report_md,
    load_dynamics,
    metabolism_demand_per_step,
    ogs_nameplate,
    plot_cheatsheet,
    sweep,
    tank_effect,
    wrs_nameplate_l,
)

_ROW_DEFAULTS = dict(
    n=1,
    mode="none",
    steps=4,
    metabolism_steps=3,
    co2_metabolism_kg=0.1,
    co2_ops_kg=0.0,
    co2_net_kg=0.1,
    o2_metabolism_kg=0.05,
    o2_ops_kg=0.0,
    o2_net_kg=-0.05,
    water_metabolism_l=0.2,
    water_ops_l=0.0,
    water_net_l=-0.2,
    co2_demand_kg=0.1,
    o2_demand_kg=0.05,
    water_demand_l=0.2,
    ars_nameplate_kg=0.25,
    ogs_nameplate_o2_kg=0.12,
    ogs_nameplate_water_l=0.14,
    wrs_nameplate_l=1.96,
)


def test_metabolism_demand_scales_with_n():
    plant = PlantSimConfig()
    o2_1, co2_1, water_1 = metabolism_demand_per_step(1, plant)
    o2_4, co2_4, water_4 = metabolism_demand_per_step(4, plant)
    assert o2_4 == pytest.approx(4 * o2_1)
    assert co2_4 == pytest.approx(4 * co2_1)
    assert water_4 == pytest.approx(4 * water_1)


def test_nameplates_are_positive_machine_ratings():
    plant = PlantSimConfig()
    o2, water = ogs_nameplate(0.15, plant)
    assert ars_nameplate_kg(1.8, plant) > 0.0
    assert o2 > 0.0
    assert water > 0.0
    assert wrs_nameplate_l(2.0, plant) > 0.0
    # Doubling the goal scales ARS; crew count is not an input.
    assert ars_nameplate_kg(3.6, plant) == pytest.approx(2 * ars_nameplate_kg(1.8, plant))


def test_cheatsheet_demand_scales_and_ops_flat_vs_n():
    rows = sweep(n_max=3, steps=5)
    none_rows = {row.n: row for row in rows if row.mode == "none"}
    ars_rows = {row.n: row for row in rows if row.mode == "ars"}
    ogs_rows = {row.n: row for row in rows if row.mode == "ogs"}
    wrs_rows = {row.n: row for row in rows if row.mode == "wrs"}

    one = none_rows[1].per_step()
    three = none_rows[3].per_step()
    assert three.o2_demand_kg == pytest.approx(3 * one.o2_demand_kg, rel=1e-6)
    assert three.co2_demand_kg == pytest.approx(3 * one.co2_demand_kg, rel=1e-6)
    assert three.water_demand_l == pytest.approx(3 * one.water_demand_l, rel=1e-6)
    assert three.co2_ops_kg == 0.0
    assert three.o2_ops_kg == 0.0

    assert tank_effect(three, "o2", "metabolism") == pytest.approx(
        3 * tank_effect(one, "o2", "metabolism")
    )
    assert ars_rows[3].ars_nameplate_kg == pytest.approx(ars_rows[1].ars_nameplate_kg)
    assert ogs_rows[3].ogs_nameplate_o2_kg == pytest.approx(ogs_rows[1].ogs_nameplate_o2_kg)
    assert wrs_rows[3].wrs_nameplate_l == pytest.approx(wrs_rows[1].wrs_nameplate_l)
    assert tank_effect(ars_rows[3].per_step(), "co2", "ops") == pytest.approx(
        tank_effect(ars_rows[1].per_step(), "co2", "ops")
    )
    assert tank_effect(ogs_rows[3].per_step(), "o2", "ops") == pytest.approx(
        tank_effect(ogs_rows[1].per_step(), "o2", "ops")
    )
    assert tank_effect(wrs_rows[3].per_step(), "water", "ops") == pytest.approx(
        tank_effect(wrs_rows[1].per_step(), "water", "ops")
    )


def test_cheatsheet_ars_reduces_cabin_co2_vs_none():
    rows = sweep(n_max=2, steps=8)
    none_n2 = next(row for row in rows if row.n == 2 and row.mode == "none")
    ars_n2 = next(row for row in rows if row.n == 2 and row.mode == "ars")
    assert ars_n2.co2_ops_kg > 0.0
    assert ars_n2.co2_net_kg < none_n2.co2_net_kg


def test_cheatsheet_ogs_adds_o2_and_uses_water():
    rows = sweep(n_max=1, steps=8)
    none_row = next(row for row in rows if row.mode == "none")
    ogs_row = next(row for row in rows if row.mode == "ogs")
    assert ogs_row.o2_ops_kg > 0.0
    assert ogs_row.o2_net_kg > none_row.o2_net_kg
    assert ogs_row.water_ops_l > 0.0


def test_tank_effect_uses_inventory_sign():
    rows = sweep(n_max=1, steps=8)
    none_row = next(row for row in rows if row.mode == "none").per_step()
    ars_row = next(row for row in rows if row.mode == "ars").per_step()
    ogs_row = next(row for row in rows if row.mode == "ogs").per_step()
    wrs_row = next(row for row in rows if row.mode == "wrs").per_step()

    assert tank_effect(none_row, "co2", "metabolism") > 0.0
    assert tank_effect(none_row, "o2", "metabolism") < 0.0
    assert tank_effect(none_row, "water", "metabolism") < 0.0
    assert tank_effect(none_row, "co2", "ops") == pytest.approx(0.0, abs=1e-12)

    assert tank_effect(ars_row, "co2", "ops") < 0.0
    assert tank_effect(ogs_row, "o2", "ops") > 0.0
    assert tank_effect(ogs_row, "water", "ops") < 0.0
    assert tank_effect(wrs_row, "water", "ops") > 0.0


def test_cheatsheet_plot_writes_png(tmp_path):
    rows = [CheatsheetRow(**_ROW_DEFAULTS)]
    png = tmp_path / "ops_cheatsheet.png"
    plot_cheatsheet(rows, png)
    assert png.exists()
    assert png.stat().st_size > 0


def test_yaml_matches_plant_sim_dynamics():
    scenario, agents, plant, policy = load_dynamics()
    crew = scenario["plant_sim"]["crew"]
    sim = scenario["simulation"]
    time = scenario["plant_sim"]["time"]
    assert plant.o2_kg_day_person == pytest.approx(float(crew["o2_kg_day_person"]))
    assert plant.co2_kg_day_person == pytest.approx(float(crew["co2_kg_day_person"]))
    assert plant.potable_water_kg_day_person == pytest.approx(
        float(crew["potable_water_kg_day_person"])
    )
    assert plant.step_seconds == pytest.approx(float(time["step_seconds"]))
    assert plant.ars_capacity_kg_day == pytest.approx(
        float(scenario["plant_sim"]["ars"]["capacity_kg_day"])
    )
    assert plant.initial_o2_kg == pytest.approx(float(sim["initial_o2_storage_kg"]))
    assert plant.initial_cabin_co2_kg == pytest.approx(float(sim["initial_co2_storage_kg"]))
    assert plant.initial_product_water_l == pytest.approx(float(sim["initial_product_water_l"]))
    ars_goal, ogs_water, wrs_urine = _policy_action_goals(policy, plant)
    assert ars_goal == pytest.approx(float(agents["policy"]["ars_goal"]["initial_co2_mass"]))
    assert ogs_water == pytest.approx(float(agents["policy"]["ogs_goal"]["input_water_mass"]))
    assert wrs_urine == pytest.approx(float(agents["policy"]["wrs_goal"]["urine_volume"]))


def test_demand_and_nameplate_match_plant_model_probes():
    scenario, agents, plant, policy = load_dynamics()
    ars_goal, ogs_water, wrs_urine = _policy_action_goals(policy, plant)

    o2, co2, water = metabolism_demand_per_step(4, plant)
    model = PlantModel(
        replace(plant, crew_size=4, survival_enabled=False, initial_o2_kg=1.0e6, initial_product_water_l=1.0e6)
    )
    metab = model.advance_step()
    assert o2 == pytest.approx(metab["o2_demand_kg"])
    assert co2 == pytest.approx(metab["co2_generated_kg"])
    assert water == pytest.approx(metab["water_demand_kg"])

    dt = plant.step_seconds / 86400.0
    assert o2 == pytest.approx(4 * plant.activity_factor * plant.o2_kg_day_person * dt)
    assert ars_nameplate_kg(ars_goal, plant) == pytest.approx(
        plant.ars_capacity_kg_day
        * plant.ars_operation_seconds
        / 86400.0
        * (ars_goal / plant.ars_reference_goal_co2_kg)
    )
    ogs_o2, ogs_h2o = ogs_nameplate(ogs_water, plant)
    unconstrained = PlantModel(
        replace(plant, initial_product_water_l=1.0e6, survival_enabled=False)
    ).run_ogs(ogs_water)
    assert ogs_o2 == pytest.approx(unconstrained["o2_generated_kg"])
    assert ogs_h2o == pytest.approx(unconstrained["processed_water_kg"])
    assert wrs_nameplate_l(wrs_urine, plant) == pytest.approx(
        min(wrs_urine, plant.wrs_max_feed_l_per_operation) * plant.wrs_urine_recovery
    )


def test_source_report_quotes_yaml_and_matches_plot():
    scenario, agents, plant, policy = load_dynamics()
    rows = sweep(n_max=2, steps=5, scenario=scenario, agents=agents)
    report = build_source_report(
        scenario=scenario, agents=agents, plant=plant, policy=policy, rows=rows
    )
    text = format_source_report_md(report)
    assert "plant_sim.crew.o2_kg_day_person" in text
    assert "simulation.initial_o2_storage_kg" in text
    assert str(scenario["plant_sim"]["crew"]["o2_kg_day_person"]) in text
    n1 = report["crew_metabolism"]["by_n"]["1"]
    assert n1["o2_demand_kg"] == pytest.approx(n1["yaml_formula_o2"])
    ars = report["one_subsystem_action"]["ars"]
    assert ars["plant_model_run_ars_unconstrained_kg"] == pytest.approx(ars["yaml_formula_kg"])
    plotted = next(row for row in rows if row.n == 1 and row.mode == "none")
    assert plotted.o2_demand_kg == pytest.approx(n1["o2_demand_kg"])
    assert report["tank_inventory"]["initial_from_yaml"]["available_o2_kg"] == pytest.approx(
        float(scenario["simulation"]["initial_o2_storage_kg"])
    )
