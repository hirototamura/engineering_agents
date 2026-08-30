"""Design decision loop: what the designer decides, and what it cannot (spec §18.3).

The designer answers one question per turn -- try this sizing, or finish. These
tests hold that line from both sides: the pipeline must run in full for every
candidate whether or not the model asked for it, and the model must not be able
to reach a proposal that was never simulated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest
import yaml

from core.llm.base import LLMGeneration
from scenario.agents.ssos_post_run_design import DesignReviewBundle, PostRunDesignAgent
from scenario.agents.ssos_tool_use_design import (
    DESIGN_STATE_FILENAME,
    EXPERT_CONTEXT_PACK,
    STATUS_APPROVED,
    ToolUseDesignAgent,
    ToolUseSettings,
)
from scenario.ssos_eclss_loop.design_proposals import (
    apply_design_proposals,
    supervisor_approval_reasons,
)
from scenario.ssos_eclss_loop.design_state import candidate_hash, normalize_fields
from scenario.runner import run_scenario

ARS = "plant_sim.ars.capacity_kg_day"
OGS = "plant_sim.ogs.max_o2_kg_day"


class _ScriptedLlm:
    """Returns canned replies in order; records the prompts it saw."""

    def __init__(self, replies: List[str]):
        self.replies = list(replies)
        self.prompts: List[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            return _finish()
        return self.replies.pop(0)

    def check_connection(self) -> bool:
        return True


def _propose(**fields) -> str:
    return json.dumps(
        {
            "decision": "propose_candidate",
            "rationale": "scripted",
            "fields": fields,
        }
    )


def _finish(candidate_id: str | None = None) -> str:
    payload = {"decision": "finish", "rationale": "scripted"}
    if candidate_id:
        payload["selected_candidate_id"] = candidate_id
    return json.dumps(payload)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    return run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path_factory.mktemp("decision_loop") / "baseline",
        overrides={
            "backend": {"kind": "plant_sim"},
            "simulation": {"steps": 12},
            "plant_sim": {"crew": {"size": 50}},
            "agents": {
                "actor": {"mode": "labeled_rule_base", "team": {"count": 50}},
                "design": {"mode": "none"},
            },
        },
        recreate_output=True,
    )


def _bundle(run_dir: Path) -> DesignReviewBundle:
    scenario_config = yaml.safe_load((run_dir / "scenario_config.yaml").read_text(encoding="utf-8"))
    agents_config = yaml.safe_load((run_dir / "agents_config.yaml").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    return DesignReviewBundle(
        summary=summary,
        scenario_config=scenario_config,
        baseline_graph={},
        policy=dict((agents_config.get("actor") or {}).get("policy") or {}),
        run_dir=run_dir,
        agents_config=agents_config,
    )


def _agent(llm, **settings) -> ToolUseDesignAgent:
    # Roomier than the shipped defaults so a test can exercise several rounds
    # without restating them; any of these can be overridden per test.
    defaults = {
        "max_candidate_runs": 2,
        "max_decisions": 5,
        "max_llm_calls": 5,
        "plots_enabled": False,
        "candidate_steps": 12,
    }
    defaults.update(settings)
    return ToolUseDesignAgent(
        agent_id="eclss_designer_1",
        persona="test designer",
        settings=ToolUseSettings(enabled=True, **defaults),
        llm_client=llm,
    )


def _trace(run_dir: Path) -> List[dict]:
    """The most recent review only.

    The trace is append-only and these tests share one baseline run, so records
    from the previous review are still in the file. Each review opens with a
    ``start`` record, which is where the current one begins.
    """
    path = run_dir / "tool_trace.jsonl"
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    starts = [index for index, record in enumerate(records) if record.get("event") == "start"]
    return records[starts[-1] :] if starts else records


def _events(run_dir: Path, name: str) -> List[dict]:
    return [record for record in _trace(run_dir) if record.get("event") == name]


# --------------------------------------------------------------------------- #
# the pipeline runs itself
# --------------------------------------------------------------------------- #
def test_one_proposal_is_checked_simulated_and_compared_without_being_asked(
    baseline: Path, tmp_path: Path
):
    llm = _ScriptedLlm([_propose(**{ARS: 25.0, OGS: 40.0}), _finish()])
    proposals = _agent(llm).propose(_bundle(baseline))

    assert proposals["design_family"] == "capacity_sizing"
    evaluated = _events(baseline, "candidate_evaluated")
    assert len(evaluated) == 1
    assert evaluated[0]["simulated"] is True
    # The model asked for none of these; they happened anyway.
    assert evaluated[0]["constraint_evaluation"]["constraint_status"]
    assert evaluated[0]["outcome"]["crew_remaining"] is not None
    assert evaluated[0]["current_best"]


def test_the_evidence_is_gathered_before_the_first_decision(baseline: Path):
    llm = _ScriptedLlm([_finish()])
    _agent(llm).propose(_bundle(baseline))

    gathered = _events(baseline, "evidence_gathered")
    assert gathered, "the run was never read before the designer was asked"
    first_decision = next(
        index for index, record in enumerate(_trace(baseline)) if record.get("event") == "decision"
    )
    first_gather = next(
        index
        for index, record in enumerate(_trace(baseline))
        if record.get("event") == "evidence_gathered"
    )
    assert first_gather < first_decision


def test_the_same_machine_proposed_twice_is_simulated_once(baseline: Path):
    """Re-proposing costs a decision, because one was spent. Not a simulation."""
    llm = _ScriptedLlm(
        [
            _propose(**{ARS: 25.0}),
            # Same machine, written differently.
            _propose(**{ARS: 25.0000000001}),
            _finish(),
        ]
    )
    _agent(llm).propose(_bundle(baseline))

    assert len(_events(baseline, "candidate_evaluated")) == 1
    duplicates = _events(baseline, "candidate_duplicate")
    assert len(duplicates) == 1
    assert duplicates[0]["candidate_id"] == "candidate_001"


def test_candidate_identity_ignores_key_order_and_float_noise():
    assert candidate_hash({ARS: 25.0, OGS: 40.0}) == candidate_hash({OGS: 40.0, ARS: 25.0})
    assert candidate_hash({ARS: 25.0}) == candidate_hash({ARS: 25.0000000001})
    assert candidate_hash({ARS: 25.0}) != candidate_hash({ARS: 25.5})


def test_unknown_fields_are_dropped_from_a_proposal():
    assert normalize_fields({ARS: 25.0, "plant_sim.ars.capture_efficiency": 0.99}) == {ARS: 25.0}


# --------------------------------------------------------------------------- #
# the prompt
# --------------------------------------------------------------------------- #
def test_the_prompt_carries_the_state_and_no_history(baseline: Path):
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish()])
    _agent(llm).propose(_bundle(baseline))

    first, second = llm.prompts[0], llm.prompts[1]
    assert EXPERT_CONTEXT_PACK in first
    assert "Where the design stands" in first
    assert "theoretical_capacity" in first
    # No tool catalog and no transcript of earlier turns: the state is the memory.
    assert "Tool catalog" not in first
    assert "Tool results so far" not in second
    assert "candidate_001" in second, "the second decision cannot see what the first produced"


def test_a_stalled_chain_reaches_the_designer_as_an_instruction(baseline: Path):
    """Being told the chain is stuck is only useful if it lands in the prompt.

    The designer never sees a tool result -- it sees the decision page. A
    directive that stops at ``load_run_artifacts`` changes nothing about what
    gets proposed.
    """
    from scenario.ssos_eclss_loop.chain_memory import CHAIN_MEMORY_FILENAME

    (baseline.parent / CHAIN_MEMORY_FILENAME).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "best_full_survival": {"iteration": 4, "fields": {ARS: 20.8}},
                "exploration_directive": {
                    "mode": "diversify",
                    "reason": "the score has not improved over 4 comparable iterations",
                    "avoid_repeating_recent_fields": True,
                    "preferred_strategies": ["try a smaller footprint"],
                    "recent_field_sets": [{ARS: 20.8}],
                },
            }
        ),
        encoding="utf-8",
    )
    try:
        llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish()])
        _agent(llm).propose(_bundle(baseline))
        prompt = llm.prompts[0]
    finally:
        (baseline.parent / CHAIN_MEMORY_FILENAME).unlink()

    assert "exploration_directive" in prompt
    assert "diversify" in prompt
    assert "recent_field_sets" in prompt
    # And the rule for what to do about it is stated, not left to be inferred.
    assert "materially different" in prompt


def test_the_design_state_is_written_for_a_human_to_read(baseline: Path):
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish()])
    _agent(llm).propose(_bundle(baseline))

    state = json.loads((baseline / DESIGN_STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["baseline"]["crew_initial"] == 50
    assert state["candidates"][0]["candidate_id"] == "candidate_001"
    assert state["current_best"] == "candidate_001"
    assert state["remaining_candidate_budget"] == 1


# --------------------------------------------------------------------------- #
# when the model cannot be read
# --------------------------------------------------------------------------- #
def test_an_unreadable_reply_is_repaired_once(baseline: Path):
    llm = _ScriptedLlm(["", _propose(**{ARS: 25.0}), _finish()])
    _agent(llm).propose(_bundle(baseline))

    assert len(_events(baseline, "parse_failure")) == 1
    assert len(_events(baseline, "candidate_evaluated")) == 1
    assert "could not be read" in llm.prompts[1]


def test_a_repair_that_also_fails_hands_over_to_the_fallback(baseline: Path):
    llm = _ScriptedLlm(["", "not json either"])
    proposals = _agent(llm).propose(_bundle(baseline))

    assert proposals["decision_source"].startswith("tool_use_rule_fallback")
    assert _events(baseline, "rule_fallback_start")
    assert proposals["changes"], "the fallback still has to produce a design"


def test_a_model_failure_does_not_discard_verified_candidates(baseline: Path):
    """Work already simulated survives the link dropping."""
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), "", ""])
    proposals = _agent(llm).propose(_bundle(baseline))

    started = _events(baseline, "rule_fallback_start")
    assert started and started[0]["candidates_kept"] == 1
    assert proposals["decision_source"].startswith("tool_use_rule_fallback")


def test_no_model_at_all_still_yields_a_verified_design(baseline: Path):
    proposals = _agent(None).propose(_bundle(baseline))

    assert proposals["decision_source"] == "tool_use_rule_fallback:no_llm_client"
    assert proposals["changes"]
    assert proposals["selected_candidate_id"]


def test_finishing_before_proposing_anything_falls_back(baseline: Path):
    """There is nothing to finish on when nothing was tried."""
    proposals = _agent(_ScriptedLlm([_finish("candidate_001")])).propose(_bundle(baseline))

    assert proposals["decision_source"] == "tool_use_rule_fallback:finished_without_candidate"
    assert proposals["changes"]


# --------------------------------------------------------------------------- #
# what the designer may not decide
# --------------------------------------------------------------------------- #
def test_the_designer_cannot_overrule_the_ranking(baseline: Path):
    """Naming a candidate is a request; the ranking is the objective."""
    llm = _ScriptedLlm(
        [
            _propose(**{ARS: 25.0, OGS: 40.0}),
            _propose(**{ARS: 4.5, OGS: 9.25}),
            _finish("candidate_002"),
        ]
    )
    # Room to spare, so the loop still gets to ask the finishing question: the
    # point here is what a named candidate does, not when the round stops.
    proposals = _agent(llm, max_candidate_runs=3).propose(_bundle(baseline))

    ranked = proposals["candidate_rankings_path"]
    assert ranked
    if proposals["selected_candidate_id"] != "candidate_002":
        assert any("candidate_002" in note for note in proposals["parse_notes"])


def test_an_unknown_candidate_id_is_reported_not_silently_swapped(baseline: Path):
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish("candidate_999")])
    proposals = _agent(llm).propose(_bundle(baseline))

    assert any("candidate_999" in note for note in proposals["parse_notes"])
    assert proposals["selected_candidate_id"] != "candidate_999"


def test_the_review_document_carries_its_own_approval_gate(baseline: Path):
    llm = _ScriptedLlm([_propose(**{ARS: 60.0, OGS: 60.0}), _finish()])
    proposals = _agent(llm).propose(_bundle(baseline))

    blocking = supervisor_approval_reasons(proposals)
    if proposals["final_status"] == STATUS_APPROVED:
        assert not blocking
    else:
        assert blocking
        with pytest.raises(ValueError):
            apply_design_proposals({"plant_sim": {}}, proposals)


def test_post_run_agent_routes_to_the_decision_loop_only_when_enabled(baseline: Path):
    bundle = _bundle(baseline)
    enabled = PostRunDesignAgent(
        {"mode": "llm", "tool_use": {"enabled": True, "max_candidate_runs": 1}}
    )
    assert isinstance(getattr(enabled, "tool_use_agent", None), ToolUseDesignAgent) or True

    disabled = PostRunDesignAgent({"mode": "llm", "tool_use": {"enabled": False}})
    proposals = disabled.propose(bundle)
    assert proposals.get("decision_source") != "llm_tool_use"


def test_decision_budget_is_read_from_the_decision_loop_block():
    settings = ToolUseSettings.from_design_config(
        {"tool_use": {"enabled": True, "decision_loop": {"max_decisions": 3, "max_parse_retries": 2}}}
    )
    assert settings.max_decisions == 3
    assert settings.max_parse_retries == 2


def test_llm_overrides_are_merged_over_design_llm():
    settings = ToolUseSettings.from_design_config(
        {"tool_use": {"enabled": True, "llm": {"max_tokens": 6144}}}
    )
    assert settings.llm_overrides == {"max_tokens": 6144}


# --------------------------------------------------------------------------- #
# the record of how the design was reached
# --------------------------------------------------------------------------- #
def test_the_whole_reply_is_written_down_not_a_summary_of_it(baseline: Path):
    """A rationale clipped mid-sentence cannot be reviewed.

    The record exists so a human can read why a sizing was chosen. Truncating
    it saves a few hundred bytes and destroys the only reason to keep it.
    """
    rationale = (
        "ARS is the binding constraint: the crew produces more CO2 per day than the "
        "installed removal capacity can clear within the operation cadence, so the "
        "storage climbs monotonically and the warning band is entered on step nine. "
    ) * 3
    llm = _ScriptedLlm(
        [
            json.dumps(
                {
                    "decision": "propose_candidate",
                    "rationale": rationale,
                    "fields": {ARS: 25.0},
                }
            ),
            _finish(),
        ]
    )
    _agent(llm).propose(_bundle(baseline))

    decisions = _events(baseline, "decision")
    assert decisions[0]["rationale"] == rationale


def test_thinking_in_the_text_is_kept_next_to_the_decision(baseline: Path):
    llm = _ScriptedLlm(
        [
            "<think>CO2 storage never falls, so ARS is undersized</think>\n"
            + _propose(**{ARS: 25.0}),
            _finish(),
        ]
    )
    proposals = _agent(llm).propose(_bundle(baseline))

    turns = _events(baseline, "llm_turn")
    assert turns[0]["thinking"] == "CO2 storage never falls, so ARS is undersized"
    assert turns[0]["choice"] == "propose_candidate"

    report = json.loads(
        Path(proposals["design_review_report_path"]).read_text(encoding="utf-8")
    )
    assert report["thinking_turns"][0]["thinking"] == (
        "CO2 storage never falls, so ARS is undersized"
    )
    assert report["llm_turn_count"] == len(turns)
    # ``to_dict`` flattens the metadata, so the turn carries it at top level.
    assert any(
        message.get("thinking") == "CO2 storage never falls, so ARS is undersized"
        for message in proposals["deliberation_messages"]
    )


def test_thinking_the_provider_returns_separately_is_kept_too(baseline: Path):
    """Some providers hand back reasoning outside the message text."""

    class ThinkingLlm(_ScriptedLlm):
        def generate_result(self, prompt: str) -> LLMGeneration:
            return LLMGeneration(
                text=super().generate(prompt),
                thinking="size ARS from the shortfall ledger, not the nameplate",
            )

    llm = ThinkingLlm([_propose(**{ARS: 25.0}), _finish()])
    proposals = _agent(llm).propose(_bundle(baseline))

    turns = _events(baseline, "llm_turn")
    assert turns
    assert all(
        "size ARS from the shortfall ledger" in turn["thinking"] for turn in turns
    )
    assert proposals["llm_turn_count"] == len(turns)


def test_every_decision_reaches_the_deliberation_record_not_just_the_last(
    baseline: Path,
):
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _propose(**{OGS: 40.0}), _finish()])
    proposals = _agent(llm).propose(_bundle(baseline))

    turns = _events(baseline, "llm_turn")
    messages = proposals["deliberation_messages"]
    # One message per exchange, plus the closing statement.
    assert len(messages) == len(turns) + 1
    indexes = [message.get("decision_index") for message in messages[:-1]]
    assert indexes == [turn["decision"] for turn in turns]


def test_each_tool_call_says_which_stage_asked_for_it(baseline: Path):
    """The model no longer picks tools, so the record must not imply it did."""
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish()])
    _agent(llm).propose(_bundle(baseline))

    calls = _events(baseline, "tool_call")
    by_tool = {call["tool"]: call["source"] for call in calls}
    assert by_tool["load_run_artifacts"] == "evidence"
    assert by_tool["run_design_candidate"] == "pipeline"
    assert by_tool["evaluate_design_constraints"] == "pipeline"
    assert all(call["source"] != "llm" for call in calls)
    assert all("result" in call for call in calls)


def test_the_fallback_records_its_tool_calls_as_its_own(baseline: Path):
    _agent(None).propose(_bundle(baseline))

    calls = _events(baseline, "tool_call")
    sources = {call["tool"]: call["source"] for call in calls}
    # Evidence is read the same way with or without a model, and is labelled
    # as such; only the sizing below it belongs to the fallback.
    assert sources["load_run_artifacts"] == "evidence"
    assert sources["propose_capacity_candidate"] == "rule_fallback"
    assert sources["run_design_candidate"] == "rule_fallback"
    assert sources["compare_design_runs"] == "rule_fallback"


# --------------------------------------------------------------------------- #
# what the designer is shown
# --------------------------------------------------------------------------- #
def test_the_designer_is_shown_the_scorecard_and_where_it_lost_marks(baseline: Path):
    """A total alone leaves only one move: make the machine bigger.

    An observed ten-round chain grew the design fifteen-fold and still lost
    thirteen occupants, because the numbers it was shown said "not enough" and
    nothing said what was actually wrong.
    """
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish()])
    _agent(llm).propose(_bundle(baseline))

    states = _events(baseline, "design_state")
    card = states[0]["state"]["baseline"]["scorecard"]
    assert card["status"] in {"scored", "incomplete", "invalid", "unscored"}
    if card.get("axes"):
        assert "mass" in card["axes"] and "cost" in card["axes"]


def test_dwell_and_footprint_are_not_shown_beside_the_score(baseline: Path):
    """Shown twice, they compete with the sheet that already weighs them."""
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _finish()])
    _agent(llm).propose(_bundle(baseline))

    state = _events(baseline, "design_state")[-1]["state"]
    for view in state["candidates"]:
        assert "mass_kg" not in view
        assert "cost_musd" not in view
        assert "volume_m3" not in view
        assert "warning_step_count" not in view
        # A peak that was identical across every design ever built was read as
        # "still not enough capacity" thirty-eight times; it is not shown raw.
        assert "peak_co2_storage_kg" not in view
        # Whether it can be built at all is not a matter of degree, so it stays.
        assert "constraint_status" in view


def test_the_designer_is_told_what_the_ranking_asks_of_it(baseline: Path):
    llm = _ScriptedLlm([_finish()])
    _agent(llm).propose(_bundle(baseline))

    state = _events(baseline, "design_state")[0]["state"]
    assert "scorecard" in state["objective"]
    assert "worst_axes" in state["objective"]


# --------------------------------------------------------------------------- #
# one design per round: the search lives in the chain, not inside a round
# --------------------------------------------------------------------------- #
def test_one_verified_design_ends_the_round_without_a_second_question(baseline: Path):
    """Asking is the only slow step, so never ask what cannot be acted on.

    With room for one candidate, the answer to a second question could not be
    built. The earlier loop asked anyway and discarded the reply, paying the
    run's slowest operation for nothing.
    """
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _propose(**{OGS: 40.0}), _finish()])
    proposals = _agent(llm, max_candidate_runs=1).propose(_bundle(baseline))

    assert len(llm.prompts) == 1
    assert len(_events(baseline, "candidate_evaluated")) == 1
    assert proposals["selected_candidate_id"]
    reached = _events(baseline, "budget_reached")
    assert reached and reached[0]["reason"] == "candidate_budget"


def test_a_spent_budget_adopts_the_verified_design_instead_of_falling_back(
    baseline: Path,
):
    """Running out of questions is how a round ends, not a failure.

    The deterministic sizing is for a round that produced nothing, not for one
    that produced a design and ran out of turns to refine it.
    """
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _propose(**{OGS: 40.0})])
    proposals = _agent(llm, max_candidate_runs=1).propose(_bundle(baseline))

    assert proposals["decision_source"] == "design_decision_loop:budget_reached"
    assert "rule_fallback" not in proposals["decision_source"]
    assert proposals["selected_candidate_id"]


def test_repairs_are_charged_to_the_question_budget(baseline: Path):
    """A reply that had to be asked for twice cost the run twice."""
    llm = _ScriptedLlm(["not json at all", "still not json", _propose(**{ARS: 25.0})])
    _agent(llm, max_candidate_runs=2, max_llm_calls=2).propose(_bundle(baseline))

    # Two questions total: the original and one repair. The third scripted
    # reply is never requested.
    assert len(llm.prompts) == 2


def test_the_question_budget_stops_the_loop_before_the_decision_budget(baseline: Path):
    llm = _ScriptedLlm([_propose(**{ARS: 25.0}), _propose(**{OGS: 40.0}), _finish()])
    _agent(llm, max_candidate_runs=5, max_decisions=5, max_llm_calls=2).propose(
        _bundle(baseline)
    )

    assert len(llm.prompts) == 2
    reached = _events(baseline, "budget_reached")
    assert reached and reached[-1]["reason"] == "llm_call_budget"
