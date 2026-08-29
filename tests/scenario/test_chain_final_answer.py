"""What a chain of iterations is allowed to answer with.

Exploration across a chain is deliberately unrestricted: a sizing that loses
occupants, or one nobody could manufacture, may still be simulated and carried
forward, because that is how the next iteration learns anything. These tests
hold the other end of that bargain — the answer the chain hands back must keep
every occupant alive, must be buildable, and must not be quietly replaced by
whatever the last iteration happened to prefer.
"""

from __future__ import annotations

import json
from pathlib import Path

from scenario.ssos_eclss_loop.chain_selection import (
    STATUS_APPROVED,
    STATUS_NOT_COMPARABLE,
    STATUS_PROVISIONAL,
    STATUS_REJECTED,
    collect_chain_candidates,
    scoring_bar_drift,
    select_chain_final_answer,
)

ARS = "plant_sim.ars.capacity_kg_day"


def _candidate(
    candidate_id: str,
    *,
    ars: float,
    crew_remaining: int,
    crew_initial: int = 50,
    critical: int = 0,
    warning: int = 0,
    mass: float = 4000.0,
    status: str = "feasible",
    gate: bool = True,
    rank: int = 1,
) -> dict:
    return {
        "rank": rank,
        "candidate_id": candidate_id,
        "label": candidate_id,
        "fields": {ARS: ars},
        "crew_remaining": crew_remaining,
        "crew_initial": crew_initial,
        "critical_step_count": critical,
        "warning_step_count": warning,
        "physics_gate_passed": gate,
        "constraint_status": status,
        "total_mass_kg": mass,
        "total_volume_m3": 10.0,
        "total_cost_musd": 100.0,
    }


THRESHOLDS = {"co2_storage_high_kg": 2.0, "co2_storage_critical_kg": 8.0}


def _iteration(
    chain_dir: Path,
    index: int,
    candidates: list,
    *,
    baseline_crew: int = 30,
    crew_initial: int = 50,
    steps: int = 72,
    thresholds: dict | None = None,
    summary: bool = True,
) -> Path:
    run_dir = chain_dir / f"{index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if summary:
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "backend": "plant_sim",
                    "crew_initial": crew_initial,
                    "steps": steps,
                    "inject_failures": True,
                    "thresholds": thresholds if thresholds is not None else THRESHOLDS,
                }
            ),
            encoding="utf-8",
        )
    (run_dir / "candidate_rankings.json").write_text(
        json.dumps(
            {
                "baseline": {"crew_remaining": baseline_crew, "crew_initial": crew_initial},
                "ranking": candidates,
                "selection": {},
            }
        ),
        encoding="utf-8",
    )
    return run_dir


# --------------------------------------------------------------------------- #
# the answer is chosen across the whole chain, not taken from the last run
# --------------------------------------------------------------------------- #
def test_a_full_survival_design_from_an_early_iteration_is_not_lost(tmp_path: Path):
    """The defect this module exists for.

    Iteration 1 found a design that saves everyone. Iteration 2 explored and
    came back with one that does not. Reporting the chain by its last run would
    hand over the loss and leave the good design unnamed.
    """
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=52.0, crew_remaining=50)])
    _iteration(chain, 2, [_candidate("candidate_001", ars=20.0, crew_remaining=31)])

    answer = select_chain_final_answer([chain / "01", chain / "02"])

    assert answer["status"] == STATUS_APPROVED
    assert answer["selected"]["chain_candidate_id"] == "i1/candidate_001"
    assert answer["selected"]["iteration"] == 1
    assert answer["selected"]["crew_remaining"] == 50


def test_every_candidate_is_considered_not_only_each_iterations_winner(tmp_path: Path):
    chain = tmp_path / "chain"
    _iteration(
        chain,
        1,
        [
            _candidate("candidate_001", ars=60.0, crew_remaining=50, mass=6000.0, rank=1),
            # Ranked second inside its own iteration only because that run
            # never saw the lighter design below.
            _candidate("candidate_002", ars=52.0, crew_remaining=50, mass=4200.0, rank=2),
        ],
    )
    _iteration(chain, 2, [_candidate("candidate_001", ars=55.0, crew_remaining=50, mass=5000.0)])

    answer = select_chain_final_answer([chain / "01", chain / "02"])

    assert answer["candidates_considered"] == 3
    # Same crew, same dwell, so mass decides: the lightest of the three.
    assert answer["selected"]["chain_candidate_id"] == "i1/candidate_002"
    assert answer["decided_by"]["decided_by"] == "total_mass_kg"


def test_candidate_ids_are_qualified_by_iteration(tmp_path: Path):
    """``candidate_001`` names a different machine in every iteration."""
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=52.0, crew_remaining=50)])
    _iteration(chain, 2, [_candidate("candidate_001", ars=48.0, crew_remaining=50)])

    ids = [record["chain_candidate_id"] for record in collect_chain_candidates(
        [chain / "01", chain / "02"]
    )]
    assert ids == ["i1/candidate_001", "i2/candidate_001"]


