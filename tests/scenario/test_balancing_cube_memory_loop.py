"""Measured design-loop regressions for the opt-in persistent agent memory."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("scipy")

from scenario.balancing_cube.design import digest
from scenario.balancing_cube.loop import run_design_loop
from scenario.balancing_cube.memory import EngineeringMemory


FIXTURE = Path(__file__).parents[1] / "fixtures/balancing_cube_snapshot.json"


def snapshot():
    return json.loads(FIXTURE.read_text())


def proposal(mass=.05, *, control=False):
    value = {"id": "test-candidate", "family": "dc_rs385", "parameters": {
        "side_m": .18, "print_mass_ref_kg": .12, "wheel_mass_kg": mass,
        "wheel_radius_ratio": .30, "inner_radius_ratio": .80, "wheel_thickness_m": .006,
    }, "hypothesis": "Test one distinct ring mass against measured feedback with fixed evaluation conditions."}
    if control:
        value["control"] = {"tilt_q_scale": .5, "rate_q_scale": 1.0,
                            "momentum_q_scale": 1.0, "yaw_rate_gain_nm_s": .04}
    return value


class SequenceLLM:
    def __init__(self, responses):
        self.responses, self.prompts = responses, []

    def generate(self, prompt):
        data = json.loads(prompt)
        self.prompts.append(data)
        response = self.responses[len(self.prompts) - 1]
        return json.dumps(copy.deepcopy(response))


def test_ten_round_configuration_executes_ten_distinct_measured_designs(tmp_path):
    llm = SequenceLLM([proposal(.04 + i * .002) for i in range(10)])
    memory = EngineeringMemory(tmp_path / "memory")
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "ten-rounds",
        llm_client=llm, rounds=10, stagnation_rounds=10, max_candidates=20, memory=memory)
    assert result["iterations_requested"] == result["iterations_completed"] == 10
    assert len(llm.prompts) == 10
    assert result["candidates_evaluated"] == 11  # Reference plus ten actual new rollouts.
    assert all(row["stage_sequence"] == ["EN", "PI", "R", "E"] for row in result["rounds"])
    results = [json.loads(path.read_text()) for path in (tmp_path / "ten-rounds/candidates").glob("*/result.json")]
    assert {row["round"] for row in results} == set(range(11))
    assert len({row["input_digest"] for row in results}) == 11
    assert all(row["records"][0]["backend"]["backend"] == "native_mujoco_cpu" for row in results)
    assert len(memory.episodes) == 11


def test_factorial_cells_have_distinct_memory_identities_and_measured_artifacts(tmp_path):
    memory = EngineeringMemory(tmp_path / "memory")
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "factorial",
        llm_client=SequenceLLM([proposal(control=True)]), rounds=1, memory=memory)
    episodes = memory.episodes
    assert result["candidates_evaluated"] == len(episodes) == 4
    assert len({episode["episode_id"] for episode in episodes}) == 4
    assert len({episode["configuration_digest"] for episode in episodes}) == 4
    assert {episode["measured_feedback"]["matrix_cell"] for episode in episodes} == {"M0C0", "M1C0", "M0C1", "M1C1"}
    for episode in episodes:
        measured = json.loads(Path(episode["source_refs"][0]).read_text())
        assert episode["configuration_digest"] == measured["input_digest"]
        assert episode["measured_feedback"]["score"] == measured["score"]
        assert episode["measured_feedback"]["candidate_id"] == measured["candidate_id"]
    # Reusing the already measured reference does not add a fictitious new episode.
    assert sum(episode["round"] == 0 for episode in episodes) == 1


def test_first_result_is_durable_and_retrieved_in_second_proposal_prompt(tmp_path):
    memory = EngineeringMemory(tmp_path / "memory")
    llm = SequenceLLM([proposal(.045), proposal(.055)])
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "feedback",
        llm_client=llm, rounds=2, memory=memory)
    first = result["rounds"][0]["feedback"]
    retrieved = llm.prompts[1]["agent_memory"]["episodic_memory"]
    measured = next(row for row in retrieved if row["measured_feedback"].get("candidate_id") == first["candidate_id"])
    persisted = next(row for row in EngineeringMemory(tmp_path / "memory").episodes
                     if row["episode_id"] == measured["episode_id"])
    assert measured["measured_feedback"] == persisted["measured_feedback"]
    assert measured["feedback_digest"] == persisted["feedback_digest"]
    assert measured["measured_feedback"]["score"] == first["score"]
    assert llm.prompts[0]["agent_memory"]["episode_count"] == 1
    assert llm.prompts[1]["agent_memory"]["episode_count"] == 2


def test_invalid_and_duplicate_repairs_preserve_final_prompt_digest(tmp_path):
    memory = EngineeringMemory(tmp_path / "memory")
    invalid = {**proposal(.055), "evaluation": {"loss_of_balance_deg": 90}}
    llm = SequenceLLM([proposal(.045), invalid, proposal(.045), proposal(.055)])
    root = tmp_path / "repairs"
    result = run_design_loop(snapshot=snapshot(), output_dir=root, llm_client=llm,
        rounds=2, memory=memory, proposal_retries=2)
    assert result["iterations_completed"] == 2
    assert result["candidates_evaluated"] == 3
    assert len(llm.prompts) == 4
    assert "allowlisted" in llm.prompts[2]["repair_feedback"]["error"]
    assert "already evaluated" in llm.prompts[3]["repair_feedback"]["error"]
    final_prompt = json.loads((root / "round-02/prompt-data.json").read_text())
    assert final_prompt == llm.prompts[-1]
    assert final_prompt == json.loads((root / "round-02/attempt-03-prompt-data.json").read_text())
    compiled = json.loads((root / "candidates/candidate-003/compiled.json").read_text())
    evaluated = json.loads((root / "candidates/candidate-003/result.json").read_text())
    assert compiled["pi_prompt_digest"] == evaluated["pi_prompt_digest"] == digest(final_prompt)
    rejected = [episode for episode in memory.episodes if episode["status"] == "rejected"]
    assert len(rejected) == len({episode["episode_id"] for episode in rejected}) == 2
    assert all((root / f"round-02/attempt-{i:02d}-rejected.json").exists() for i in (1, 2))
    assert not (root / "round-02/rejected.json").exists()


def test_seed_memory_factory_runs_after_output_immutability_guard(tmp_path):
    historical_root = tmp_path / "historical"
    history = run_design_loop(snapshot=snapshot(), output_dir=historical_root,
        llm_client=SequenceLLM([proposal(.045)]), rounds=1)
    root = tmp_path / "seeded"
    created = []
    def factory():
        assert root.is_dir()
        memory = EngineeringMemory(root / "memory")
        memory.bootstrap_run(historical_root)
        created.append(memory)
        return memory
    llm = SequenceLLM([proposal(.055)])
    result = run_design_loop(snapshot=snapshot(), output_dir=root, llm_client=llm,
        rounds=1, memory=factory)
    assert result["iterations_completed"] == 1 and len(created) == 1
    assert any(episode["run_id"] == history["run_id"]
               for episode in llm.prompts[0]["agent_memory"]["episodic_memory"])
    count = len(created[0].episodes)
    with pytest.raises(ValueError, match="immutable"):
        run_design_loop(snapshot=snapshot(), output_dir=root, llm_client=llm,
                        rounds=1, memory=factory)
    assert len(created) == 1 and len(created[0].episodes) == count


def test_exhausted_repairs_preserve_the_actual_last_prompt_digest(tmp_path):
    invalid = {**proposal(.045), "evaluation": {"loss_of_balance_deg": 90}}
    llm = SequenceLLM([invalid, invalid, invalid])
    root = tmp_path / "exhausted"
    result = run_design_loop(snapshot=snapshot(), output_dir=root, llm_client=llm,
        rounds=1, memory=EngineeringMemory(tmp_path / "memory"), proposal_retries=2)
    assert len(llm.prompts) == 3
    assert result["iterations_completed"] == 0
    last_prompt = json.loads((root / "round-01/attempt-03-prompt-data.json").read_text())
    rejected = json.loads((root / "round-01/rejected.json").read_text())
    assert last_prompt == llm.prompts[-1]
    assert json.loads((root / "round-01/prompt-data.json").read_text()) == last_prompt
    assert rejected["pi_prompt_digest"] == digest(last_prompt)


def test_rejected_proposal_is_not_counted_as_completed_measured_round(tmp_path):
    invalid = {**proposal(.045), "sensing": {"control_delay_s": 0}}
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "partial",
        llm_client=SequenceLLM([invalid, proposal(.055)]), rounds=2)
    assert len(result["rounds"]) == 2
    assert result["rounds"][0]["status"] == "rejected"
    assert result["rounds"][1]["stage_sequence"] == ["EN", "PI", "R", "E"]
    assert result["iterations_completed"] == 1


def test_seeded_factorial_run_retains_reference_every_cell_and_exact_feedback(tmp_path):
    root = tmp_path / 'factorial-seed'
    summary = run_design_loop(snapshot=snapshot(), output_dir=root,
        llm_client=SequenceLLM([proposal(control=True)]), rounds=1)
    measured = [json.loads(p.read_text()) for p in (root / 'candidates').glob('*/result.json')]
    assert len(measured) == 4
    # The baseline shall remain in memory even when another candidate is best.
    summary['best'] = next(r for r in measured if r['matrix_cell'] == 'M1C1')
    (root / 'summary.json').write_text(json.dumps(summary))
    before = {p: p.read_bytes() for p in root.rglob('*.json')}
    seeded = EngineeringMemory(tmp_path / 'seeded-memory')
    assert seeded.bootstrap_run(root)['episode_count'] == 5
    journal = seeded.journal_path.read_bytes()
    assert seeded.bootstrap_run(root)['episode_count'] == 5
    assert seeded.journal_path.read_bytes() == journal
    validation_episode = next(e for e in seeded.episodes if e['status'] == 'historical_validation')
    validation = json.loads((root / 'validation/result.json').read_text())
    assert validation_episode['measured_feedback']['score'] == validation['score']
    assert 'not an unseen holdout' in validation_episode['measured_feedback']['disclosure']
    episodes = [e for e in seeded.episodes if e['status'] != 'historical_validation']
    assert {e['measured_feedback']['matrix_cell'] for e in episodes} == {'M0C0', 'M1C0', 'M0C1', 'M1C1'}
    for result in measured:
        episode = next(e for e in episodes if e['configuration_digest'] == result['input_digest'])
        assert episode['proposal'] == result['proposal']
        assert episode['measured_feedback']['score'] == result['score']
        failed_metrics = sorted({c['metric'] for trial in result['records']
                                 for c in trial['screening'] if not c['passed']})
        assert episode['measured_feedback']['failure_metrics'] == failed_metrics
        assert episode['measured_feedback']['all_screening_passed'] == result['all_screening_passed']
        assert any(ref['kind'] == 'numeric_result' and len(ref['sha256']) == 64 for ref in episode['source_refs'])
    assert all(p.read_bytes() == content for p, content in before.items())
