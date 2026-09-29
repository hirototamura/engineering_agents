"""Academic analysis layer for the ECLSS design->verify loop.

This package treats an Engineering Agents campaign as a *dynamical system on a
design space* and provides the statistics and figures needed to characterise it:

``design_space``
    Maps a scenario config to the normalised design vector and to the
    dimensionless coverage ratios ``rho`` (installed capacity / crew demand)
    that act as the order parameters of the system.
``artifacts``
    Reads a run directory (or an ``--iterate`` chain directory) into flat
    records, using the same canonical-row rule as the scorecard so that the
    analysis and the evaluation never disagree about what a step was.
``statistics``
    Dependency-light (numpy-only) inference: bootstrap intervals, exact
    permutation tests, Cliff's delta, logistic response fits, Kaplan-Meier with
    right censoring, and balanced accuracy for model comparison.
``loop_dynamics``
    Order parameters of a design chain (displacement, step norm, turning angle,
    actuation share) and the trajectory archetype taxonomy.
``experiments``
    Batch harness that drives ``tools.cli`` to build response surfaces,
    one-at-a-time sensitivities, crew-scaling curves and design chains.
``figures`` / ``report``
    Publication-style matplotlib figures and a single self-contained HTML
    report that embeds them.

The layering rule (``tools -> scenario -> environment -> core``) holds: this
package reads scenario modules and run artifacts and never the reverse.
"""

from tools.analysis.design_space import (
    CAPACITY_AXES,
    CoverageRatios,
    DesignPoint,
    coverage_ratios,
    crew_demand,
    design_footprint,
    design_vector,
)
from tools.analysis.statistics import (
    BootstrapInterval,
    KaplanMeierCurve,
    LogisticFit,
    balanced_accuracy,
    bootstrap_mean,
    cliffs_delta,
    fit_logistic_response,
    kaplan_meier,
    permutation_test,
)

__all__ = [
    "BootstrapInterval",
    "CAPACITY_AXES",
    "CoverageRatios",
    "DesignPoint",
    "KaplanMeierCurve",
    "LogisticFit",
    "balanced_accuracy",
    "bootstrap_mean",
    "cliffs_delta",
    "coverage_ratios",
    "crew_demand",
    "design_footprint",
    "design_vector",
    "fit_logistic_response",
    "kaplan_meier",
    "permutation_test",
]
