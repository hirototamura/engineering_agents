import json
from pathlib import Path

import pytest

pytest.importorskip("onepiece.cube_scoring", reason="The new evaluator requires the current One-Piece checkout")

from integrations.one_piece.mechanical_bridge import MechanicalBridge
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.evaluation import aggregate, selection_key
from scenario.balancing_cube.memory import EngineeringMemory

STORE = Path(__file__).resolve().parents[3] / "one-piece/projects/balancing-cube/store"


@pytest.fixture(scope="module")
def snapshot():
    if not STORE.exists():
        pytest.skip("Integration requires the sibling canonical Cube store")
    return MechanicalBridge(STORE, snapshot_revision="requirement-scoring-20261115-2").load_snapshot()


def record(tilt=1, drift=1):
    rows = [{"time_s": i * .015, "tilt_total_deg": tilt, "pivot_displacement_mm": drift} for i in range(668)]
    return {"run_id": "case-1", "domain_id": "nominal", "condition_id": "release", "seed": 1,
            "summary": {"simulated_duration_s": 10.005, "status": "completed"}, "rows": rows,
            "screening": [], "paired_metrics": {"passed": False}}


def test_adapter_feedback_returns_measured_requirement_values_and_exact_contract(snapshot):
    data = record(3)
    result = aggregate([data], snapshot, [("nominal", "release", 1)])
    result["candidate_id"] = "test-candidate"
    feedback = BalancingCubeAdapter(snapshot).feedback(result)
    assert feedback["scoring_contract_ref"] == snapshot["scoring_contract_ref"]
    assert feedback["score"] == pytest.approx(-.5)
    rms = next(r for r in feedback["requirement_evaluation"]["cases"][0]["requirement_results"] if r["requirement_ref"]["id"] == "R-RMS")
    assert rms["value"] == pytest.approx(3)
    assert rms["limit"] == 2
    assert rms["deficit"] == pytest.approx(.5)
    assert feedback["requirement_evaluation"]["physical_status"] == "unjudged"
    assert selection_key(result)[0] == 0


def test_new_score_ties_after_pass_and_rejects_missing_or_duplicate_matrix(snapshot):
    a = aggregate([record()], snapshot, [("nominal", "release", 1)])
    b = aggregate([record(.01, .01)], snapshot, [("nominal", "release", 1)])
    assert selection_key(a) == selection_key(b) == (1, 0)
    with pytest.raises(ValueError, match="matrix"):
        aggregate([record(), record()], snapshot, [("nominal", "release", 1)])
    with pytest.raises(ValueError, match="matrix"):
        aggregate([record()], snapshot, [("nominal", "different", 1)])
    missing = record()
    missing["rows"] = []
    result = aggregate([missing], snapshot, [("nominal", "release", 1)])
    assert result["score"] is None
    assert selection_key(result)[0] == -1


def test_feedback_keeps_worst_case_values_without_repeating_every_rule(snapshot):
    a, b = record(.01, .01), record(3)
    b.update(run_id="case-2", seed=2)
    result = aggregate([a, b], snapshot, [("nominal", "release", 1), ("nominal", "release", 2)])
    result["candidate_id"] = "candidate"
    feedback = BalancingCubeAdapter(snapshot).feedback(result)["requirement_evaluation"]
    assert feedback["case_projection"]["total"] == 2
    assert len(feedback["requirement_results"]) == 4
    assert len(feedback["unjudged_requirements"]) == 18
    assert any(c["case_ref"]["run_id"] == "case-2" for c in feedback["cases"])
    assert len(result["requirement_evaluation"]["cases"]) == 2


def test_reset_freezes_onepiece_evaluator_sources(snapshot, monkeypatch):
    adapter = BalancingCubeAdapter(snapshot)
    original = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda p: b"altered evaluator" if p.name == "cube_scoring.py" else original(p))
    with pytest.raises(ValueError, match="requirement evaluator changed"):
        adapter.reset()


def test_unscorable_candidate_is_not_selected_by_the_loop(snapshot, monkeypatch, tmp_path):
    from environment.mujoco import backend
    from scenario.balancing_cube.loop import run_design_loop
    def early(*args, **kwargs):
        value = record()
        value["rows"] = value["rows"][:401]
        value["summary"].update(status="lost_balance", simulated_duration_s=6.)
        return {**value, "frames": [], "metadata": {"accelerated": False}}
    monkeypatch.setattr(backend, "native_rollout", early)
    result = run_design_loop(snapshot=snapshot, output_dir=tmp_path / "run", llm_client=None, rounds=1)
    assert result["status"] == "inconclusive"
    assert result["best"] is None
    assert json.loads((tmp_path / "run/design_proposals.json").read_text())["selected_candidate"] is None


def test_legacy_frozen_contract_keeps_original_formula():
    source = json.loads((Path(__file__).parents[1] / "fixtures/balancing_cube_snapshot.json").read_text())
    from scenario.balancing_cube.evaluation import screening
    summary = {r["metric"]: r["limit"] for r in source["contract"]["screening"]["criteria"]}
    summary.update(status="completed", simulated_duration_s=6, final_1s_tilt_rms_deg=1., continuous_torque_exceeded_fraction=.05)
    result = aggregate([{**record(), "summary": summary}], source, [("nominal", "release", 1)])
    assert "requirement_evaluation" not in result
    assert result["score"] == pytest.approx(1 - .05 - .2 * .05)


def test_memory_does_not_choose_legacy_positive_score_as_new_contract_best(tmp_path):
    memory = EngineeringMemory(tmp_path / "episodes.jsonl")
    for i, feedback in enumerate([{"score": .99}, {"score": -.2, "scoring_contract_ref": {"id": "new", "revision": "1"}}]):
        memory.record_episode(run_id="run", round_index=i, feedback=feedback, proposal={}, status="evaluated")
    retrieved = memory.retrieve(scoring_contract_ref={"id": "new", "revision": "1"})
    items = retrieved["episodic_memory"]
    best = [r for r in items if "best_measured_score" in r["selection_reasons"]]
    assert len(best) == 1
    assert best[0]["measured_feedback"]["score"] == -.2
