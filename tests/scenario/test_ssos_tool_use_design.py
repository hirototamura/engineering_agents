"""Tool-use design agent: planning loop, Evidence Gate, fallback (design doc §10)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List

import pytest
import yaml

from core.llm.base import LLMGeneration

from scenario.agents.ssos_post_run_design import DesignReviewBundle, PostRunDesignAgent
from scenario.agents.ssos_tool_use_design import (
    EXPERT_CONTEXT_PACK,
    STATUS_APPROVED,
    ToolUseDesignAgent,
    ToolUseSettings,
)
from scenario.ssos_eclss_loop.design_proposals import (
    apply_design_proposals,
    supervisor_approval_reasons,
)
from scenario.runner import run_scenario


class _ScriptedLlm:
    """Returns canned JSON replies in order; records the prompts it saw."""

    def __init__(self, replies: List[str]):
        self.replies = list(replies)
        self.prompts: List[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.replies:
            return json.dumps({"message": "done", "reasoning": "no more scripted replies"})
        return self.replies.pop(0)

    def check_connection(self) -> bool:
        return True


def _tool(name: str, arguments: dict | None = None, message: str = "next step") -> str:
    return json.dumps(
        {
            "message": message,
            "reasoning": "scripted",
            "task_plan": ["read", "compute", "verify"],
            "tool_call": {"name": name, "arguments": arguments or {}},
        }
    )


def _final(candidate_id: str | None = None) -> str:
    payload = {
        "message": "final recommendation",
        "reasoning": "verified by re-simulation",
        "final_proposal": {
            "changes": [
                {
                    "change_kind": "capacity_profile",
                    "payload": {"backend": "plant_sim", "fields": {}},
                }
            ],
            "expected_outcome": {},
            "constraint_evaluation": {},
        },
    }
    if candidate_id:
        payload["final_proposal"]["candidate_id"] = candidate_id
    return json.dumps(payload)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    return run_scenario(
        "ssos_eclss_loop",
        output_dir=tmp_path_factory.mktemp("tool_use") / "baseline",
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


def _load_jsonl(path: Path) -> List[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fresh_bundle(baseline: Path, tmp_path: Path) -> DesignReviewBundle:
    dest = tmp_path / "run"
    shutil.copytree(baseline, dest)
    for name in (
        "tool_trace.jsonl",
        "design_review_report.json",
        "candidate_rankings.json",
        "design_proposals.json",
    ):
        leftover = dest / name
        if leftover.exists():
            leftover.unlink()
    return _bundle(dest)


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
    return ToolUseDesignAgent(
        agent_id="eclss_designer_1",
        persona="test designer",
        settings=ToolUseSettings(
            enabled=True,
            max_candidate_runs=2,
            plots_enabled=False,
            candidate_steps=12,
            **settings,
        ),
        llm_client=llm,
    )


def _happy_path_replies(margin: float = 1.2) -> List[str]:
    return [
        _tool("load_run_artifacts"),
        _tool("summarize_timeseries", {"source": "telemetry"}),
        _tool("compute_theoretical_capacity"),
        _tool("propose_capacity_candidate", {"margin": margin}),
        _tool("evaluate_design_constraints", {"fields": {"plant_sim.ars.capacity_kg_day": 25.0}}),
        _tool("run_design_candidate", {"fields": {"plant_sim.ars.capacity_kg_day": 25.0}}),
        _tool("compare_design_runs"),
        _final(),
    ]


def test_agent_walks_the_tools_and_emits_a_verified_proposal(baseline: Path, tmp_path: Path):
    llm = _ScriptedLlm(_happy_path_replies())
    proposals = _agent(llm).propose(_bundle(baseline))

    assert proposals["decision_source"] == "llm_tool_use"
    assert proposals["design_family"] == "capacity_sizing"
    assert len(proposals["changes"]) == 1
    change = proposals["changes"][0]
    assert change["change_kind"] == "capacity_profile"
    assert change["payload"]["backend"] == "plant_sim"
    # the adopted fields come from the candidate that was actually simulated,
    # not from whatever the model typed in its final message
    assert change["payload"]["fields"] == {"plant_sim.ars.capacity_kg_day": 25.0}
    assert change["candidate_id"] == proposals["selected_candidate_id"]
    assert proposals["expected_outcome"]["crew_remaining"] is not None

    for path_key in ("tool_trace_path", "candidate_rankings_path", "design_review_report_path"):
        assert Path(proposals[path_key]).exists()
    assert proposals["evidence"]["missing"] == []


def test_prompt_carries_the_expert_context_pack_and_the_catalog(baseline: Path):
    llm = _ScriptedLlm(_happy_path_replies())
    _agent(llm).propose(_bundle(baseline))
    first_prompt = llm.prompts[0]
    assert EXPERT_CONTEXT_PACK.splitlines()[1] in first_prompt
    assert "run_design_candidate" in first_prompt
    assert "one tool_call per turn" in first_prompt
    # the model is not handed the whole run up front
    assert "telemetry.jsonl" not in first_prompt


def test_evidence_gate_rejects_an_unbacked_final_proposal(baseline: Path):
    llm = _ScriptedLlm(
        [
            _tool("load_run_artifacts"),
            _final(),  # far too early: no theory, no candidate, no comparison
            *_happy_path_replies()[1:],
        ]
    )
    proposals = _agent(llm).propose(_bundle(baseline))

    trace = [
        json.loads(line)
        for line in Path(proposals["tool_trace_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rejects = [rec for rec in trace if rec["event"] == "evidence_gate_reject"]
    assert len(rejects) == 1
    assert "computed_theoretical_capacity" in rejects[0]["missing_evidence"]
    assert "ran_candidate" in rejects[0]["missing_evidence"]
    # the loop continued and still reached a verified proposal
    assert proposals["decision_source"] == "llm_tool_use"
    assert proposals["changes"]
    # the gate told the model what was missing
    assert any("Evidence Gate rejected" in prompt for prompt in llm.prompts)


def test_unknown_tool_is_rejected_and_the_loop_retries(baseline: Path):
    llm = _ScriptedLlm([_tool("delete_everything"), *_happy_path_replies()])
    proposals = _agent(llm).propose(_bundle(baseline))
    trace = [
        json.loads(line)
        for line in Path(proposals["tool_trace_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [rec["requested"] for rec in trace if rec["event"] == "unknown_tool"] == [
        "delete_everything"
    ]
    assert proposals["changes"]


def test_unparsable_replies_fall_back_to_the_deterministic_designer(baseline: Path):
    llm = _ScriptedLlm(["not json at all", "still not json", "<think>nope"])
    proposals = _agent(llm).propose(_bundle(baseline))
    assert proposals["decision_source"] == "tool_use_rule_fallback:repeated_parse_failure"
    assert proposals["changes"], "the fallback must still deliver a sized design"
    assert proposals["selected_candidate_id"] is not None


def test_max_iterations_falls_back_and_still_verifies(baseline: Path):
    llm = _ScriptedLlm([_tool("load_run_artifacts")] * 3)
    proposals = _agent(llm, max_tool_iterations=3).propose(_bundle(baseline))
    assert proposals["decision_source"] == "tool_use_rule_fallback:max_iterations"
    assert proposals["changes"]
    report = json.loads(Path(proposals["design_review_report_path"]).read_text(encoding="utf-8"))
    assert report["candidates"], "fallback ran and ranked candidates"
    assert report["evidence"]["missing"] == []


def test_no_llm_client_uses_the_fallback(baseline: Path):
    proposals = _agent(None).propose(_bundle(baseline))
    assert proposals["decision_source"] == "tool_use_rule_fallback:no_llm_client"
    assert proposals["changes"]


def test_a_real_review_document_carries_its_own_approval_gate(baseline: Path):
    """End to end: what the designer writes is what --apply-proposals judges."""
    bundle = _bundle(baseline)
    proposals = _agent(None).propose(bundle)
    blocking = supervisor_approval_reasons(proposals)

    if proposals["final_status"] == STATUS_APPROVED:
        assert blocking == []
        merged = apply_design_proposals(bundle.scenario_config, proposals)
        assert merged["plant_sim"]["ars"]["capacity_kg_day"] > 0
        return

    assert blocking, "a provisional design must not slip through the apply path"
    assert proposals["selection_reason"]
    with pytest.raises(ValueError, match="requires supervisor approval"):
        apply_design_proposals(bundle.scenario_config, proposals)
    # ... and a human can still take it on purpose
    merged = apply_design_proposals(
        bundle.scenario_config, proposals, approve_provisional=True
    )
    fields = proposals["changes"][0]["payload"]["fields"]
    assert merged["plant_sim"]["ars"]["capacity_kg_day"] == fields[
        "plant_sim.ars.capacity_kg_day"
    ]


def test_the_designer_cannot_overrule_the_ranking(baseline: Path):
    """Rank 1 is the calmest then smallest design that saves everyone; a named runner-up is not.

    The designer steers which candidates get built and simulated. Which verified
    candidate is adopted is the objective's call, not the model's.
    """
    llm = _ScriptedLlm(
        [
            _tool("load_run_artifacts"),
            _tool("summarize_timeseries", {"source": "telemetry"}),
            _tool("compute_theoretical_capacity"),
            _tool("propose_capacity_candidate", {"margin": 1.2}),
            _tool(
                "evaluate_design_constraints",
                {"fields": {"plant_sim.ars.capacity_kg_day": 25.0}},
            ),
            _tool("run_design_candidate", {"fields": {"plant_sim.ars.capacity_kg_day": 25.0}}),
            _tool("run_design_candidate", {"fields": {"plant_sim.ars.capacity_kg_day": 30.0}}),
            _tool("compare_design_runs"),
            _final("candidate_002"),
        ]
    )
    proposals = _agent(llm).propose(_bundle(baseline))
    rankings = json.loads(Path(proposals["candidate_rankings_path"]).read_text(encoding="utf-8"))
    assert len(rankings["ranking"]) == 2
    rank_one = next(row for row in rankings["ranking"] if row["rank"] == 1)
    assert proposals["selected_candidate_id"] == rank_one["candidate_id"]
    if rank_one["candidate_id"] != "candidate_002":
        assert any("candidate_002" in note for note in proposals["parse_notes"])


def test_post_run_agent_routes_to_tool_use_only_when_enabled(baseline: Path, monkeypatch):
    monkeypatch.setattr(
        PostRunDesignAgent,
        "_build_llm_client",
        staticmethod(lambda cfg: _ScriptedLlm(_happy_path_replies())),
    )
    tool_use_cfg = {
        "mode": "llm",
        "team": {"count": 1, "id_prefix": "eclss_designer"},
        "llm": {},
        "tool_use": {
            "enabled": True,
            "max_candidate_runs": 1,
            "plots_enabled": False,
            "candidate_steps": 12,
        },
    }
    proposals = PostRunDesignAgent(tool_use_cfg).propose(_bundle(baseline))
    assert proposals["decision_source"] == "llm_tool_use"
    assert proposals["changes"][0]["change_kind"] == "capacity_profile"

    classic_cfg = {**tool_use_cfg, "tool_use": {"enabled": False}}
    classic = PostRunDesignAgent(classic_cfg).propose(_bundle(baseline))
    assert classic["decision_source"] in {"llm", "llm_parse_fail"}
    assert "design_family" not in classic


def test_tool_loop_llm_overrides_are_merged_over_design_llm(baseline: Path, monkeypatch):
    """The loop may run on a smaller completion budget than the classic designer."""
    seen: List[dict] = []

    def _capture(cfg):
        seen.append(dict(cfg))
        return _ScriptedLlm(_happy_path_replies())

    monkeypatch.setattr(PostRunDesignAgent, "_build_llm_client", staticmethod(_capture))
    PostRunDesignAgent(
        {
            "mode": "llm",
            "team": {"count": 1, "id_prefix": "eclss_designer"},
            "llm": {"provider": "vllm", "max_tokens": 16384, "think": True},
            "tool_use": {
                "enabled": True,
                "max_candidate_runs": 1,
                "plots_enabled": False,
                "candidate_steps": 12,
                "llm": {"max_tokens": 4096},
            },
        }
    ).propose(_bundle(baseline))

    assert seen[0]["max_tokens"] == 16384  # designer default, built in __init__
    assert seen[1]["max_tokens"] == 4096  # tool loop override
    assert seen[1]["think"] is True  # everything else is inherited


def test_selecting_the_ranked_candidate_by_name_adds_no_note(baseline: Path):
    """Naming rank 1 is agreement, not a disagreement worth recording."""
    llm = _ScriptedLlm([*_happy_path_replies()[:-1], _final("candidate_001")])
    proposals = _agent(llm).propose(_bundle(baseline))
    assert proposals["selected_candidate_id"] == "candidate_001"
    assert proposals["parse_notes"] == []


def test_unknown_candidate_id_is_reported_not_silently_swapped(baseline: Path):
    llm = _ScriptedLlm([*_happy_path_replies()[:-1], _final("candidate_999")])
    proposals = _agent(llm).propose(_bundle(baseline))
    assert proposals["selected_candidate_id"] == "candidate_001"
    assert any("candidate_999" in note for note in proposals["parse_notes"])


def test_think_tags_are_logged_on_each_llm_turn(baseline: Path, tmp_path: Path):
    replies = [
        f"<think>need the baseline artifacts first</think>\n{_tool('load_run_artifacts')}",
        *_happy_path_replies()[1:],
    ]
    proposals = _agent(_ScriptedLlm(replies)).propose(_fresh_bundle(baseline, tmp_path))
    trace = _load_jsonl(Path(proposals["tool_trace_path"]))
    llm_turns = [row for row in trace if row["event"] == "llm_turn"]
    tool_calls = [row for row in trace if row["event"] == "tool_call"]
    assert llm_turns
    assert llm_turns[0]["thinking"] == "need the baseline artifacts first"
    assert tool_calls
    assert tool_calls[0]["tool"] == "load_run_artifacts"
    assert tool_calls[0]["thinking"] == "need the baseline artifacts first"
    assert "result" in tool_calls[0]
    report = json.loads(Path(proposals["design_review_report_path"]).read_text(encoding="utf-8"))
    assert report["thinking_turns"][0]["thinking"] == "need the baseline artifacts first"
    assert any(
        row.get("thinking") == "need the baseline artifacts first"
        for row in proposals["deliberation_messages"]
    )


def test_provider_thinking_is_logged_from_generate_result(baseline: Path, tmp_path: Path):
    class ThinkingLlm(_ScriptedLlm):
        def generate_result(self, prompt: str) -> LLMGeneration:
            return LLMGeneration(
                text=super().generate(prompt),
                thinking="inspect the CO2 shortfall before sizing ARS",
            )

    proposals = _agent(ThinkingLlm(_happy_path_replies())).propose(
        _fresh_bundle(baseline, tmp_path)
    )
    trace = _load_jsonl(Path(proposals["tool_trace_path"]))
    llm_turns = [row for row in trace if row["event"] == "llm_turn"]
    assert all(
        row["thinking"] == "inspect the CO2 shortfall before sizing ARS" for row in llm_turns
    )
    assert proposals["llm_turn_count"] == len(llm_turns)


def test_rule_fallback_writes_each_tool_call(baseline: Path, tmp_path: Path):
    proposals = _agent(None).propose(_fresh_bundle(baseline, tmp_path))
    trace = _load_jsonl(Path(proposals["tool_trace_path"]))
    tools = [row["tool"] for row in trace if row.get("event") == "tool_call"]
    assert "load_run_artifacts" in tools
    assert "compute_theoretical_capacity" in tools
    assert "run_design_candidate" in tools
    assert "compare_design_runs" in tools
    assert all(
        row.get("source") == "rule_fallback"
        for row in trace
        if row.get("event") == "tool_call"
    )
    assert Path(proposals["tool_trace_path"]).exists()
    assert Path(proposals["design_review_report_path"]).exists()
