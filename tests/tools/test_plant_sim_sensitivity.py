"""Tests for plant_sim cheatsheet sensitivity (non-UI core)."""

from __future__ import annotations

import pytest

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from tools.plant_sim_ops_cheatsheet import load_ssos_yaml, tank_effect
from tools.plant_sim_sensitivity import (
    apply_sensitivity_overrides,
    close_crew_water,
    run_sensitivity,
    sensitivity_figure,
    yaml_defaults,
)


def test_yaml_defaults_match_scenario_file():
    scenario, _agents = load_ssos_yaml()
    defaults = yaml_defaults()
    assert defaults["simulation.initial_o2_storage_kg"] == pytest.approx(
        float(scenario["simulation"]["initial_o2_storage_kg"])
    )
    assert defaults["plant_sim.crew.o2_kg_day_person"] == pytest.approx(
        float(scenario["plant_sim"]["crew"]["o2_kg_day_person"])
    )
    assert int(defaults["plant_sim.crew.size"]) == int(scenario["plant_sim"]["crew"]["size"])


def test_overrides_do_not_mutate_source_yaml_dict():
    scenario, _agents = load_ssos_yaml()
    original = float(scenario["plant_sim"]["crew"]["o2_kg_day_person"])
    patched = apply_sensitivity_overrides(scenario, {"plant_sim.crew.o2_kg_day_person": original * 2})
    assert scenario["plant_sim"]["crew"]["o2_kg_day_person"] == pytest.approx(original)
    assert patched["plant_sim"]["crew"]["o2_kg_day_person"] == pytest.approx(original * 2)
    assert patched["plant_sim"]["survival"]["enabled"] is False


def test_crew_water_closes_to_potable():
    crew = {
        "potable_water_kg_day_person": 4.0,
        "urine_kg_day_person": 1.50,
        "condensate_kg_day_person": 0.75,
        "unrecoverable_water_kg_day_person": 0.03,
    }
    close_crew_water(crew)
    assert crew["urine_kg_day_person"] + crew["condensate_kg_day_person"] + crew[
        "unrecoverable_water_kg_day_person"
    ] == pytest.approx(4.0)


def test_o2_rate_override_scales_metabolism_column():
    base_rows, _ = run_sensitivity({}, n_max=2, steps=4)
    hot_rows, patched = run_sensitivity(
        {"plant_sim.crew.o2_kg_day_person": 1.68},
        n_max=2,
        steps=4,
    )
    PlantSimConfig.from_scenario_config(patched)
    base = next(row for row in base_rows if row.n == 2 and row.mode == "none").per_step()
    hot = next(row for row in hot_rows if row.n == 2 and row.mode == "none").per_step()
    assert hot.o2_demand_kg == pytest.approx(2 * base.o2_demand_kg, rel=1e-6)
    assert tank_effect(hot, "o2", "metabolism") == pytest.approx(
        2 * tank_effect(base, "o2", "metabolism")
    )


def test_ars_capacity_override_scales_nameplate():
    base_rows, _ = run_sensitivity({}, n_max=1, steps=4)
    fat_rows, _ = run_sensitivity({"plant_sim.ars.capacity_kg_day": 9.0}, n_max=1, steps=4)
    base = next(row for row in base_rows if row.mode == "ars")
    fat = next(row for row in fat_rows if row.mode == "ars")
    assert fat.ars_nameplate_kg == pytest.approx(2 * base.ars_nameplate_kg, rel=1e-6)


def test_larger_initial_o2_reduces_tank_starvation():
    starved, _ = run_sensitivity(
        {"simulation.initial_o2_storage_kg": 0.05},
        n_max=4,
        steps=8,
    )
    rich, _ = run_sensitivity(
        {"simulation.initial_o2_storage_kg": 5.0},
        n_max=4,
        steps=8,
    )
    starved_row = next(row for row in starved if row.n == 4 and row.mode == "none").per_step()
    rich_row = next(row for row in rich if row.n == 4 and row.mode == "none").per_step()
    assert starved_row.o2_metabolism_kg < rich_row.o2_demand_kg - 1e-6
    assert rich_row.o2_metabolism_kg == pytest.approx(rich_row.o2_demand_kg, rel=1e-5)


def test_sensitivity_figure_is_3x4():
    rows, _ = run_sensitivity({}, n_max=2, steps=4)
    fig = sensitivity_figure(rows, baseline_rows=rows, yaml_n=4)
    assert fig.axes
    assert len(fig.get_axes()) >= 12
    import matplotlib.pyplot as plt

    plt.close(fig)
