"""The note one iteration of a design chain leaves for the next one.

The failure this exists to prevent is concrete: a round that kept every
occupant alive is followed by a partial proposal, the omitted subsystems fall
back to their baseline sizes, and the next run loses the whole crew. Nothing in
the chain notices, because no iteration reads any run but its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence

import yaml

from scenario.ssos_eclss_loop.chain_memory import (
    ARS_KEY,
    CHAIN_MEMORY_FILENAME,
    DEFAULT_MIN_SCORE_DELTA,
    DEFAULT_STAGNATION_WINDOW,
    MAX_MEMORY_BYTES,
    MODE_DIVERSIFY,
    OGS_KEY,
    PATTERN_BELOW_FLOOR,
    PATTERN_DROPPED_TO_BASELINE,
    STAGNATION_ACTIVE,
    STAGNATION_COOLDOWN,
    STAGNATION_IMPROVING,
    STAGNATION_NOT_COMPARABLE,
    STAGNATION_WARMING_UP,
    TIER_FULL,
    TIER_PARTIAL,
    TIER_ZERO,
    WRS_KEY,
    capacity_keys_in_document,
    exploration_settings,
    load_chain_memory,
    survival_tier,
    theoretical_floor_from_trace,
    update_compact_chain_memory,
)
from scenario.ssos_eclss_loop.design_state import build_design_state
from scenario.ssos_eclss_loop.design_tools import DesignToolContext, DesignToolkit
from scenario.ssos_eclss_loop.design_variables import BASELINE_CAPACITY

FLOOR = {ARS_KEY: 20.8, OGS_KEY: 42.0, WRS_KEY: 1.5625}
# The sizing this fixture's rounds fly, unless a test says otherwise.
SURVIVOR = {ARS_KEY: 20.8, OGS_KEY: 42.0}


def _write_iteration(
    chain_dir: Path,
    index: int,
    *,
    fields: dict,
    crew_remaining: int,
    crew_initial: int = 50,
    score: float = 60.0,
    status: str = "scored",
    gate_passed: bool = True,
    with_trace: bool = True,
) -> Path:
    """One finished iteration on disk: what ran, and how it went."""
    run_dir = chain_dir / f"{index:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(
        json.dumps({"crew_initial": crew_initial, "crew_remaining": crew_remaining}),
        encoding="utf-8",
    )
    (run_dir / "evaluation.json").write_text(
        json.dumps(
            {
                "status": status,
                "physics_gate": {"passed": gate_passed},
                "scores": {"total": score, "max_score": 100},
            }
        ),
        encoding="utf-8",
    )
    config = {
        "plant_sim": {
            "crew": {"size": crew_initial},
            "ars": {"capacity_kg_day": fields[ARS_KEY]},
            "ogs": {"max_o2_kg_day": fields[OGS_KEY]},
            "wrs": {"max_feed_l_per_operation": fields[WRS_KEY]},
        }
    }
    (run_dir / "scenario_config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    if with_trace:
        (run_dir / "tool_trace.jsonl").write_text(
            json.dumps(
                {
                    "event": "tool_call",
                    "tool": "compute_theoretical_capacity",
                    "arguments": {},
                    "result": {
                        "subsystems": {
                            "ars": {"required_nameplate_kg_day": FLOOR[ARS_KEY]},
                            "ogs": {"required_nameplate_kg_day": FLOOR[OGS_KEY]},
                            "wrs": {"expected_feed_l_per_step": FLOOR[WRS_KEY]},
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    return run_dir


def _survivor_fields(wrs: float = 1.8) -> dict:
    return {ARS_KEY: 20.8, OGS_KEY: 42.0, WRS_KEY: wrs}


def _baseline_fields() -> dict:
    return dict(BASELINE_CAPACITY)


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #
def test_a_run_outside_a_chain_has_no_memory_and_says_so(tmp_path: Path):
    assert load_chain_memory(tmp_path / "solo") is None


def test_an_iteration_reads_the_note_left_at_the_chain_root(tmp_path: Path):
    (tmp_path / CHAIN_MEMORY_FILENAME).write_text(
        json.dumps({"schema_version": "1.0", "updated_after_iteration": 7}), encoding="utf-8"
    )
    run_dir = tmp_path / "08"
    run_dir.mkdir()
    memory = load_chain_memory(run_dir)
    assert memory["updated_after_iteration"] == 7


def test_a_corrupt_note_is_an_error_object_not_an_exception(tmp_path: Path):
    (tmp_path / CHAIN_MEMORY_FILENAME).write_text("{not json", encoding="utf-8")
    memory = load_chain_memory(tmp_path)
    assert memory["error"] == "failed_to_load_chain_memory"
    assert memory["path"].endswith(CHAIN_MEMORY_FILENAME)
    assert memory["message"]


def test_a_note_that_is_not_an_object_is_refused_the_same_way(tmp_path: Path):
    (tmp_path / CHAIN_MEMORY_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    assert load_chain_memory(tmp_path)["error"] == "failed_to_load_chain_memory"


# --------------------------------------------------------------------------- #
# what the note keeps
# --------------------------------------------------------------------------- #
def test_a_round_that_saved_everyone_becomes_the_best_on_record(tmp_path: Path):
    run_dir = _write_iteration(
        tmp_path, 1, fields=_survivor_fields(), crew_remaining=50, score=66.2
    )
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)

    memory = load_chain_memory(tmp_path)
    best = memory["best_full_survival"]
    assert best["iteration"] == 1
    assert best["crew_remaining"] == best["crew_initial"] == 50
    assert best["score"] == 66.2
    assert best["fields"] == _survivor_fields()
    assert best["physics_gate_passed"] is True
    assert memory["theoretical_floor"] == FLOOR
    assert memory["objective"]["primary"] == "maximize_crew_remaining"


def test_a_round_that_lost_the_crew_does_not_replace_the_best(tmp_path: Path):
    good = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50, score=66.2)
    update_compact_chain_memory(tmp_path, good, iteration=1)
    # A higher score means nothing when the crew did not come back.
    bad = _write_iteration(tmp_path, 2, fields=_baseline_fields(), crew_remaining=0, score=99.0)
    update_compact_chain_memory(tmp_path, bad, iteration=2)

    memory = load_chain_memory(tmp_path)
    assert memory["best_full_survival"]["iteration"] == 1
    assert memory["best_full_survival"]["score"] == 66.2
    assert memory["updated_after_iteration"] == 2


def test_a_failed_physics_gate_keeps_a_full_survival_round_off_the_record(tmp_path: Path):
    run_dir = _write_iteration(
        tmp_path, 1, fields=_survivor_fields(), crew_remaining=50, gate_passed=False
    )
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)
    assert load_chain_memory(tmp_path)["best_full_survival"] is None


def test_an_unscored_round_is_not_a_best_either(tmp_path: Path):
    run_dir = _write_iteration(
        tmp_path, 1, fields=_survivor_fields(), crew_remaining=50, status="not_applicable"
    )
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)
    assert load_chain_memory(tmp_path)["best_full_survival"] is None


def test_the_last_effective_design_is_what_ran_not_what_was_proposed(tmp_path: Path):
    """The proposal asked for one machine; the config says which was built."""
    run_dir = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50)
    (run_dir / "design_proposals.json").write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "change_kind": "capacity_profile",
                        "payload": {"fields": {ARS_KEY: 999.0, OGS_KEY: 999.0, WRS_KEY: 999.0}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)

    last = load_chain_memory(tmp_path)["last_effective_design"]
    assert last["fields"] == _survivor_fields()
    assert 999.0 not in last["fields"].values()
    assert last["iteration"] == 1
    assert last["crew_remaining"] == 50


def test_the_best_survives_being_overtaken_only_by_a_higher_score(tmp_path: Path):
    first = _write_iteration(
        tmp_path, 1, fields=_survivor_fields(1.8), crew_remaining=50, score=66.2
    )
    update_compact_chain_memory(tmp_path, first, iteration=1)
    lower = _write_iteration(
        tmp_path, 2, fields=_survivor_fields(2.5), crew_remaining=50, score=60.0
    )
    update_compact_chain_memory(tmp_path, lower, iteration=2)
    assert load_chain_memory(tmp_path)["best_full_survival"]["iteration"] == 1

    higher = _write_iteration(
        tmp_path, 3, fields=_survivor_fields(2.0), crew_remaining=50, score=70.0
    )
    update_compact_chain_memory(tmp_path, higher, iteration=3)
    assert load_chain_memory(tmp_path)["best_full_survival"]["iteration"] == 3


# --------------------------------------------------------------------------- #
# the failures it counts
# --------------------------------------------------------------------------- #
def test_a_partial_proposal_that_gave_back_ars_and_ogs_is_counted(tmp_path: Path):
    grown = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50)
    update_compact_chain_memory(tmp_path, grown, iteration=1)
    # Iteration 2 applied a WRS-only proposal, so ARS and OGS came back baseline.
    reset = _write_iteration(
        tmp_path, 2, fields={**_baseline_fields(), WRS_KEY: 1.8}, crew_remaining=0
    )
    update_compact_chain_memory(tmp_path, reset, iteration=2, applied_capacity_keys=[WRS_KEY])

    patterns = {p["id"]: p for p in load_chain_memory(tmp_path)["known_bad_patterns"]}
    assert patterns[PATTERN_DROPPED_TO_BASELINE]["observed_count"] == 1
    assert patterns[PATTERN_DROPPED_TO_BASELINE]["avoid_if_possible"] is True


def test_a_complete_proposal_is_not_counted_as_a_drop(tmp_path: Path):
    grown = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50)
    update_compact_chain_memory(tmp_path, grown, iteration=1)
    same = _write_iteration(tmp_path, 2, fields=_survivor_fields(2.0), crew_remaining=50)
    update_compact_chain_memory(
        tmp_path, same, iteration=2, applied_capacity_keys=[ARS_KEY, OGS_KEY, WRS_KEY]
    )
    ids = [p["id"] for p in load_chain_memory(tmp_path)["known_bad_patterns"]]
    assert PATTERN_DROPPED_TO_BASELINE not in ids


def test_sizing_under_the_floor_and_losing_the_crew_is_counted_with_its_thresholds(
    tmp_path: Path,
):
    run_dir = _write_iteration(tmp_path, 1, fields=_baseline_fields(), crew_remaining=0)
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)

    patterns = {p["id"]: p for p in load_chain_memory(tmp_path)["known_bad_patterns"]}
    breach = patterns[PATTERN_BELOW_FLOOR]
    assert breach["observed_count"] == 1
    assert breach["thresholds"] == {ARS_KEY: 20.8, OGS_KEY: 42.0}


def test_sizing_under_the_floor_without_losing_anyone_is_not_counted(tmp_path: Path):
    run_dir = _write_iteration(tmp_path, 1, fields=_baseline_fields(), crew_remaining=50)
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)
    ids = [p["id"] for p in load_chain_memory(tmp_path)["known_bad_patterns"]]
    assert PATTERN_BELOW_FLOOR not in ids


def test_repeated_failures_accumulate_on_one_entry(tmp_path: Path):
    for index in range(1, 4):
        run_dir = _write_iteration(tmp_path, index, fields=_baseline_fields(), crew_remaining=0)
        update_compact_chain_memory(tmp_path, run_dir, iteration=index)
    patterns = load_chain_memory(tmp_path)["known_bad_patterns"]
    below = [p for p in patterns if p["id"] == PATTERN_BELOW_FLOOR]
    assert len(below) == 1
    assert below[0]["observed_count"] == 3


# --------------------------------------------------------------------------- #
# the budget the note is written against
# --------------------------------------------------------------------------- #
def test_the_note_stays_inside_the_context_budget_over_a_long_chain(tmp_path: Path):
    for index in range(1, 51):
        fields = _survivor_fields() if index % 2 else _baseline_fields()
        run_dir = _write_iteration(
            tmp_path,
            index,
            fields=fields,
            crew_remaining=50 if index % 2 else 0,
            score=60.0 + index,
        )
        update_compact_chain_memory(
            tmp_path, run_dir, iteration=index, applied_capacity_keys=[WRS_KEY]
        )
    path = tmp_path / CHAIN_MEMORY_FILENAME
    assert path.stat().st_size <= MAX_MEMORY_BYTES
    memory = json.loads(path.read_text(encoding="utf-8"))
    assert len(memory["known_bad_patterns"]) <= 5
    # 50 rounds in, it still names one best design and one installed design.
    assert isinstance(memory["best_full_survival"], dict)
    assert isinstance(memory["last_effective_design"], dict)


def test_a_corrupt_note_is_rewritten_rather_than_inherited(tmp_path: Path):
    (tmp_path / CHAIN_MEMORY_FILENAME).write_text("{ truncated", encoding="utf-8")
    run_dir = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50)
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)
    memory = load_chain_memory(tmp_path)
    assert memory.get("error") is None
    assert memory["best_full_survival"]["iteration"] == 1


def test_an_iteration_that_wrote_nothing_leaves_the_note_alone(tmp_path: Path):
    empty = tmp_path / "01"
    empty.mkdir()
    assert update_compact_chain_memory(tmp_path, empty, iteration=1) is None
    assert not (tmp_path / CHAIN_MEMORY_FILENAME).exists()


def test_the_floor_comes_from_the_designers_own_capacity_call(tmp_path: Path):
    run_dir = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50)
    assert theoretical_floor_from_trace(run_dir / "tool_trace.jsonl") == FLOOR


def test_a_capacity_call_for_a_different_crew_is_not_the_floor(tmp_path: Path):
    trace = tmp_path / "tool_trace.jsonl"
    trace.write_text(
        json.dumps(
            {
                "tool": "compute_theoretical_capacity",
                "arguments": {"crew_size": 6},
                "result": {"subsystems": {"ars": {"required_nameplate_kg_day": 2.5}}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert theoretical_floor_from_trace(trace) == {}


def test_the_floor_survives_a_result_kept_only_as_text(tmp_path: Path):
    trace = tmp_path / "tool_trace.jsonl"
    trace.write_text(
        json.dumps(
            {
                "tool": "compute_theoretical_capacity",
                "arguments": {},
                "result_excerpt": json.dumps(
                    {"subsystems": {"ogs": {"required_nameplate_kg_day": 42.0}}}
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert theoretical_floor_from_trace(trace) == {OGS_KEY: 42.0}


def test_a_missing_capacity_call_keeps_the_floor_the_chain_already_had(tmp_path: Path):
    first = _write_iteration(tmp_path, 1, fields=_survivor_fields(), crew_remaining=50)
    update_compact_chain_memory(tmp_path, first, iteration=1)
    second = _write_iteration(
        tmp_path, 2, fields=_survivor_fields(), crew_remaining=50, with_trace=False
    )
    update_compact_chain_memory(tmp_path, second, iteration=2)
    assert load_chain_memory(tmp_path)["theoretical_floor"] == FLOOR



def test_a_documents_named_variables_are_read_off_the_document(tmp_path: Path):
    document = {
        "changes": [
            {"change_kind": "set_parameter", "payload": {"fields": {ARS_KEY: 1.0}}},
            {"change_kind": "capacity_profile", "payload": {"fields": {WRS_KEY: 1.8}}},
        ]
    }
    assert capacity_keys_in_document(document) == [WRS_KEY]
    assert capacity_keys_in_document({}) == []
    assert capacity_keys_in_document(None) == []


# --------------------------------------------------------------------------- #
# what the designer is shown
# --------------------------------------------------------------------------- #
def _state(chain_memory) -> dict:
    return build_design_state(
        baseline_outcome={"crew_initial": 50, "crew_remaining": 0},
        theory={},
        features={},
        candidates=[],
        scenario_config={},
        decisions_left=2,
        candidate_budget_left=1,
        chain_memory=chain_memory,
    )


def test_the_decision_page_carries_the_best_design_earlier_rounds_found(tmp_path: Path):
    run_dir = _write_iteration(
        tmp_path, 1, fields=_survivor_fields(), crew_remaining=50, score=66.2
    )
    update_compact_chain_memory(tmp_path, run_dir, iteration=1)

    memory = _state(load_chain_memory(tmp_path))["chain_memory"]
    assert memory["best_full_survival"]["fields"] == _survivor_fields()
    assert memory["theoretical_floor"] == FLOOR
    assert memory["proposal_guidance"]["prefer_complete_capacity_profile"] is True
    assert memory["proposal_guidance"]["do_not_reduce_below_best_without_reason"] is True
    assert len(memory["proposal_guidance"]["include_all_design_variables"]) == 3
    assert "best_full_survival" in memory["note"]
    assert "theoretical_floor" in memory["note"]


def test_the_decision_page_says_nothing_when_there_is_no_memory():
    assert "chain_memory" not in _state(None)
    assert "chain_memory" not in _state({"error": "failed_to_load_chain_memory"})


def test_the_round_after_a_partial_proposal_is_told_what_it_lost(tmp_path: Path):
    """The regression, end to end, as the designer of round three meets it.

    Round 1 keeps all fifty. Round 2 proposes WRS alone, so ARS and OGS fall
    back to baseline and the crew is lost. Round 3 asks for its artifacts and
    has to be handed the design that worked, the floor it fell under, and the
    instruction to name all three variables next time.
    """
    first = _write_iteration(
        tmp_path, 1, fields=_survivor_fields(), crew_remaining=50, score=66.2
    )
    update_compact_chain_memory(tmp_path, first, iteration=1)
    second = _write_iteration(
        tmp_path, 2, fields={**_baseline_fields(), WRS_KEY: 1.8}, crew_remaining=0, score=25.4
    )
    update_compact_chain_memory(tmp_path, second, iteration=2, applied_capacity_keys=[WRS_KEY])

    third = _write_iteration(tmp_path, 3, fields=_baseline_fields(), crew_remaining=0)
    toolkit = DesignToolkit(
        DesignToolContext(
            run_dir=third,
            scenario_config=yaml.safe_load(
                (third / "scenario_config.yaml").read_text(encoding="utf-8")
            ),
            summary=json.loads((third / "summary.json").read_text(encoding="utf-8")),
            plots_enabled=False,
        )
    )
    memory = toolkit.call("load_run_artifacts", {})["chain_memory_compact"]

    assert memory["best_full_survival"]["iteration"] == 1
    assert memory["best_full_survival"]["fields"] == _survivor_fields()
    assert memory["last_effective_design"]["iteration"] == 2
    assert memory["proposal_guidance"]["prefer_complete_capacity_profile"] is True
    counted = {p["id"]: p["observed_count"] for p in memory["known_bad_patterns"]}
    assert counted[PATTERN_DROPPED_TO_BASELINE] == 1
    assert counted[PATTERN_BELOW_FLOOR] == 1

    # And it reaches the page the decision is actually taken from.
    shown = _state(memory)["chain_memory"]
    assert shown["best_full_survival"]["fields"] == _survivor_fields()
    assert "theoretical_floor" in shown["note"]

# --------------------------------------------------------------------------- #
# noticing that the chain has stopped getting anywhere
# --------------------------------------------------------------------------- #
EXPLORATION = {
    "stagnation_window": 4,
    "min_score_delta": 0.25,
    "require_same_survival_tier": True,
    "cooldown_iterations": 2,
}


def _one_round(
    chain_dir: Path,
    index: int,
    *,
    score: float,
    crew_remaining: int = 50,
    wrs: float = 2.0,
    exploration: Optional[dict] = None,
) -> dict:
    """Run one iteration through the memory and hand back what it now says."""
    run_dir = _write_iteration(
        chain_dir,
        index,
        fields=_survivor_fields(wrs),
        crew_remaining=crew_remaining,
        score=score,
    )
    config = yaml.safe_load((run_dir / "scenario_config.yaml").read_text(encoding="utf-8"))
    config["iteration"] = {
        "exploration": dict(EXPLORATION if exploration is None else exploration)
    }
    (run_dir / "scenario_config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    update_compact_chain_memory(chain_dir, run_dir, iteration=index)
    return load_chain_memory(chain_dir)


def _stall(chain_dir: Path, scores: Sequence[float]) -> dict:
    memory: dict = {}
    for index, score in enumerate(scores, start=1):
        memory = _one_round(chain_dir, index, score=score, wrs=2.0 + index / 100.0)
    return memory


# Climbs, then flattens: each round after the third buys well under a quarter
# of a point, which is what "the same neighbourhood again" looks like on paper.
STALLING = [60.0, 64.0, 65.0, 65.05, 65.10, 65.12, 65.15, 65.18, 65.20, 65.22]


def test_a_chain_that_stops_improving_is_told_to_look_elsewhere(tmp_path: Path):
    memory = _stall(tmp_path, STALLING[:7])

    stagnation = memory["stagnation"]
    assert stagnation["status"] == STAGNATION_ACTIVE
    assert stagnation["survival_tier"] == TIER_FULL
    assert stagnation["window"] == 4
    assert stagnation["iterations"] == [4, 5, 6, 7]
    # Best inside the window against the best reached before it opened.
    assert stagnation["best_score_in_window"] == 65.15
    assert stagnation["best_score_before_window"] == 65.0
    assert stagnation["score_delta"] < 0.25

    directive = memory["exploration_directive"]
    assert directive["mode"] == MODE_DIVERSIFY
    assert directive["avoid_repeating_recent_fields"] is True
    assert directive["preferred_strategies"]
    # Named in full, so a proposal can be checked against them.
    assert all(
        set(fields) == set(_survivor_fields()) for fields in directive["recent_field_sets"]
    )
    assert directive["recent_field_sets"][0][WRS_KEY] == 2.07


def test_a_chain_still_gaining_ground_is_left_alone(tmp_path: Path):
    memory = _stall(tmp_path, [60.0, 62.0, 64.0, 66.0, 68.0, 70.0])
    assert memory["stagnation"]["status"] == STAGNATION_IMPROVING
    assert memory["exploration_directive"] is None


def test_a_round_that_lost_people_is_information_not_a_stall(tmp_path: Path):
    """Scores from different survival tiers were never the same question."""
    memory = _stall(tmp_path, STALLING[:7])
    assert memory["stagnation"]["status"] == STAGNATION_ACTIVE

    # One exploratory round costs four occupants: the window is no longer
    # comparable, and the chain is not told it is going round in circles.
    memory = _one_round(tmp_path, 8, score=62.0, crew_remaining=46, wrs=1.6)
    assert memory["stagnation"]["status"] == STAGNATION_NOT_COMPARABLE
    assert memory["stagnation"]["survival_tier"] is None


def test_the_detector_does_not_fire_again_while_it_is_cooling_down(tmp_path: Path):
    statuses: List[str] = []
    for index, score in enumerate(STALLING, start=1):
        memory = _one_round(tmp_path, index, score=score, wrs=2.0 + index / 100.0)
        statuses.append(memory["stagnation"]["status"])

    fired = [i for i, status in enumerate(statuses, start=1) if status == STAGNATION_ACTIVE]
    # Fires, holds for the two cooldown rounds, then may fire again.
    assert fired == [7, 10]
    assert statuses[7:9] == [STAGNATION_COOLDOWN, STAGNATION_COOLDOWN]


def test_the_directive_stays_up_through_the_cooldown(tmp_path: Path):
    """The cooldown stops the detector re-firing, not the exploring."""
    memory = _stall(tmp_path, STALLING[:8])
    assert memory["stagnation"]["status"] == STAGNATION_COOLDOWN
    assert memory["exploration_directive"]["mode"] == MODE_DIVERSIFY


def test_a_short_chain_says_it_is_still_collecting(tmp_path: Path):
    memory = _one_round(tmp_path, 1, score=60.0)
    assert memory["stagnation"]["status"] == STAGNATION_WARMING_UP
    assert memory["exploration_directive"] is None


def test_the_window_and_the_bar_come_from_the_runs_own_config(tmp_path: Path):
    memory: dict = {}
    for index, score in enumerate([60.0, 65.0, 65.05, 65.1], start=1):
        memory = _one_round(
            tmp_path,
            index,
            score=score,
            wrs=2.0 + index / 100.0,
            exploration={**EXPLORATION, "stagnation_window": 2, "min_score_delta": 1.0},
        )
    assert memory["stagnation"]["window"] == 2
    assert memory["stagnation"]["min_score_delta"] == 1.0
    assert memory["stagnation"]["status"] == STAGNATION_ACTIVE


def test_a_missing_exploration_block_falls_back_to_the_defaults():
    assert exploration_settings(None)["stagnation_window"] == DEFAULT_STAGNATION_WINDOW
    assert exploration_settings({})["min_score_delta"] == DEFAULT_MIN_SCORE_DELTA
    # A nonsense window is not honoured; an explicit zero cooldown is.
    nonsense = {"iteration": {"exploration": {"stagnation_window": 0}}}
    assert exploration_settings(nonsense)["stagnation_window"] == DEFAULT_STAGNATION_WINDOW
    eager = {"iteration": {"exploration": {"cooldown_iterations": 0}}}
    assert exploration_settings(eager)["cooldown_iterations"] == 0


def test_survival_tier_names_the_three_answers():
    assert survival_tier(50, 50) == TIER_FULL
    assert survival_tier(46, 50) == TIER_PARTIAL
    assert survival_tier(0, 50) == TIER_ZERO
    assert survival_tier(None, 50) is None
    assert survival_tier(0, 0) is None


def test_a_stalled_chain_still_fits_the_context_budget(tmp_path: Path):
    """Directive, failures and bookkeeping all at once, over a long chain."""
    for index in range(1, 41):
        crew = 50 if index % 7 else 0
        _one_round(tmp_path, index, score=65.0 + index / 100.0, crew_remaining=crew, wrs=2.0)
    path = tmp_path / CHAIN_MEMORY_FILENAME
    assert path.stat().st_size <= MAX_MEMORY_BYTES
    memory = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(memory["best_full_survival"], dict)
    assert isinstance(memory["last_effective_design"], dict)


def test_the_decision_page_carries_the_directive_but_not_the_bookkeeping(tmp_path: Path):
    memory = _stall(tmp_path, STALLING[:7])

    shown = _state(memory)["chain_memory"]
    assert shown["exploration_directive"]["mode"] == MODE_DIVERSIFY
    assert shown["exploration_directive"]["recent_field_sets"]
    # The detector's own ledger is not advice and does not go in front of the model.
    assert "recent_points" not in shown
    assert "best_score_before_window" not in shown
    assert "cooldown_until" not in shown
    assert "exploration_directive" in shown["note"]
