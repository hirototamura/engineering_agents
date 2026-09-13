"""One designer, then an independent three-lens audit panel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agents.persona import ARCHETYPE_LENSES
from core.storage import DesignStorage
from scenario.ssos_eclss_loop.design_ensemble import (
    AUDIT_BRIEF_CHAR_BUDGET,
    AuditAgent,
    AuditVerdict,
    build_audit_brief,
    collect_audit_evidence,
    integrate_audit_panel,
    merge_audit_llm_cfg,
    resolve_audit_config,
    run_lens_audit,
)
from scenario.ssos_eclss_loop.design_eval import STATUS_APPROVED, STATUS_PROVISIONAL
from scenario.ssos_eclss_loop.design_variables import BASELINE_CAPACITY

ARS = "plant_sim.ars.capacity_kg_day"
OGS = "plant_sim.ogs.max_o2_kg_day"
WRS = "plant_sim.wrs.max_feed_l_per_operation"


def _designer_record(*, local_id: str = "candidate_001") -> dict:
    return {
        "candidate_id": local_id,
        "fields": {
            "plant_sim.ars.capacity_kg_day": 25.0,
            "plant_sim.ogs.max_o2_kg_day": 12.0,
            "plant_sim.wrs.max_feed_l_per_operation": 14.0,
        },
        "final_eligible": True,
        "simulated": True,
        "run_dir": f"/tmp/{local_id}",
        "constraint_evaluation": {
            "preflight_status": "valid",
            "constraint_status": "feasible",
            "total_mass_kg": 80.0,
            "total_volume_m3": 1.0,
            "total_cost_musd": 1.0,
        },
        "outcome": {
            "crew_remaining": 50,
            "crew_initial": 50,
            "critical_step_count": 1,
            "warning_step_count": 0,
            "evaluation_compact": {"score": 89, "max_score": 90},
        },
    }


def _designer_proposal(tmp_path: Path, record: dict) -> dict:
    return {
        "proposed_by": "eclss_designer_1",
        "decision_source": "design_decision_loop",
        "selected_candidate_id": record["candidate_id"],
        "final_status": STATUS_APPROVED,
        "message": "size ARS to 25",
        "reasoning": "the crew cadence needs the larger machine",
        "ranked_candidates": [record],
        "baseline_outcome": {"crew_remaining": 40, "crew_initial": 50},
        "parse_notes": [],
        "deliberation_messages": [
            {"from_role": "eclss_designer_1", "message": "size ARS to 25", "to_role": "team"}
        ],
        "tool_trace_path": str(tmp_path / "tool_trace.jsonl"),
        "changes": [
            {
                "change_kind": "capacity_profile",
                "payload": {"backend": "plant_sim", "fields": record["fields"]},
            }
        ],
        "requires_supervisor_approval": False,
        "selection_reason": "full survival",
    }


def _panel(*decisions: str) -> list:
    lenses = ["rederive_numbers", "avoid_local_optima", "design_validity"]
    verdicts = []
    for index, decision in enumerate(decisions, start=1):
        lens = lenses[index - 1]
        verdicts.append(
            AuditVerdict(
                decision=decision,
                agent_id=f"eclss_auditor_{index}",
                lens=lens,
                message=f"{lens} says {decision}",
                reasoning=f"{lens} checked the numbers",
            )
        )
    return verdicts


def test_resolve_audit_config_builds_three_lens_panel():
    cfg = resolve_audit_config(
        {
            "audit": {
                "enabled": True,
                "count": 3,
                "id_prefix": "eclss_auditor",
                "archetypes": ["rederive_numbers", "avoid_local_optima", "design_validity"],
                "persona": "",
            }
        }
    )
    assert cfg["enabled"] is True
    assert [agent.agent_id for agent in cfg["agents"]] == [
        "eclss_auditor_1",
        "eclss_auditor_2",
        "eclss_auditor_3",
    ]
    assert [agent.lens for agent in cfg["agents"]] == [
        "rederive_numbers",
        "avoid_local_optima",
        "design_validity",
    ]
    assert cfg["agents"][0].persona == ARCHETYPE_LENSES["rederive_numbers"]


def test_resolve_audit_config_default_lenses_include_avoid_local_optima():
    cfg = resolve_audit_config({"audit": {"enabled": True}})
    assert [agent.lens for agent in cfg["agents"]] == [
        "rederive_numbers",
        "avoid_local_optima",
        "design_validity",
    ]


def test_resolve_audit_config_missing_block_is_off():
    assert resolve_audit_config({})["enabled"] is False
    assert resolve_audit_config({})["agents"] == []


def test_resolve_audit_config_unknown_lens_raises():
    with pytest.raises(ValueError, match="Unknown audit lens"):
        resolve_audit_config({"audit": {"enabled": True, "archetypes": ["bogus"]}})


def test_panel_all_approve_keeps_designer_machine(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    bundle = type("Bundle", (), {"run_dir": tmp_path, "scenario_config": {}, "baseline_graph": {}})()
    merged = integrate_audit_panel(bundle, designer, _panel("approve", "approve", "approve"), DesignStorage(tmp_path))
    assert merged["selected_candidate_id"] == "candidate_001"
    assert merged["proposed_by"] == "eclss_designer_1"
    assert merged["audited_by"] == ["eclss_auditor_1", "eclss_auditor_2", "eclss_auditor_3"]
    assert merged["decision_source"] == "tool_use_audit_panel"
    assert merged["final_status"] == STATUS_APPROVED
    assert merged["changes"][0]["payload"]["fields"] == record["fields"]
    assert "size ARS to 25" in merged["message"]
    assert "rederive_numbers says approve" in merged["message"]
    assert "avoid_local_optima says approve" in merged["message"]
    assert "design_validity says approve" in merged["message"]
    assert "ranked_candidates" not in merged
    report = json.loads((tmp_path / "design_review_report.json").read_text(encoding="utf-8"))
    assert len(report["audit"]) == 3


def test_audit_merge_keeps_the_designer_review_report(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    (tmp_path / "design_review_report.json").write_text(
        json.dumps(
            {
                "thinking_turns": [{"choice": "propose_candidate", "thinking": "size ARS"}],
                "llm_turn_count": 1,
                "plots": ["/tmp/co2.png"],
                "evidence": {"computed_features": True},
                "selection": {"rank_rationale": "full survival first"},
                "notes": ["designer note"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate_rankings.json").write_text(
        json.dumps(
            {
                "baseline": {"crew_remaining": 40},
                "ranking": [{"candidate_id": "candidate_001"}],
                "selection": {"rank_rationale": "full survival first"},
            }
        ),
        encoding="utf-8",
    )
    bundle = type("Bundle", (), {"run_dir": tmp_path, "scenario_config": {}, "baseline_graph": {}})()
    integrate_audit_panel(bundle, designer, _panel("approve", "approve", "approve"), DesignStorage(tmp_path))
    report = json.loads((tmp_path / "design_review_report.json").read_text(encoding="utf-8"))
    assert report["thinking_turns"][0]["thinking"] == "size ARS"
    assert report["llm_turn_count"] == 1
    assert report["plots"] == ["/tmp/co2.png"]
    assert report["evidence"]["computed_features"] is True
    assert report["evidence"]["audit_panel"] == 3
    assert report["selection"]["rank_rationale"] == "full survival first"
    assert "designer note" in report["notes"]
    assert len(report["audit"]) == 3
    rankings = json.loads((tmp_path / "candidate_rankings.json").read_text(encoding="utf-8"))
    assert rankings["selection"]["rank_rationale"] == "full survival first"
    assert rankings["baseline"]["crew_remaining"] == 40
    assert len(rankings["audit"]) == 3


def _scenario(*, ars: float = 4.5, ogs: float = 9.25, wrs: float = 10.0) -> dict:
    return {
        "plant_sim": {
            "ars": {"capacity_kg_day": ars},
            "ogs": {"max_o2_kg_day": ogs},
            "wrs": {"max_feed_l_per_operation": wrs},
        }
    }


def test_rejected_items_are_pinned_to_installed(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    bundle = type(
        "Bundle",
        (),
        {"run_dir": tmp_path, "scenario_config": _scenario(wrs=10.0), "baseline_graph": {}},
    )()
    panel = _panel("approve", "reject", "approve")
    panel[1].rejected_fields = [WRS]
    merged = integrate_audit_panel(bundle, designer, panel, DesignStorage(tmp_path))
    fields = merged["changes"][0]["payload"]["fields"]
    assert fields[ARS] == 25.0
    assert fields[OGS] == 12.0
    assert fields[WRS] == 10.0
    ranked = designer["ranked_candidates"][0]
    assert ranked["fields"][WRS] == 14.0
    assert ranked.get("audited_fields") is None
    assert merged["decision_source"] == "tool_use_audit_panel:item_veto"
    assert merged["final_status"] == STATUS_PROVISIONAL
    assert merged["requires_supervisor_approval"] is True


def test_vetoed_ogs_does_not_revert_to_yaml_baseline(tmp_path: Path):
    record = _designer_record()
    record["fields"] = {ARS: 4.5, OGS: 48.0, WRS: 10.0}
    designer = _designer_proposal(tmp_path, record)
    bundle = type(
        "Bundle",
        (),
        {"run_dir": tmp_path, "scenario_config": _scenario(ogs=50.0), "baseline_graph": {}},
    )()
    panel = _panel("approve", "reject", "approve")
    panel[1].rejected_fields = [OGS]
    merged = integrate_audit_panel(bundle, designer, panel, DesignStorage(tmp_path))
    fields = merged["changes"][0]["payload"]["fields"]
    assert fields[ARS] == 4.5
    assert fields[OGS] == 50.0
    assert fields[WRS] == 10.0
    assert set(fields) == {ARS, OGS, WRS}


def test_empty_veto_keeps_installed_machine_so_the_next_run_can_proceed(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    bundle = type(
        "Bundle",
        (),
        {
            "run_dir": tmp_path,
            "scenario_config": _scenario(ars=4.5, ogs=50.0, wrs=10.0),
            "baseline_graph": {},
        },
    )()
    panel = _panel("reject", "reject", "reject")
    for verdict, key in zip(panel, [ARS, OGS, WRS]):
        verdict.rejected_fields = [key]
    merged = integrate_audit_panel(bundle, designer, panel, DesignStorage(tmp_path))
    assert merged["changes"][0]["payload"]["fields"] == {
        ARS: 4.5,
        OGS: 50.0,
        WRS: 10.0,
    }
    assert merged["decision_source"] == "tool_use_audit_panel:kept_to_proceed"
    assert merged["final_status"] == STATUS_PROVISIONAL


def test_unusable_audits_do_not_invent_a_machine(tmp_path: Path):
    designer = _designer_proposal(tmp_path, _designer_record())
    bundle = type("Bundle", (), {"run_dir": tmp_path, "scenario_config": {}, "baseline_graph": {}})()
    merged = integrate_audit_panel(
        bundle,
        designer,
        [
            AuditVerdict(
                decision="fallback",
                agent_id="eclss_auditor_1",
                lens="rederive_numbers",
                fallback_reason="unknown_decision:adopt",
            ),
            AuditVerdict(
                decision="fallback",
                agent_id="eclss_auditor_2",
                lens="avoid_local_optima",
                fallback_reason="unusable_reply:empty_response",
            ),
            AuditVerdict(
                decision="fallback",
                agent_id="eclss_auditor_3",
                lens="design_validity",
                fallback_reason="no_llm_client",
            ),
        ],
        DesignStorage(tmp_path),
    )
    assert merged["selected_candidate_id"] == "candidate_001"
    assert merged["decision_source"] == "design_decision_loop"
    assert merged["final_status"] == STATUS_APPROVED


def test_audit_brief_shows_designer_and_forbids_a_new_machine(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    brief = build_audit_brief(
        designer=designer,
        ranked=[record],
        bias_direction="declared bias text",
        auditor=AuditAgent(
            agent_id="eclss_auditor_2",
                lens="avoid_local_optima",
            persona="audit persona",
        ),
    )
    assert "You are eclss_auditor_2" in brief
    assert "size ARS to 25" in brief
    assert "declared bias text" in brief
    assert "do not invent" in brief.lower() or "Do not invent" in brief
    assert "eclss_auditor_1" not in brief
    assert "eclss_auditor_3" not in brief
    assert "evaluation_compact" not in brief
    assert len(brief) < AUDIT_BRIEF_CHAR_BUDGET


def test_audit_brief_does_not_embed_raw_evaluation_or_long_speech(tmp_path: Path):
    record = _designer_record()
    record["outcome"]["evaluation_compact"] = {
        "score": 89,
        "max_score": 90,
        "device_response": {
            "operations": [{"quality": index, "payload": "x" * 200} for index in range(400)]
        },
        "actor_decision": {"attempts": [{"id": index} for index in range(400)]},
    }
    designer = _designer_proposal(tmp_path, record)
    designer["message"] = "keep the lead " + ("word " * 2000)
    designer["reasoning"] = "because " + ("why " * 2000)
    brief = build_audit_brief(
        designer=designer,
        ranked=[record],
        bias_direction="bias",
        auditor=AuditAgent(
            agent_id="eclss_auditor_1",
            lens="rederive_numbers",
            persona="p",
        ),
    )
    assert "keep the lead" in brief
    assert "operations" not in brief
    assert "attempts" not in brief
    assert len(brief) < 4000
    assert "chars omitted" in brief


class _AuditLlm:
    def __init__(self, reply: str):
        self.reply = reply
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def test_invented_rejected_field_is_ignored(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    bundle = type("Bundle", (), {"run_dir": tmp_path, "scenario_config": {}, "baseline_graph": {}})()
    panel = _panel("reject", "approve", "approve")
    panel[0].rejected_fields = ["invented.field", "plant_sim.wrs.max_feed_l_per_operation"]
    merged = integrate_audit_panel(bundle, designer, panel, DesignStorage(tmp_path))
    fields = merged["changes"][0]["payload"]["fields"]
    assert "invented.field" not in fields
    assert fields[WRS] == BASELINE_CAPACITY[WRS]
    assert fields[ARS] == 25.0


def test_run_lens_audit_treats_invented_adopt_as_abstain():
    verdict = run_lens_audit(
        llm_client=_AuditLlm(
            '{"decision": "adopt", "candidate_id": "invented", "message": "no"}'
        ),
        brief="brief",
        auditor=AuditAgent(
            agent_id="eclss_auditor_1",
            lens="rederive_numbers",
            persona="p",
        ),
    )
    assert verdict.decision == "fallback"
    assert verdict.fallback_reason == "unknown_decision:adopt"


def test_run_lens_audit_reads_rejected_fields():
    verdict = run_lens_audit(
        llm_client=_AuditLlm(
            '{"decision": "reject",'
            ' "rejected_fields": ["plant_sim.wrs.max_feed_l_per_operation", "invented"],'
            ' "message": "wrs only"}'
        ),
        brief="brief",
        auditor=AuditAgent(
            agent_id="eclss_auditor_2",
            lens="avoid_local_optima",
            persona="p",
        ),
    )
    assert verdict.decision == "reject"
    assert verdict.rejected_fields == [WRS]


def test_audit_evidence_is_nameplates_and_chain_only(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    (tmp_path / "compact_chain_memory.json").write_text(
        json.dumps(
            {
                "last_effective_design": {"fields": {OGS: 50.0}},
                "theoretical_floor": {"ogs": 42.0},
                "best_full_survival": {"crew_remaining": 50},
                "proposal_guidance": {"prefer_complete_capacity_profile": True},
            }
        ),
        encoding="utf-8",
    )
    evidence = collect_audit_evidence(
        designer=designer,
        ranked=[record],
        scenario_config=_scenario(ogs=50.0),
        run_dir=tmp_path,
    )
    assert evidence["installed"][OGS] == 50.0
    assert evidence["proposed"][ARS] == 25.0
    assert evidence["delta"][OGS] == 12.0 - 50.0
    assert evidence["chain"]["last_effective_design"]["fields"][OGS] == 50.0
    assert evidence["chain"]["theoretical_floor"]["ogs"] == 42.0
    assert "proposal_guidance" not in evidence["chain"]
    brief = build_audit_brief(
        designer=designer,
        ranked=[record],
        bias_direction="",
        auditor=AuditAgent(agent_id="eclss_auditor_1", lens="rederive_numbers", persona="p"),
        evidence=evidence,
    )
    assert "Installed vs proposed" in brief
    assert "50.0" in brief
    assert "proposal_guidance" not in brief
    assert len(brief) < 4000


def test_merge_audit_llm_cfg_lowers_tokens_and_keeps_think():
    cfg = merge_audit_llm_cfg(
        {
            "llm": {"model": "qwen3.8-27b-uncensored", "think": True, "max_tokens": 16384},
            "audit": {"llm": {}},
        },
        {"max_tokens": 6144},
    )
    assert cfg["think"] is True
    assert cfg["max_tokens"] == 2048
    assert cfg["model"] == "qwen3.8-27b-uncensored"
    explicit = merge_audit_llm_cfg(
        {"llm": {"think": True, "max_tokens": 16384}, "audit": {"llm": {"max_tokens": 1536}}},
        {"max_tokens": 6144},
    )
    assert explicit["max_tokens"] == 1536
