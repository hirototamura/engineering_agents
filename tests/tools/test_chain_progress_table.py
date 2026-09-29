"""What the live table shows while a design chain is running.

An iterating run is judged on two numbers: how many occupants came back, and
what the scorecard made of the design that brought them back. The table showed
the first and not the second, so a chain spending ten rounds getting worse read
exactly like one getting better.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from rich.console import Console

from tools.cli.output import crew_remaining_table

ARS = "plant_sim.ars.capacity_kg_day"
OGS = "plant_sim.ogs.max_o2_kg_day"
WRS = "plant_sim.wrs.max_feed_l_per_operation"


def _row(
    iteration: Any,
    *,
    crew_remaining: Optional[int] = 50,
    score: Optional[float] = None,
    status: str = "scored",
    sizing: Optional[tuple] = (20.8, 42.0, 2.0),
    applied_from: Optional[str] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "iteration": iteration,
        "crew_initial": 50,
        "crew_remaining": crew_remaining,
        "crew_lost": None if crew_remaining is None else 50 - crew_remaining,
        "evaluation_score": score,
        "evaluation_max_score": 100,
        "evaluation_status": status,
        "design_proposal_count": 1,
    }
    if sizing is not None:
        row["installed_capacity"] = dict(zip((ARS, OGS, WRS), sizing))
    if applied_from is not None:
        row["apply_proposals_path"] = f"C:\\chain\\{applied_from}\\applied_proposals.json"
    return row


def _render(rows, width: int = 110) -> str:
    console = Console(width=width, force_terminal=False, legacy_windows=False, record=True)
    console.print(crew_remaining_table(rows))
    return console.export_text()


def test_every_round_shows_its_score_and_which_way_it_moved():
    text = _render(
        [
            _row(1, crew_remaining=0, score=58.04, sizing=(4.5, 9.25, 10.0)),
            _row(2, score=62.02, sizing=(20.8, 42.0, 10.0), applied_from="01"),
            _row(3, score=65.45, sizing=(20.8, 42.0, 2.0), applied_from="02"),
            _row(4, score=58.02, sizing=(23.92, 48.3, 5.0), applied_from="03"),
        ]
    )
    assert "58.04" in text and "62.02" in text and "65.45" in text
    # The move, not just the level: a chain that is sliding has to look like one.
    assert "+3.98" in text
    assert "-7.43" in text
    assert "Score /100" in text


def test_the_sizing_that_produced_the_score_is_on_the_same_line():
    text = _render([_row(1, score=65.45, sizing=(20.8, 42.0, 2.0))])
    assert "20.8 / 42 / 2" in text


def test_the_best_round_so_far_is_marked_and_only_if_everyone_came_back():
    text = _render(
        [
            # A higher score that lost the crew is not a design to steer towards.
            _row(1, crew_remaining=0, score=90.0),
            _row(2, score=62.02),
            _row(3, score=65.45),
            _row(4, score=61.00),
        ]
    )
    lines = [line for line in text.splitlines() if "│" in line]
    marked = [line for line in lines if "★" in line]
    assert len(marked) == 2
    assert marked[0].lstrip("│ ").startswith("2")
    assert marked[1].lstrip("│ ").startswith("3")


def test_the_crew_column_says_how_many_out_of_how_many():
    text = _render([_row(1, crew_remaining=46), _row(2, crew_remaining=50)])
    assert "46/50" in text
    assert "50/50" in text


def test_a_round_with_no_score_says_why_rather_than_showing_a_blank():
    text = _render([_row("baseline-replay", score=None, status="incomplete", sizing=None)])
    assert "incomplete" in text


def test_a_replay_row_without_a_config_still_renders():
    """Replays are summary rows too, and they never carry installed capacity."""
    text = _render([_row("final-replay", score=None, status="not_applicable", sizing=None)])
    assert "final-replay" in text or "final-repl" in text