# --------------------------------------------------------------------------- #
# what may not be answered with
# --------------------------------------------------------------------------- #
def test_a_design_that_loses_occupants_is_never_the_answer(tmp_path: Path):
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=30.0, crew_remaining=49)])
    _iteration(chain, 2, [_candidate("candidate_001", ars=35.0, crew_remaining=48)])

    answer = select_chain_final_answer([chain / "01", chain / "02"])

    assert answer["status"] == STATUS_REJECTED
    assert answer["selected"] is None
    # The near-miss is still reported -- as context, under a name that cannot
    # be mistaken for a recommendation.
    assert answer["best_observed"]["crew_remaining"] == 49
    assert "not_full_survival=49/50" in answer["best_observed"]["final_ineligible_reasons"]


def test_a_design_outside_the_manufacturable_range_is_never_the_answer(tmp_path: Path):
    chain = tmp_path / "chain"
    _iteration(
        chain,
        1,
        [_candidate("candidate_001", ars=900.0, crew_remaining=50, status="out_of_bounds")],
    )

    answer = select_chain_final_answer([chain / "01"])

    assert answer["status"] == STATUS_REJECTED
    assert answer["selected"] is None


def test_an_unaudited_design_is_never_the_answer(tmp_path: Path):
    """Survival the physics gate could not confirm is not survival."""
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=52.0, crew_remaining=50, gate=False)])

    answer = select_chain_final_answer([chain / "01"])

    assert answer["status"] == STATUS_REJECTED
    assert "physics_gate_not_passed" in answer["best_observed"]["final_ineligible_reasons"]


def test_over_budget_is_allowed_through_for_a_human_to_decide(tmp_path: Path):
    """Cost is a decision, not a disqualification.

    A machine that keeps everyone alive and busts the budget is a real answer
    to a real question: is the crew worth the money. That question belongs to a
    person, so the design is handed over marked, not filtered out.
    """
    chain = tmp_path / "chain"
    _iteration(
        chain,
        1,
        [_candidate("candidate_001", ars=52.0, crew_remaining=50, status="over_budget")],
    )

    answer = select_chain_final_answer([chain / "01"])

    assert answer["status"] == STATUS_PROVISIONAL
    assert answer["selected"]["chain_candidate_id"] == "i1/candidate_001"
    assert answer["requires_supervisor_approval"] is True


def test_nothing_found_is_reported_as_nothing_found(tmp_path: Path):
    chain = tmp_path / "chain"
    _iteration(chain, 1, [])

    answer = select_chain_final_answer([chain / "01"])

    assert answer["status"] == STATUS_REJECTED
    assert answer["selected"] is None
    assert answer["candidates_considered"] == 0


# --------------------------------------------------------------------------- #
# candidates may only be ranked against each other if they sat the same exam
# --------------------------------------------------------------------------- #
def test_a_threshold_that_moves_partway_through_stops_the_ranking(tmp_path: Path):
    """Iteration 3 sat an easier exam, so its marks are not iteration 1's marks."""
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=52.0, crew_remaining=50)])
    _iteration(
        chain,
        2,
        [_candidate("candidate_001", ars=20.0, crew_remaining=50)],
        thresholds={"co2_storage_high_kg": 9.0, "co2_storage_critical_kg": 30.0},
    )

    answer = select_chain_final_answer([chain / "01", chain / "02"])

    assert answer["status"] == STATUS_NOT_COMPARABLE
    assert answer["selected"] is None
    assert answer["ranking"] == []
    assert answer["scoring_bar_drift"][0]["iteration"] == 2
    assert answer["scoring_bar_drift"][0]["changed"] == ["thresholds"]


def test_a_crew_size_that_moves_partway_through_stops_the_ranking(tmp_path: Path):
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=52.0, crew_remaining=50)])
    _iteration(
        chain,
        2,
        [_candidate("candidate_001", ars=30.0, crew_remaining=20, crew_initial=20)],
        crew_initial=20,
    )

    drift = scoring_bar_drift([chain / "01", chain / "02"])
    assert drift[0]["changed"] == ["crew_initial"]
    assert drift[0]["expected"] == {"crew_initial": 50}
    assert drift[0]["found"] == {"crew_initial": 20}


def test_a_chain_run_away_from_the_shipped_scenario_is_still_comparable(tmp_path: Path):
    """Overridden once at the start is not the same as moved halfway through.

    A chain deliberately run at six occupants over eight steps differs from the
    scenario file in every one of these numbers and is entirely self-consistent.
    Refusing to rank it would make the check useless in the one setting it is
    most often used in.
    """
    chain = tmp_path / "chain"
    for index in (1, 2):
        _iteration(
            chain,
            index,
            [_candidate("candidate_001", ars=8.0, crew_remaining=6, crew_initial=6)],
            crew_initial=6,
            steps=8,
            baseline_crew=4,
        )

    answer = select_chain_final_answer([chain / "01", chain / "02"])

    assert answer["scoring_bar_drift"] == []
    assert answer["status"] == STATUS_APPROVED


def test_an_iteration_that_recorded_no_standard_is_not_ranked_against(tmp_path: Path):
    chain = tmp_path / "chain"
    _iteration(chain, 1, [_candidate("candidate_001", ars=52.0, crew_remaining=50)])
    _iteration(
        chain,
        2,
        [_candidate("candidate_001", ars=48.0, crew_remaining=50)],
        summary=False,
    )

    drift = scoring_bar_drift([chain / "01", chain / "02"])

    assert [row["iteration"] for row in drift] == [2]
    assert select_chain_final_answer([chain / "01", chain / "02"])["status"] == (
        STATUS_NOT_COMPARABLE
    )
