"""The note one iteration of a design chain leaves for the next one.

The failure this exists to prevent is concrete: a round that kept every
occupant alive is followed by a partial proposal, the omitted subsystems fall
back to their baseline sizes, and the next run loses the whole crew. Nothing in
the chain notices, because no iteration reads any run but its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scenario.ssos_eclss_loop.chain_memory import (
    ARS_KEY,
    CHAIN_MEMORY_FILENAME,
    MAX_MEMORY_BYTES,
    OGS_KEY,
    PATTERN_BELOW_FLOOR,
    PATTERN_DROPPED_TO_BASELINE,
    WRS_KEY,
    capacity_keys_in_document,
    load_chain_memory,
    theoretical_floor_from_trace,
    update_compact_chain_memory,
)
from scenario.ssos_eclss_loop.design_state import build_design_state
from scenario.ssos_eclss_loop.design_tools import DesignToolContext, DesignToolkit
from scenario.ssos_eclss_loop.design_variables import BASELINE_CAPACITY

FLOOR = {ARS_KEY: 20.8, OGS_KEY: 42.0, WRS_KEY: 1.5625}


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
    assert len(patterns) == 1
    assert patterns[0]["observed_count"] == 3


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


# --------------------------------------------------------------------------- #
# the pieces it is built from
# --------------------------------------------------------------------------- #
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
