"""Unit tests for the design-space coordinates and coverage ratios."""

from __future__ import annotations

import math

import pytest

from tools.analysis import design_space as ds

CONFIG = {
    "plant_sim": {
        "time": {"step_seconds": 1200, "wrs_operation_seconds": 1200},
        "crew": {
            "size": 50,
            "activity_factor": 1.0,
            "co2_kg_day_person": 1.04,
            "o2_kg_day_person": 0.84,
            "potable_water_kg_day_person": 2.28,
            "urine_kg_day_person": 1.5,
            "condensate_kg_day_person": 0.75,
        },
        "ars": {"capacity_kg_day": 4.5},
        "ogs": {"max_o2_kg_day": 9.25},
        "wrs": {"max_feed_l_per_operation": 10.0},
    },
    "thresholds": {
        "co2_storage_high_kg": 2.0,
        "o2_storage_low_kg": 6.0,
        "product_water_low_l": 50.0,
    },
}


# --------------------------------------------------------------------------- #
# crew demand
# --------------------------------------------------------------------------- #
def test_crew_demand_scales_linearly_with_crew_size():
    demand = ds.crew_demand(CONFIG)
    assert demand.crew_size == 50
    assert demand.co2_kg_day == pytest.approx(52.0)
    assert demand.o2_kg_day == pytest.approx(42.0)
    assert demand.waste_water_l_day == pytest.approx(112.5)


def test_crew_demand_honours_the_activity_factor():
    config = {"plant_sim": {"crew": dict(CONFIG["plant_sim"]["crew"], activity_factor=2.0)}}
    assert ds.crew_demand(config).co2_kg_day == pytest.approx(104.0)


def test_crew_demand_falls_back_to_defaults_for_an_empty_config():
    demand = ds.crew_demand({})
    assert demand.crew_size == 50
    assert demand.co2_kg_day > 0


# --------------------------------------------------------------------------- #
# coverage ratios
# --------------------------------------------------------------------------- #
def test_shipped_station_is_undersized_on_both_gas_loops():
    coverage = ds.coverage_ratios(CONFIG)
    assert coverage.ars == pytest.approx(4.5 / 52.0)
    assert coverage.ogs == pytest.approx(9.25 / 42.0)
    assert coverage.ars < 1.0 and coverage.ogs < 1.0


def test_binding_subsystem_is_the_smallest_coverage():
    coverage = ds.coverage_ratios(CONFIG)
    assert coverage.binding_subsystem == "ars"
    assert coverage.minimum == pytest.approx(coverage.ars)


def test_capacity_override_moves_the_coverage():
    coverage = ds.coverage_ratios(
        CONFIG, {"plant_sim.ogs.max_o2_kg_day": 42.0}
    )
    assert coverage.ogs == pytest.approx(1.0)


def test_water_loop_is_not_a_bottleneck_at_the_shipped_size():
    assert ds.coverage_ratios(CONFIG).wrs > 1.0


def test_wrs_throughput_uses_the_slower_of_step_and_operation():
    slow = dict(CONFIG)
    slow["plant_sim"] = dict(CONFIG["plant_sim"],
                             time={"step_seconds": 600, "wrs_operation_seconds": 3600})
    assert ds.wrs_throughput_l_day(slow, 10.0) == pytest.approx(10.0 * 24)


def test_halving_the_crew_doubles_every_coverage():
    halved = dict(CONFIG)
    halved["plant_sim"] = dict(CONFIG["plant_sim"],
                               crew=dict(CONFIG["plant_sim"]["crew"], size=25))
    base = ds.coverage_ratios(CONFIG)
    small = ds.coverage_ratios(halved)
    assert small.ars == pytest.approx(base.ars * 2)
    assert small.ogs == pytest.approx(base.ogs * 2)


# --------------------------------------------------------------------------- #
# design vector
# --------------------------------------------------------------------------- #
def test_design_vector_places_the_shipped_baseline_at_the_origin():
    vector = ds.design_vector({
        "plant_sim.ars.capacity_kg_day": 4.5,
        "plant_sim.ogs.max_o2_kg_day": 9.25,
        "plant_sim.wrs.max_feed_l_per_operation": 10.0,
    })
    assert all(component == pytest.approx(0.0) for component in vector)


def test_design_vector_is_logarithmic():
    vector = ds.design_vector({"plant_sim.ars.capacity_kg_day": 9.0})
    assert vector[0] == pytest.approx(math.log(2.0))


# --------------------------------------------------------------------------- #
# actuation space
# --------------------------------------------------------------------------- #
def test_actuation_vector_covers_all_three_subspaces():
    subspaces = {spec["subspace"] for spec in ds.ACTUATION_AXES.values()}
    assert subspaces == {"capacity", "action", "policy"}


def test_actuation_vector_is_zero_for_the_shipped_configuration():
    agents = {
        "actor": {
            "policy": {
                "ars_goal": {"initial_co2_mass": 4.5},
                "ogs_goal": {"input_water_mass": 0.15},
                "wrs_goal": {"urine_volume": 0.5},
                "request_co2_amount": 0.025,
            }
        }
    }
    vector = ds.actuation_vector(CONFIG, agents)
    assert all(v == pytest.approx(0.0) for v in vector.values())


def test_an_action_change_lands_only_in_the_action_subspace():
    agents = {"actor": {"policy": {"ars_goal": {"initial_co2_mass": 4.5 * 1.25}}}}
    delta = ds.actuation_vector(CONFIG, agents)
    norms = ds.subspace_norms(delta)
    assert norms["action"] == pytest.approx(math.log(1.25))
    assert norms["capacity"] == pytest.approx(0.0)
    assert norms["policy"] == pytest.approx(0.0)


def test_a_capacity_change_lands_only_in_the_capacity_subspace():
    config = dict(CONFIG)
    config["plant_sim"] = dict(CONFIG["plant_sim"], ogs={"max_o2_kg_day": 18.5})
    norms = ds.subspace_norms(ds.actuation_vector(config, {}))
    assert norms["capacity"] == pytest.approx(math.log(2.0))
    assert norms["action"] == pytest.approx(0.0)


def test_missing_axes_read_as_the_baseline_rather_than_being_dropped():
    vector = ds.actuation_vector({}, {})
    assert set(vector) == set(ds.ACTUATION_AXIS_NAMES)
    assert all(v == pytest.approx(0.0) for v in vector.values())


# --------------------------------------------------------------------------- #
# footprint and constraints
# --------------------------------------------------------------------------- #
def test_footprint_grows_with_capacity():
    small = ds.design_footprint(CONFIG)
    large = ds.design_footprint(CONFIG, {"plant_sim.ars.capacity_kg_day": 45.0})
    assert large["total_mass_kg"] > small["total_mass_kg"]
    assert large["total_cost_musd"] > small["total_cost_musd"]


def test_budget_limits_expose_the_declared_ceilings():
    budgets = ds.budget_limits(CONFIG)
    assert set(budgets) >= {"max_total_mass_kg", "max_total_cost_musd", "max_total_volume_m3"}


def test_capacity_bounds_are_ordered():
    for edge in ds.capacity_bounds(CONFIG).values():
        assert edge["min"] < edge["max"]


def test_design_point_assembles_every_view_of_one_design():
    point = ds.design_point(CONFIG, {"plant_sim.ogs.max_o2_kg_day": 42.0})
    assert point.coverage.ogs == pytest.approx(1.0)
    assert point.footprint["total_mass_kg"] > 0
    assert len(point.vector) == len(ds.CAPACITY_AXES)
