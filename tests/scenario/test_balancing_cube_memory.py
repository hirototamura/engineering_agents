"""Evidence memory persistence, bounded recall and cross-run reuse."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario.balancing_cube.memory import EngineeringMemory, proposal_configuration_digest


def proposal(identifier="one", **parameters):
    return {"id": identifier, "family": "bldc_ec45", "parameters": parameters,
            "hypothesis": "A larger wheel might improve stability"}


def test_persistent_idempotent_journal_keeps_exact_feedback_and_separate_hypotheses(tmp_path):
    memory = EngineeringMemory(tmp_path)
    feedback = {"score": 0.7686281972821207, "all_screening_passed": False,
                "failure_metrics": ["peak_tilt_deg"], "physical_verified": False}
    args = dict(run_id="prior", round_index=1, proposal=proposal(wheel_mass_kg=.08),
                feedback=feedback, source_refs=[{"id": "source", "revision": "v1"}])
    first = memory.record_episode(**args)
    journal_before = memory.journal_path.read_bytes()
    assert memory.record_episode(**args) == first
    assert memory.journal_path.read_bytes() == journal_before
    feedback["score"] = 123
    restored = EngineeringMemory(tmp_path)
    assert restored.episodes[0]["measured_feedback"]["score"] == 0.7686281972821207
    payload = restored.retrieve()
    assert payload["episodic_memory"][0]["measured_feedback"]["physical_verified"] is False
    assert payload["self_reflection_memory"][0]["classification"] == "unverified LLM interpretation"
    assert "might improve" in payload["self_reflection_memory"][0]["hypothesis"]
    args["feedback"] = {"score": 12}
    with pytest.raises(ValueError, match="Conflicting content"):
        restored.record_episode(**args)
    assert restored.journal_path.read_bytes() == journal_before


def test_append_only_chain_detects_modification_and_refuses_infinite_metrics(tmp_path):
    memory = EngineeringMemory(tmp_path)
    memory.record_episode(run_id="run", round_index=1, feedback={"score": .5})
    before = memory.journal_path.read_bytes()
    memory.record_episode(run_id="run", round_index=2, status="rejected",
                          proposal=proposal(wheel_mass_kg=.99), feedback={"error": "outside mechanical bounds"})
    assert memory.journal_path.read_bytes().startswith(before)
    assert EngineeringMemory(tmp_path).flush()["episode_count"] == 2
    with pytest.raises(ValueError):
        memory.record_episode(run_id="run", round_index=3, feedback={"score": float("nan")})
    text = memory.journal_path.read_text().replace('"score":0.5', '"score":0.6')
    memory.journal_path.write_text(text)
    with pytest.raises(ValueError, match="integrity failure"):
        EngineeringMemory(tmp_path)


def test_hybrid_recall_pins_repeat_best_and_relevant_diverse_failures(tmp_path):
    memory = EngineeringMemory(tmp_path)
    target = proposal(wheel_mass_kg=.04)
    memory.record_episode(run_id="r", round_index=1, proposal=target,
                          feedback={"score": .4, "failure_metrics": ["peak_tilt_deg"]})
    memory.record_episode(run_id="r", round_index=2, proposal=proposal(wheel_mass_kg=.05),
                          feedback={"score": .9, "all_screening_passed": True})
    rejected = memory.record_episode(run_id="r", round_index=3, proposal=proposal(wheel_mass_kg=.5),
                          status="rejected", feedback={"error": "wheel_mass_kg outside bounds"})
    for index in range(4, 10):
        memory.record_episode(run_id="r", round_index=index, proposal=proposal(wheel_mass_kg=.06 + index / 1000),
                             feedback={"score": .3, "failure_metrics": ["pivot_position_mm"]})
    recalled = memory.retrieve(query="wheel_mass_kg outside bounds",
                              configuration_digest=proposal_configuration_digest(target), limit=5)
    episodes = recalled["episodic_memory"]
    assert any("exact_configuration_repeat" in e["selection_reasons"] for e in episodes)
    assert any(e["measured_feedback"].get("score") == .9 for e in episodes)
    assert any(e["round"] == 9 for e in episodes)
    assert any(e["episode_id"] == rejected["episode_id"] for e in episodes)
    assert recalled["semantic_memory"]["failure_metric_episode_counts"]["pivot_position_mm"] == 6


def test_prompt_budget_does_not_truncate_numeric_evidence_and_retains_oversize_episode(tmp_path):
    memory = EngineeringMemory(tmp_path, max_prompt_chars=2000)
    measured = {"score": .8, "trial_results": [{"rms": i / 100} for i in range(1000)]}
    memory.record_episode(run_id="r", round_index=1, proposal=proposal(), feedback=measured)
    memory.record_episode(run_id="r", round_index=2, proposal=proposal(), status="duplicate",
                          feedback={"score": .8})
    recalled = memory.retrieve(max_chars=2000)
    encoded = json.dumps(recalled, ensure_ascii=False)
    assert len(encoded) <= 2000
    assert recalled["omitted_count"] >= 1
    assert memory.episodes[0]["measured_feedback"] == measured
    assert recalled["semantic_memory"]["repeated_configuration_count"] == 1


def test_settings_digest_excludes_ids_and_hypotheses():
    first = proposal("one", wheel_mass_kg=.04)
    second = {**first, "id": "renamed", "hypothesis": "Different explanation", "parent_id": "other"}
    assert proposal_configuration_digest(first) == proposal_configuration_digest(second)
    second["control"] = {"tilt_q_scale": 2}
    assert proposal_configuration_digest(first) != proposal_configuration_digest(second)


def test_two_independent_memory_writers_re_read_before_append(tmp_path):
    first, second = EngineeringMemory(tmp_path), EngineeringMemory(tmp_path)
    first.record_episode(run_id="a", round_index=1, feedback={"score": .1})
    second.record_episode(run_id="b", round_index=1, feedback={"score": .2})
    assert [e["sequence"] for e in first.episodes] == [1, 2]
    assert first.episodes[1]["previous_record_digest"] == first.episodes[0]["record_digest"]


def test_bootstrap_previous_results_preserves_duplicates_rejections_and_artifact_hashes(tmp_path):
    run = tmp_path / "previous"
    run.mkdir()
    result_dir = run / "candidates" / "candidate-002"
    result_dir.mkdir(parents=True)
    result = {"candidate_id": "one", "input_digest": "compiled-config-1", "score": .42,
              "proposal": proposal("one", wheel_mass_kg=.08), "records": [{"large_raw_data": True}]}
    (result_dir / "result.json").write_text(json.dumps(result))
    feedback = {"candidate_id": "one", "score": .42, "failure_metrics": ["peak_tilt_deg"]}
    summary = {"run_id": "previous", "rounds": [
        {"round": 1, "feedback": feedback}, {"round": 2, "feedback": feedback},
        {"round": 3, "status": "rejected", "error": "outside bounds"}]}
    (run / "summary.json").write_text(json.dumps(summary))
    for index in (1, 2):
        directory = run / f"round-{index:02d}"
        directory.mkdir()
        (directory / "proposal.json").write_text(json.dumps(proposal(str(index), wheel_mass_kg=.08)))
        (directory / "prompt-data.json").write_text('{"authority":"requirements are frozen"}')
    directory = run / "round-03"
    directory.mkdir()
    (directory / "rejected.json").write_text(json.dumps({"proposal": proposal("bad", wheel_mass_kg=.5)}))
    memory = EngineeringMemory(tmp_path / "memory")
    assert memory.bootstrap_run(run)["episode_count"] == 3
    assert memory.bootstrap_run(run)["episode_count"] == 3
    episodes = memory.episodes
    assert [e["status"] for e in episodes] == ["evaluated", "duplicate", "rejected"]
    assert episodes[1]["configuration_digest"] == "compiled-config-1"
    assert episodes[2]["proposal"]["parameters"]["wheel_mass_kg"] == .5
    assert all(len(ref["sha256"]) == 64 for e in episodes for ref in e["source_refs"])
    assert memory.retrieve()["semantic_memory"]["failure_metric_episode_counts"]["peak_tilt_deg"] == 2


def test_jsonl_path_and_sparse_historical_seed(tmp_path):
    run = tmp_path / "previous"
    run.mkdir()
    feedback = {"candidate_id": "candidate", "score": .42, "failure_metrics": ["peak_tilt_deg"]}
    (run / "summary.json").write_text(json.dumps({"run_id": "historical", "rounds": [
        {"round": 1, "feedback": feedback}, {"round": 2, "feedback": feedback}]}))
    for number in (1, 2):
        directory = run / f"round-{number:02d}"
        directory.mkdir()
        (directory / "proposal.json").write_text(json.dumps(proposal(str(number), wheel_mass_kg=.08)))
    path = tmp_path / "new" / "memory" / "episodes.jsonl"
    memory = EngineeringMemory(path)
    assert memory.journal_path == path
    assert memory.bootstrap_run(run)["episode_count"] == 2
    assert [e["status"] for e in memory.episodes] == ["evaluated", "duplicate"]
    assert all(e["configuration_digest_source"] == "proposal_settings" for e in memory.episodes)
    assert all(e["measured_feedback"] == feedback for e in memory.episodes)
