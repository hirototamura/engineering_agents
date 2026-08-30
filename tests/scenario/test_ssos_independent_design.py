"""One designer, then an independent three-lens audit panel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.agents.persona import ARCHETYPE_LENSES
from core.storage import DesignStorage
from scenario.ssos_eclss_loop.design_ensemble import (
    AuditAgent,
    AuditVerdict,
    build_audit_brief,
    integrate_audit_panel,
    resolve_audit_config,
    run_lens_audit,
)
from scenario.ssos_eclss_loop.design_eval import STATUS_APPROVED, STATUS_PROVISIONAL


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


def test_rejected_items_are_dropped_and_the_rest_are_kept(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    bundle = type("Bundle", (), {"run_dir": tmp_path, "scenario_config": {}, "baseline_graph": {}})()
    panel = _panel("approve", "reject", "approve")
    panel[1].rejected_fields = ["plant_sim.wrs.max_feed_l_per_operation"]
    merged = integrate_audit_panel(bundle, designer, panel, DesignStorage(tmp_path))
    fields = merged["changes"][0]["payload"]["fields"]
    assert fields["plant_sim.ars.capacity_kg_day"] == 25.0
    assert fields["plant_sim.ogs.max_o2_kg_day"] == 12.0
    assert "plant_sim.wrs.max_feed_l_per_operation" not in fields
    assert merged["decision_source"] == "tool_use_audit_panel:item_veto"
    assert merged["final_status"] == STATUS_PROVISIONAL
    assert merged["requires_supervisor_approval"] is True


def test_empty_veto_keeps_designer_fields_so_the_next_run_can_proceed(tmp_path: Path):
    record = _designer_record()
    designer = _designer_proposal(tmp_path, record)
    bundle = type("Bundle", (), {"run_dir": tmp_path, "scenario_config": {}, "baseline_graph": {}})()
    panel = _panel("reject", "reject", "reject")
    for verdict, key in zip(
        panel,
        [
            "plant_sim.ars.capacity_kg_day",
            "plant_sim.ogs.max_o2_kg_day",
            "plant_sim.wrs.max_feed_l_per_operation",
        ],
    ):
        verdict.rejected_fields = [key]
    merged = integrate_audit_panel(bundle, designer, panel, DesignStorage(tmp_path))
    assert merged["changes"][0]["payload"]["fields"] == record["fields"]
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
    assert "plant_sim.wrs.max_feed_l_per_operation" not in fields
    assert fields["plant_sim.ars.capacity_kg_day"] == 25.0


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
    assert verdict.rejected_fields == ["plant_sim.wrs.max_feed_l_per_operation"]
