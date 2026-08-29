"""Unit tests for chain order parameters, archetypes and controllability."""

from __future__ import annotations

import math

import pytest

from tools.analysis import loop_dynamics as ld


# --------------------------------------------------------------------------- #
# archetype classification
# --------------------------------------------------------------------------- #
def test_a_chain_that_never_moves_is_frozen():
    assert ld.classify([0.0, 0.0], [None, None], [0.0, 0.0, 0.0]) == "frozen"


def test_a_chain_with_no_proposals_at_all_is_frozen():
    assert ld.classify([], [], [0.5]) == "frozen"


def test_movement_without_any_outcome_change_is_saturating():
    assert ld.classify([0.4, 0.4, 0.4], [None, 1.0, 1.0], [0.0, 0.0, 0.0, 0.0]) == "saturating"


def test_steady_improvement_is_converging():
    assert ld.classify([0.4, 0.2, 0.1], [None, 1.0, 1.0], [0.0, 0.3, 0.7, 1.0]) == "converging"


def test_one_reversal_on_the_way_up_is_overshooting():
    assert ld.classify([0.4, 0.4, 0.4], [None, -1.0, 1.0], [0.0, 0.2, 0.6, 1.0]) == "overshooting"


def test_repeated_reversals_are_oscillating():
    assert ld.classify([0.4, 0.4, 0.4], [None, -1.0, -1.0], [0.0, 0.4, 0.2, 0.5]) == "oscillating"


def test_movement_that_makes_things_worse_is_not_called_converging():
    assert ld.classify([0.4, 0.4], [None, 1.0], [1.0, 0.5, 0.0]) != "converging"


def test_the_archetypes_are_exhaustive_over_the_tested_shapes():
    cases = [
        ([0.0], [None], [0.0, 0.0]),
        ([0.4, 0.4], [None, 1.0], [0.0, 0.0, 0.0]),
        ([0.4, 0.2], [None, 1.0], [0.0, 0.5, 1.0]),
        ([0.4, 0.4], [None, -1.0], [0.0, 0.5, 1.0]),
        ([0.4, 0.4, 0.4], [None, -1.0, -1.0], [0.0, 0.4, 0.2, 0.5]),
    ]
    for steps, turning, outcomes in cases:
        assert ld.classify(steps, turning, outcomes) in ld.ARCHETYPES


def test_every_archetype_has_a_description():
    assert set(ld.ARCHETYPE_DESCRIPTIONS) == set(ld.ARCHETYPES)


def test_archetype_distribution_sums_to_one():
    chains = [_chain("saturating"), _chain("converging"), _chain("converging")]
    distribution = ld.archetype_distribution(chains)
    assert sum(distribution.values()) == pytest.approx(1.0)
    assert distribution["converging"] == pytest.approx(2 / 3)


def test_archetype_distribution_of_no_chains_is_all_zero():
    assert set(ld.archetype_distribution([]).values()) == {0.0}


def _chain(archetype: str) -> ld.ChainDynamics:
    return ld.ChainDynamics(
        chain_id="c", design_mode="labeled_rule_base", states=(),
        archetype=archetype, total_displacement=0.0, displacement_by_subspace={},
        outcome_change=0.0, proposed_share={}, applied_share={},
        magnitude_share={}, discarded_fraction=0.0, verdict=None,
    )


# --------------------------------------------------------------------------- #
# change-kind mapping
# --------------------------------------------------------------------------- #
def test_capacity_and_action_changes_map_to_different_subspaces():
    assert ld.SUBSPACE_BY_CHANGE_KIND["capacity_profile"] == "capacity"
    assert ld.SUBSPACE_BY_CHANGE_KIND["action_profile"] == "action"
    assert ld.SUBSPACE_BY_CHANGE_KIND["service_config"] == "action"
    assert ld.SUBSPACE_BY_CHANGE_KIND["set_parameter"] == "policy"


# --------------------------------------------------------------------------- #
# controllability
# --------------------------------------------------------------------------- #
def _oat_rows(axis: str, subspace: str, pairs):
    return [
        {"axis": axis, "subspace": subspace, "multiplier": m, "survival_fraction": s}
        for m, s in pairs
    ]


def test_controllability_is_zero_for_an_axis_that_changes_nothing():
    rows = _oat_rows("dead", "action", [(0.5, 0.0), (1.0, 0.0), (2.0, 0.0), (4.0, 0.0)])
    control = ld.controllability(rows)[0]
    assert control.gain == pytest.approx(0.0)
    assert control.outcome_range == pytest.approx(0.0)


def test_controllability_is_positive_for_an_axis_that_moves_the_outcome():
    rows = _oat_rows("live", "capacity", [(1.0, 0.0), (math.e, 1.0)])
    control = ld.controllability(rows)[0]
    assert control.gain == pytest.approx(1.0)


def test_controllability_reports_the_largest_local_slope_not_the_average():
    rows = _oat_rows("kink", "capacity",
                     [(1.0, 0.0), (math.e, 0.0), (math.e ** 2, 1.0)])
    assert ld.controllability(rows)[0].gain == pytest.approx(1.0)


def test_controllability_is_sorted_with_the_strongest_axis_first():
    rows = (
        _oat_rows("weak", "action", [(1.0, 0.0), (math.e, 0.1)])
        + _oat_rows("strong", "capacity", [(1.0, 0.0), (math.e, 1.0)])
    )
    assert [c.axis for c in ld.controllability(rows)] == ["strong", "weak"]


def test_controllability_ignores_rows_without_labels():
    rows = _oat_rows("live", "capacity", [(1.0, 0.0), (math.e, 1.0)])
    rows.append({"survival_fraction": 0.5})
    assert len(ld.controllability(rows)) == 1


def test_controllability_skips_non_positive_multipliers():
    rows = _oat_rows("live", "capacity", [(0.0, 0.0), (1.0, 0.0), (math.e, 1.0)])
    assert ld.controllability(rows)[0].n_points == 2


# --------------------------------------------------------------------------- #
# effective gain
# --------------------------------------------------------------------------- #
def test_effective_gain_is_zero_when_actuation_misses_the_controllable_axis():
    controls = [
        ld.AxisControllability("cap", "capacity", gain=1.2, outcome_range=1.0, n_points=5),
        ld.AxisControllability("act", "action", gain=0.0, outcome_range=0.0, n_points=5),
    ]
    gains = ld.effective_gain({"capacity": 0.0, "action": 1.0}, controls)
    assert gains["action"] == pytest.approx(0.0)
    assert gains["capacity"] == pytest.approx(0.0)


def test_effective_gain_is_the_product_of_share_and_controllability():
    controls = [
        ld.AxisControllability("cap", "capacity", gain=2.0, outcome_range=1.0, n_points=5),
    ]
    gains = ld.effective_gain({"capacity": 0.5}, controls)
    assert gains["capacity"] == pytest.approx(1.0)


def test_effective_gain_uses_the_best_axis_within_a_subspace():
    controls = [
        ld.AxisControllability("a", "capacity", gain=0.1, outcome_range=0.1, n_points=3),
        ld.AxisControllability("b", "capacity", gain=3.0, outcome_range=1.0, n_points=3),
    ]
    assert ld.effective_gain({"capacity": 1.0}, controls)["capacity"] == pytest.approx(3.0)
