"""Session, artifacts, and claims registry (ADK-style storage cylinder)."""

from __future__ import annotations

from pathlib import Path

from core.storage import DesignStorage
from core.storage.claims import ClaimsRegistry, claim_phrases, rewrite_body_from_selected
from scenario.ssos_eclss_loop.design_ensemble import apply_claims_sweep
from scenario.ssos_eclss_loop.design_eval import STATUS_APPROVED, STATUS_PROVISIONAL


def test_session_is_isolated_per_agent(tmp_path: Path):
    store = DesignStorage(tmp_path)
    store.session.append("eclss_designer_1", {"event": "done", "secret": "LENS_ONE"})
    store.session.append("eclss_designer_2", {"event": "done", "secret": "LENS_TWO"})

    one = store.session.load("eclss_designer_1")
    two = store.session.load("eclss_designer_2")
    assert [row["secret"] for row in one] == ["LENS_ONE"]
    assert [row["secret"] for row in two] == ["LENS_TWO"]
    assert store.session.path_for("eclss_designer_1").exists()


def test_artifact_store_round_trips_json(tmp_path: Path):
    store = DesignStorage(tmp_path)
    path = store.artifacts.write_json("candidate_rankings.json", {"ranking": []})
    assert path == tmp_path / "candidate_rankings.json"
    assert store.artifacts.read_json("candidate_rankings.json") == {"ranking": []}


def test_claim_phrases_do_not_include_local_candidate_tail():
    phrases = claim_phrases(
        candidate_id="eclss_designer_1:candidate_001",
        local_candidate_id="candidate_001",
        fields={"plant_sim.ars.capacity_kg_day": 25.0},
    )
    assert "eclss_designer_1:candidate_001" in phrases
    assert "candidate_001" not in phrases


def test_sweep_ignores_phrases_shared_with_the_standing_claim(tmp_path: Path):
    registry = ClaimsRegistry(tmp_path / "claims.json")
    registry.register(
        agent_id="eclss_designer_1",
        candidate_id="eclss_designer_1:candidate_001",
        fields={"plant_sim.ars.capacity_kg_day": 25.0},
    )
    registry.register(
        agent_id="eclss_designer_2",
        candidate_id="eclss_designer_2:candidate_001",
        fields={"plant_sim.ars.capacity_kg_day": 25.0},
    )
    registry.retract_except("eclss_designer_2:candidate_001")
    hits = registry.sweep_text(
        "Adopted ranked candidate eclss_designer_2:candidate_001 "
        "(plant_sim.ars.capacity_kg_day=25.0)."
    )
    assert hits == []


def test_claims_sweep_rewrites_naked_retracted_recommendation(tmp_path: Path):
    registry = ClaimsRegistry(tmp_path / "claims.json")
    registry.register(
        agent_id="eclss_designer_1",
        candidate_id="eclss_designer_1:candidate_001",
        fields={"plant_sim.ars.capacity_kg_day": 10.0},
    )
    registry.register(
        agent_id="eclss_designer_2",
        candidate_id="eclss_designer_2:candidate_001",
        fields={"plant_sim.ars.capacity_kg_day": 25.0},
    )
    registry.retract_except("eclss_designer_2:candidate_001")
    selected = {
        "candidate_id": "eclss_designer_2:candidate_001",
        "fields": {"plant_sim.ars.capacity_kg_day": 25.0},
    }
    proposals = {
        "message": "Ship eclss_designer_1:candidate_001 now.",
        "reasoning": "lens 1 was right",
        "final_status": STATUS_APPROVED,
        "selected_candidate_id": "eclss_designer_2:candidate_001",
    }
    notes = apply_claims_sweep(proposals, registry, selected=selected)
    assert notes
    assert "eclss_designer_1:candidate_001" not in proposals["message"]
    assert proposals["selected_candidate_id"] in proposals["message"]
    assert proposals["final_status"] == STATUS_APPROVED
    assert (tmp_path / "claims.json").exists()


def test_failed_sweep_refuses_approved_final(tmp_path: Path):
    registry = ClaimsRegistry(tmp_path / "claims.json")
    registry.claims.append(
        {
            "claim_id": "poison",
            "agent_id": "x",
            "candidate_id": "poison",
            "status": "retracted",
            "phrases": ["Adopted ranked candidate"],
            "fields": {},
        }
    )
    selected = {"candidate_id": "winner", "fields": {}}
    proposals = {
        "message": "Adopted ranked candidate poison still standing.",
        "reasoning": "old",
        "final_status": STATUS_APPROVED,
        "selection_reason": "rank 1",
    }
    apply_claims_sweep(proposals, registry, selected=selected)
    rewritten = rewrite_body_from_selected(selected)
    assert "Adopted ranked candidate" in rewritten["message"]
    assert proposals["final_status"] == STATUS_PROVISIONAL
    assert proposals["requires_supervisor_approval"] is True
