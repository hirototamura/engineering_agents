"""Unit tests for the numpy-only estimators in ``tools.analysis.statistics``.

Each estimator is checked against a case with a known closed-form answer rather
than against a previous run of itself, so a regression cannot be blessed by
updating a stored number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tools.analysis import statistics as st


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #
def test_bootstrap_mean_brackets_the_point_estimate():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    interval = st.bootstrap_mean(values, resamples=500)
    assert interval.estimate == pytest.approx(4.5)
    assert interval.low < interval.estimate < interval.high


def test_bootstrap_of_a_constant_sample_has_zero_width():
    interval = st.bootstrap_mean([3.0] * 10, resamples=200)
    assert interval.low == pytest.approx(3.0)
    assert interval.high == pytest.approx(3.0)


def test_bootstrap_is_reproducible_for_a_fixed_seed():
    values = list(np.linspace(0, 1, 25))
    first = st.bootstrap_mean(values, resamples=300, seed=7)
    second = st.bootstrap_mean(values, resamples=300, seed=7)
    assert first.low == second.low and first.high == second.high


def test_bootstrap_of_empty_input_is_nan_rather_than_an_error():
    interval = st.bootstrap_mean([])
    assert math.isnan(interval.estimate)


# --------------------------------------------------------------------------- #
# effect size and permutation
# --------------------------------------------------------------------------- #
def test_cliffs_delta_is_plus_one_for_complete_separation():
    assert st.cliffs_delta([5, 6, 7], [1, 2, 3]) == pytest.approx(1.0)


def test_cliffs_delta_is_minus_one_when_reversed():
    assert st.cliffs_delta([1, 2, 3], [5, 6, 7]) == pytest.approx(-1.0)


def test_cliffs_delta_is_zero_for_identical_samples():
    assert st.cliffs_delta([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)


def test_cliffs_delta_magnitude_labels():
    assert st.cliffs_delta_magnitude(0.05) == "negligible"
    assert st.cliffs_delta_magnitude(0.9) == "large"


def test_permutation_test_separates_clearly_different_samples():
    result = st.permutation_test(
        [10.0] * 8, [0.0] * 8, permutations=400
    )
    assert result.observed == pytest.approx(10.0)
    assert result.p_value < 0.05


def test_permutation_test_p_value_is_never_exactly_zero():
    result = st.permutation_test([1.0, 1.0], [0.0, 0.0], permutations=50)
    assert result.p_value > 0.0


def test_permutation_test_on_identical_samples_is_not_significant():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    result = st.permutation_test(values, values, permutations=400)
    assert result.p_value > 0.05


# --------------------------------------------------------------------------- #
# logistic response
# --------------------------------------------------------------------------- #
def test_fit_logistic_recovers_known_parameters():
    x = np.linspace(-4, 6, 60)
    truth_x0, truth_w = 1.5, 0.6
    y = 1.0 / (1.0 + np.exp(-(x - truth_x0) / truth_w))
    fit = st.fit_logistic_response(x, y)
    assert fit.x0 == pytest.approx(truth_x0, abs=0.05)
    assert fit.width == pytest.approx(truth_w, abs=0.05)
    assert fit.r_squared > 0.999


def test_logistic_max_slope_matches_the_analytic_value():
    fit = st.LogisticFit(x0=0.0, width=0.25, r_squared=1.0, rmse=0.0, n=10)
    assert fit.max_slope == pytest.approx(1.0)


def test_logistic_predict_is_a_half_at_the_midpoint():
    fit = st.LogisticFit(x0=2.0, width=0.5, r_squared=1.0, rmse=0.0, n=10)
    assert float(fit.predict(2.0)) == pytest.approx(0.5)


def test_fit_logistic_with_too_few_points_returns_nan():
    fit = st.fit_logistic_response([1.0, 2.0], [0.0, 1.0])
    assert math.isnan(fit.x0)


def test_fit_logistic_can_represent_a_decreasing_response():
    x = np.linspace(0.0, 8.0, 40)
    y = 1.0 / (1.0 + np.exp((x - 3.0) / 0.5))
    fit = st.fit_logistic_response(x, y)
    assert fit.width < 0
    assert fit.r_squared > 0.99
    assert fit.as_dict()["published"] is True


# --------------------------------------------------------------------------- #
# goodness of fit
# --------------------------------------------------------------------------- #
def test_r_squared_is_one_for_a_perfect_prediction():
    values = [1.0, 2.0, 3.0]
    assert st.r_squared(values, values) == pytest.approx(1.0)


def test_r_squared_is_zero_for_the_mean_predictor():
    values = [1.0, 2.0, 3.0]
    assert st.r_squared(values, [2.0, 2.0, 2.0]) == pytest.approx(0.0)


def test_r_squared_goes_negative_for_a_worse_than_mean_prediction():
    assert st.r_squared([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) < 0.0


def test_rmse_matches_the_hand_computed_value():
    assert st.rmse([0.0, 0.0], [1.0, 1.0]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# balanced accuracy
# --------------------------------------------------------------------------- #
def test_balanced_accuracy_penalises_a_constant_predictor_on_imbalanced_data():
    truth = [True] * 9 + [False]
    assert st.balanced_accuracy(truth, [True] * 10) == pytest.approx(0.5)


def test_balanced_accuracy_is_one_for_a_perfect_predictor():
    truth = [True, False, True, False]
    assert st.balanced_accuracy(truth, truth) == pytest.approx(1.0)


def test_balanced_accuracy_is_zero_when_every_label_is_inverted():
    truth = [True, False, True, False]
    assert st.balanced_accuracy(truth, [not t for t in truth]) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# survival analysis
# --------------------------------------------------------------------------- #
def test_kaplan_meier_without_censoring_is_the_empirical_survival():
    curve = st.kaplan_meier([1.0, 2.0, 3.0, 4.0], [True] * 4)
    assert curve.survival[-1] == pytest.approx(0.0)
    assert curve.survival[1] == pytest.approx(0.75)
    assert curve.n_events == 4


def test_kaplan_meier_censoring_keeps_the_curve_above_zero():
    curve = st.kaplan_meier([1.0, 2.0, 3.0, 4.0], [True, False, False, False])
    assert curve.n_events == 1
    assert curve.survival[-1] == pytest.approx(0.75)


def test_kaplan_meier_median_is_the_first_time_at_or_below_half():
    curve = st.kaplan_meier([1.0, 2.0, 3.0, 4.0], [True] * 4)
    assert curve.median() == pytest.approx(2.0)


def test_kaplan_meier_median_is_infinite_when_never_reached():
    curve = st.kaplan_meier([1.0, 2.0, 3.0, 4.0], [True, False, False, False])
    assert math.isinf(curve.median())


def test_log_rank_detects_clearly_separated_groups():
    result = st.log_rank_test(
        list(range(1, 11)), [True] * 10,
        list(range(51, 61)), [True] * 10,
    )
    assert result.p_value < 0.01


def test_log_rank_finds_no_difference_between_identical_groups():
    times = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = st.log_rank_test(times, [True] * 5, times, [True] * 5)
    assert result.p_value > 0.5


# --------------------------------------------------------------------------- #
# derivatives and correlation
# --------------------------------------------------------------------------- #
def test_central_difference_of_a_line_is_its_slope():
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [2.0 * v + 1.0 for v in x]
    _, slope = st.central_difference(x, y)
    assert np.allclose(slope, 2.0)


def test_central_difference_peaks_at_a_step():
    x = list(np.linspace(0, 10, 41))
    y = [0.0 if v < 5 else 1.0 for v in x]
    centres, slope = st.central_difference(x, y)
    assert centres[int(np.argmax(np.abs(slope)))] == pytest.approx(5.0, abs=0.3)


def test_spearman_is_one_for_a_monotone_nonlinear_relation():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [v ** 3 for v in x]
    assert st.spearman(x, y) == pytest.approx(1.0)
    assert st.pearson(x, y) < 1.0


def test_summarise_reports_the_expected_moments():
    out = st.summarise([1.0, 2.0, 3.0])
    assert out["n"] == 3.0
    assert out["mean"] == pytest.approx(2.0)
    assert out["median"] == pytest.approx(2.0)
    assert out["min"] == pytest.approx(1.0)


def test_summarise_empty_includes_median():
    out = st.summarise([])
    assert out["n"] == 0.0
    assert math.isnan(out["median"])
    assert math.isnan(out["mean"])
