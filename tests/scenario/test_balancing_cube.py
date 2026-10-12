"""Real native MuJoCo short episodes plus deterministic orchestration guards."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("scipy")

from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.design import compile_controller, compile_mechanical, digest
from scenario.balancing_cube.loop import run_design_loop

FIXTURE = Path(__file__).parents[1] / "fixtures/balancing_cube_snapshot.json"


def snapshot():
    return json.loads(FIXTURE.read_text())


def proposal(identifier="small-ring", *, control=False):
    value = {"id": identifier, "family": "dc_rs385", "parameters": {
        "side_m": .18, "print_mass_ref_kg": .12, "wheel_mass_kg": .05,
        "wheel_radius_ratio": .30, "inner_radius_ratio": .80, "wheel_thickness_m": .006,
    }, "hypothesis": "Compare coupled ring inertia and mass with the frozen reference"}
    if control:
        value["control"] = {"tilt_q_scale": .5, "rate_q_scale": 1.0,
                            "momentum_q_scale": 1.0, "yaw_rate_gain_nm_s": .04}
    return value


class FakeLLM:
    def __init__(self, joint=False):
        self.prompts = []
        self.joint = joint

    def generate(self, prompt):
        data = json.loads(prompt)
        self.prompts.append(data)
        value = proposal(str(len(self.prompts)), control=self.joint)
        value["parameters"]["wheel_mass_kg"] += .005 * (len(self.prompts) - 1)
        return json.dumps(value)


def test_mechanical_compiler_updates_dependent_inertias_and_rejects_verifier_edits():
    source = snapshot()
    before = digest(source)
    config = compile_mechanical(proposal(), source)
    assert config["physics"]["wheel_radius_m"] == pytest.approx(.054)
    assert config["physics"]["wheel_mass_kg"] == pytest.approx(.075)
    assert 2 * config["physics"]["wheel_transverse_inertia_kg_m2"] >= config["physics"]["wheel_axial_inertia_kg_m2"]
    assert digest(source) == before
    with pytest.raises(ValueError):
        compile_mechanical({**proposal(), "evaluation": {"loss_of_balance_deg": 90}}, source)
    with pytest.raises(ValueError):
        compile_mechanical({**proposal(), "parameters": {**proposal()["parameters"], "side_m": .5}}, source)


def test_controller_changes_only_q_groups_yaw_keep_r_and_nominal_linearization():
    source = snapshot()
    frozen = compile_controller(proposal(), source)
    assert frozen == source["controller"]
    same_as_frozen = {"control": {"tilt_q_scale": 1.0, "rate_q_scale": 1.0,
        "momentum_q_scale": 1.0,
        "yaw_rate_gain_nm_s": source["model"]["controller"]["yaw_rate_gain_nm_s"]}}
    assert compile_controller(same_as_frozen, source) == frozen
    designed = compile_controller(proposal(control=True), source)
    assert designed["fixed_r"] == source["model"]["controller"]["vertex_r"]
    assert designed["yaw_rate_gain_nm_s"] == .04
    assert designed["K"] != frozen["K"]
    with pytest.raises(ValueError):
        compile_controller({"control": {"vertex_r": [1, 1]}}, source)
    with pytest.raises(ValueError):
        compile_controller({"control": {"tilt_q_scale": .1}}, source)


@pytest.mark.parametrize("value", [list(proposal()["parameters"]), None, True, "side_m"])
def test_mechanical_parameters_require_a_json_object(value):
    with pytest.raises(ValueError, match="parameters.*object"):
        compile_mechanical({**proposal(), "parameters": value}, snapshot())


@pytest.mark.parametrize("value", [list(proposal(control=True)["control"]), None, False, "tilt_q_scale"])
def test_control_parameters_require_a_json_object(value):
    with pytest.raises(ValueError, match="control.*object"):
        compile_controller({**proposal(), "control": value}, snapshot())


def test_malformed_nested_proposal_is_recorded_and_next_round_runs(tmp_path):
    class MalformedThenValid(FakeLLM):
        def generate(self, prompt):
            value = json.loads(super().generate(prompt))
            if len(self.prompts) == 1:
                value["parameters"] = list(value["parameters"])
            return json.dumps(value)
    bridge = ssot_bridge(tmp_path)
    result = run_design_loop(snapshot=bridge.load_snapshot(), output_dir=tmp_path / "malformed",
                             llm_client=MalformedThenValid(), rounds=2, bridge=bridge)
    rejected = bridge.store.records(kinds=["design_proposal"])
    assert len(rejected) == 1 and rejected[0]["data"]["status"] == "rejected"
    assert isinstance(rejected[0]["data"]["proposal"]["parameters"], list)
    assert result["rounds"][0]["status"] == "rejected"
    assert result["rounds"][1]["stage_sequence"] == ["EN", "PI", "R", "E"]
    assert (tmp_path / "malformed/summary.json").is_file()
    assert bridge.store.check()["ok"]


def test_llm_provider_failure_stops_campaign_as_inconclusive(tmp_path):
    from core.llm.base import LLMGeneration

    class FailedLLM:
        def generate_result(self, prompt):
            return LLMGeneration(text="", error="local provider read timeout")

    bridge = ssot_bridge(tmp_path)
    result = run_design_loop(snapshot=bridge.load_snapshot(), output_dir=tmp_path / "provider-failed",
                             llm_client=FailedLLM(), rounds=2, bridge=bridge)
    failed = [r for r in bridge.store.records(kinds=["design_proposal"])
              if r["id"].endswith(".failed.1")]
    assert len(failed) == 1 and failed[0]["data"]["status"] == "failed"
    assert result["status"] == "inconclusive"
    assert result["stopped_reason"] == "proposal_generation_failed"
    assert result["rounds"] == [{"round": 1, "status": "failed", "error": "local provider read timeout"}]


def test_pi_projection_keeps_model_parameter_leafs_in_source_only(tmp_path):
    onepiece = pytest.importorskip("onepiece")
    from scenario.balancing_cube.loop import _compact_agent_context

    bridge = ssot_bridge(tmp_path)
    leaf = onepiece.make_record(project_id="balancing-cube", id="model-leaf-test", kind="model_parameter",
        data={"name": "physics timestep", "model_path": "physics.timestep_s", "value": .001,
              "authoritative_field": "data.model.physics.timestep_s", "unit": "s",
              "value_source": {"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"}})
    bridge.store.import_records([leaf])
    source = bridge.context()
    projection = _compact_agent_context(source, bridge.load_snapshot())
    assert any(r["id"] == "model-leaf-test" for r in source["records"])
    assert not any(r["id"] == "model-leaf-test" for r in projection["records"])
    assert projection["counts"]["model_parameter_leaves_in_source"] == 1


@pytest.mark.parametrize("limits,expected_status", [
    ({"pivot_drift_stop_mm": .005}, "excessive_slip"),
    ({"contact_loss_stop_s": .015}, "lost_contact"),
    ({"slip_stop_speed_m_s": 0.0, "slip_stop_duration_s": .015}, "excessive_slip"),
])
def test_cpu_uses_authoritative_stop_thresholds(limits, expected_status):
    from environment.mujoco.backend import native_rollout
    source = snapshot()
    cfg = source["model"]
    cfg["evaluation"].update(limits)
    case = {"id": "stop-threshold", "seed": 0, "initial_tilt_deg": [1, 0], "duration_s": .06}
    if expected_status == "lost_contact":
        # With no gravity the initial geometric contact carries no load.
        case["initial_tilt_deg"] = [0, 0]
        cfg["physics"]["gravity_m_s2"] = 0.0
    result = native_rollout(cfg, case, source["controller"])
    assert result["summary"]["status"] == expected_status
    assert result["summary"]["simulated_duration_s"] < case["duration_s"]


def test_gpu_trajectory_parameters_use_the_same_authoritative_limits_as_cpu():
    from environment.mujoco.contact import contact_stop_limits
    from environment.mujoco.gpu_backend import _world_parameters
    cfg = snapshot()["model"]
    cfg["evaluation"].update(contact_loss_stop_s=.03, slip_stop_speed_m_s=.002,
                             slip_stop_duration_s=.045, pivot_drift_stop_mm=.005)
    assert contact_stop_limits(cfg["evaluation"]) == (.03, .002, .045, .005)
    params = _world_parameters(cfg, {}, duration=.06, dt=.015, lag=0)
    assert params[10:14] == [.03, .045, .002, .005]


def test_real_two_rounds_evolve_policy_and_feed_it_to_next_pi(tmp_path):
    source = snapshot()
    fake = FakeLLM()
    calls = []
    def reload():
        calls.append(True)
        return copy.deepcopy(source)
    result = run_design_loop(snapshot=source, output_dir=tmp_path / "loop", llm_client=fake,
                             rounds=2, context_loader=reload)
    assert len(fake.prompts) == 2 and len(calls) == 2
    assert fake.prompts[0]["policy"]["revision"] == 1
    assert fake.prompts[1]["policy"]["revision"] == 2
    assert fake.prompts[0]["proposal_schema"]["parameter_keys"] == [
        "side_m", "print_mass_ref_kg", "wheel_mass_kg", "wheel_radius_ratio", "inner_radius_ratio", "wheel_thickness_m"]
    assert fake.prompts[0]["proposal_schema"]["control_keys"] == [
        "tilt_q_scale", "rate_q_scale", "momentum_q_scale", "yaw_rate_gain_nm_s"]
    assert set(fake.prompts[0]["valid_example"]["parameters"]) == set(fake.prompts[0]["proposal_schema"]["parameter_keys"])
    assert fake.prompts[0]["valid_example"]["hypothesis"]
    assert len(json.dumps(fake.prompts[0]["context_data"], ensure_ascii=False)) < 100_000
    assert "Do not use aliases" in fake.prompts[0]["output_contract"]
    assert fake.prompts[1]["policy"]["suggested_search_step"] != fake.prompts[0]["policy"]["suggested_search_step"]
    assert "Measured candidate" in fake.prompts[1]["policy"]["hypothesis"]
    assert fake.prompts[1]["feedback"]
    assert result["iterations_completed"] == 2 and result["candidates_evaluated"] == 3
    assert result["numeric_gpu_verified"] is False and result["physical_verified"] is False
    saved = sorted((tmp_path / "loop/candidates").glob("*/result.json"))
    controllers = set()
    for path in saved:
        value = json.loads(path.read_text())
        controllers.add(value["controller_digest"])
        record = value["records"][0]
        assert len(record["frames"]) > 1
        assert record["backend"]["backend"] == "native_mujoco_cpu"
        assert record["physics_timestep_s"] == source["model"]["physics"]["timestep_s"]
        assert value["half_step_adjudication_performed"] is False
        assert value["gpu_state"] == "not_run"
    assert len(controllers) == 1


def test_joint_mechanical_and_control_changes_run_factorial_campaigns(tmp_path):
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "factorial",
                             llm_client=FakeLLM(joint=True), rounds=1)
    assert result["candidates_evaluated"] == 4
    assert result["rounds"][0]["factorial_cells"] == ["M0C0", "M1C0", "M0C1", "M1C1"]
    values = [json.loads(path.read_text()) for path in (tmp_path / "factorial/candidates").glob("*/result.json")]
    assert len({value["campaign_id"] for value in values}) == 2
    for campaign in {value["campaign_id"] for value in values}:
        assert len({value["controller_digest"] for value in values if value["campaign_id"] == campaign}) == 1


def test_hash_guard_rejects_mutated_environment_before_rollout():
    adapter = BalancingCubeAdapter(snapshot())
    adapter.snapshot["contract"]["screening"]["required_duration_s"] *= 2
    with pytest.raises(ValueError, match="invalid_contract_tamper"):
        adapter.reset()


def test_gpu_unavailability_cannot_promote_cpu_evidence(monkeypatch):
    from environment.mujoco import backend
    from environment.mujoco import gpu_backend
    def unavailable(*args, **kwargs):
        raise RuntimeError("no CUDA device")
    monkeypatch.setattr(gpu_backend, "run_batch", unavailable)
    adapter = BalancingCubeAdapter(snapshot())
    result = adapter.rollout(adapter.compile(proposal()), require_gpu=True)
    assert result["numeric_cpu_verified"] is True
    assert result["numeric_gpu_verified"] is False
    assert result["gpu_state"] == "not_run"
    assert result["agreement_state"] == "inconclusive"


def test_changed_ssot_revision_requires_new_run(tmp_path):
    source = snapshot()
    changed = copy.deepcopy(source)
    changed["requirements"].append({"id": "new-requirement"})
    fake = FakeLLM()
    result = run_design_loop(snapshot=source, output_dir=tmp_path / "changed", llm_client=fake,
                             rounds=2, context_loader=lambda: changed)
    assert result["stopped_reason"] == "context_revision_changed_requires_new_run"
    assert fake.prompts == []


def test_cpu_import_does_not_load_jax_in_clean_process():
    import subprocess
    result = subprocess.run([sys.executable, "-c",
        "import sys; from scenario.balancing_cube.adapter import BalancingCubeAdapter; from environment.mujoco.backend import native_rollout; assert 'jax' not in sys.modules"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def ssot_bridge(tmp_path):
    onepiece = pytest.importorskip("onepiece")
    from integrations.one_piece.mechanical_bridge import MechanicalBridge
    source = snapshot()
    requirement = onepiece.make_record(project_id="balancing-cube", id="R-TEST", kind="requirement",
                                       data=source["requirements"][0])
    parameters = [onepiece.make_record(project_id="balancing-cube", id=p["id"], kind="parameter", data=p)
                  for p in source["kdps"]["entries"]]
    comparison = onepiece.make_record(project_id="balancing-cube", id="BEST", kind="design", data={
        "physics": {**source["model"]["physics"], "cube_side_m": .17},
        "actuation": source["model"]["actuation"],
    })
    language_profile = onepiece.make_record(project_id="balancing-cube", id="cube.language.profile",
        kind="specification", revision="standards-draft-test", data={
            "name": "English requirement writing profile", "normative_modal": "shall",
            "requirement_standard": {"name": "ISO/IEC/IEEE 29148:2018"},
            "standards_precedence": [{"rank": 1, "name": "ISO/IEC/IEEE 29148:2018"},
                                     {"rank": 2, "name": "NASA systems engineering standards"},
                                     {"rank": 3, "name": "ASD-STE100 Issue 9"}],
        })
    source["language_profile_ref"] = onepiece.ref(language_profile)
    source["context_refs"] = {"requirements": [onepiece.ref(requirement)], "kdps": [onepiece.ref(p) for p in parameters]}
    source["comparison_design_ref"] = onepiece.ref(comparison)
    record = onepiece.make_record(project_id="balancing-cube", id="cube.simulation.snapshot",
                                  kind="simulation_snapshot", revision="fixed-dt-mvp-2", data=source)
    store = onepiece.Store(tmp_path / "store")
    store.import_records([requirement, *parameters, comparison, language_profile, record])
    return MechanicalBridge(tmp_path / "store")


def test_real_store_two_rounds_read_saved_evidence_and_resolve_comparison(tmp_path):
    bridge = ssot_bridge(tmp_path)
    source = bridge.load_snapshot()
    adapter = BalancingCubeAdapter(source)
    reference = adapter.compile({"id": "ref", "family": "reference", "parameters": {}, "hypothesis": "test"})
    assert reference["config"]["physics"]["cube_side_m"] == .17
    assert source["model"]["physics"]["cube_side_m"] != .17
    assert reference["controller"] == source["controller"]
    fake = FakeLLM()
    result = run_design_loop(snapshot=source, output_dir=tmp_path / "run", llm_client=fake,
                             rounds=2, bridge=bridge, context_loader=bridge.load_snapshot)
    assert result["iterations_completed"] == 2
    first_id = result["rounds"][0]["feedback"]["candidate_id"]
    saved = fake.prompts[1]["context_data"]["records"]
    assert any(r["kind"] == "simulation_run" and r["data"].get("candidate_id") == first_id for r in saved)
    profile = next(r for r in fake.prompts[0]["context_data"]["records"] if r["kind"] == "specification")
    assert profile["data"]["normative_modal"] == "shall"
    first_candidate = next(r for r in bridge.store.records(kinds=["design_candidate"])
                           if r["id"].endswith(".candidate.2"))
    artifact_paths = {a["path"] for a in first_candidate["artifacts"]}
    assert any(path.endswith("round-01/ssot-context.json") for path in artifact_paths)
    assert any(path.endswith("round-01/prompt-data.json") for path in artifact_paths)
    assert bridge.store.check()["ok"]
    assert bridge.outbox(tmp_path / "run").flush()["pending"] == 0


def test_agent_context_excludes_acceptance_runs_before_design_and_evidence_limits(tmp_path):
    onepiece = pytest.importorskip("onepiece")
    bridge = ssot_bridge(tmp_path)
    exclusions = json.loads((Path(__file__).parents[2] / "src/integrations/one_piece/agent_context_exclusions.json").read_text())
    acceptance_id = exclusions["excluded_run_ids"][0]
    records = [
        onepiece.make_record(project_id="balancing-cube", id=f"{acceptance_id}.candidate.1",
            kind="design_candidate", data={"snapshot_ref": {"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"}}),
        onepiece.make_record(project_id="balancing-cube", id=f"{acceptance_id}.evaluation.1",
            kind="simulation_run", data={"snapshot_ref": {"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"}}),
        onepiece.make_record(project_id="balancing-cube", id=f"{acceptance_id}.policy.1",
            kind="design_policy", data={"snapshot_ref": {"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"}}),
        onepiece.make_record(project_id="balancing-cube", id="real-experiment.candidate.1",
            kind="design_candidate", data={"snapshot_ref": {"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"}}),
        onepiece.make_record(project_id="balancing-cube", id="real-experiment.evaluation.1",
            kind="simulation_run", data={"snapshot_ref": {"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"}}),
        onepiece.make_record(project_id="balancing-cube", id="cube.campaign.summary", kind="campaign_summary",
            data={"prior46": {"count": 46, "passed": 31, "failed": 9, "pending": 6}}),
    ]
    bridge.store.import_records(records)

    context = bridge.context()
    visible_ids = {record["id"] for record in context["records"]}
    assert not any(identifier == acceptance_id or identifier.startswith(acceptance_id + ".")
                   for identifier in visible_ids)
    assert {"real-experiment.candidate.1", "real-experiment.evaluation.1", "BEST", "cube.campaign.summary"} <= visible_ids
    assert context["limits"] == {"max_designs": 5, "max_evidence": 8, "max_proposals": 5}
    assert context["excluded_acceptance_runs"] == exclusions["excluded_run_ids"]
    assert context["counts"]["pinned_designs"] == 1
    profile = next(r for r in context["records"] if r["kind"] == "specification")
    assert profile["data"]["normative_modal"] == "shall"


def test_sync_failure_stops_before_pi_and_retries_exact_records(tmp_path, monkeypatch):
    bridge = ssot_bridge(tmp_path)
    source = bridge.load_snapshot()
    deliver = bridge.store.import_records
    def unavailable(*args, **kwargs):
        raise OSError("simulated record destination unavailable")
    monkeypatch.setattr(bridge.store, "import_records", unavailable)
    fake = FakeLLM()
    result = run_design_loop(snapshot=source, output_dir=tmp_path / "outage", llm_client=fake,
                             rounds=2, bridge=bridge)
    assert result["stopped_reason"] == "onepiece_sync_pending_before_pi"
    assert result["status"] == "inconclusive" and not fake.prompts
    outbox = bridge.outbox(tmp_path / "outage")
    assert outbox.flush()["pending"] > 0
    monkeypatch.setattr(bridge.store, "import_records", deliver)
    assert outbox.flush()["pending"] == 0
    count = len(bridge.store.records())
    assert outbox.flush()["pending"] == 0
    assert len(bridge.store.records()) == count and bridge.store.check()["ok"]


def test_rejected_proposal_is_recorded_in_ssot(tmp_path):
    bridge = ssot_bridge(tmp_path)
    forbidden = {**proposal(), "sensing": {"control_delay_s": 0}}
    result = run_design_loop(snapshot=bridge.load_snapshot(), output_dir=tmp_path / "rejected",
                             llm_client=None, proposal=forbidden, rounds=1, bridge=bridge)
    rejections = bridge.store.records(kinds=["design_proposal"])
    assert len(rejections) == 1 and rejections[0]["data"]["status"] == "rejected"
    assert result["rounds"][0]["status"] == "rejected"


def test_deadline_retains_incomplete_evidence_without_aggregate_score():
    import time
    from scenario.balancing_cube.adapter import RolloutDeadlineExceeded
    adapter = BalancingCubeAdapter(snapshot())
    with pytest.raises(RolloutDeadlineExceeded) as stopped:
        adapter.rollout(adapter.compile(proposal()), deadline=time.monotonic() - 1)
    assert stopped.value.evidence["completed_cpu_trials"] == 0
    assert stopped.value.evidence["state"] == "incomplete"
    assert "score" not in stopped.value.evidence
    assert stopped.value.evidence["compiled"]["controller"]["K"]


def test_physics_failure_retains_configuration_and_cannot_select(tmp_path, monkeypatch):
    from environment.mujoco import backend
    def failed(*args, **kwargs):
        raise RuntimeError("injected native solver failure")
    monkeypatch.setattr(backend, "native_rollout", failed)
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "failed", llm_client=None)
    artifact = json.loads((tmp_path / "failed/incomplete-evaluations/attempt-001/result.json").read_text())
    assert artifact["state"] == "failed" and artifact["compiled"]["controller"]["K"]
    assert result["status"] == "inconclusive" and result["best"] is None
    assert result["numeric_gpu_verified"] is False


def test_reference_failure_never_starts_pi(tmp_path, monkeypatch):
    from environment.mujoco import backend
    def failed(*args, **kwargs):
        raise RuntimeError("reference solver failed")
    monkeypatch.setattr(backend, "native_rollout", failed)
    fake = FakeLLM()
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "run", llm_client=fake, rounds=2)
    assert result["status"] == "inconclusive"
    assert result["stopped_reason"] == "reference_execution_failed"
    assert not fake.prompts and not result["rounds"]


def test_requested_gpu_not_run_is_inconclusive_and_never_starts_pi(tmp_path, monkeypatch):
    from environment.mujoco import backend
    monkeypatch.setattr(backend, "gpu_rollouts", lambda *args: {"state": "not_run", "reason": "no GPU", "results": []})
    fake = FakeLLM()
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "gpu", llm_client=fake, require_gpu=True)
    assert result["status"] == "inconclusive" and result["required_gpu"] is True
    assert result["stopped_reason"] == "required_gpu_not_run_for_reference"
    assert not result["numeric_gpu_verified"] and not fake.prompts


def test_aggregate_failure_rolls_back_partial_factorial_best(tmp_path, monkeypatch):
    from scenario.balancing_cube import adapter as module
    actual = module.aggregate
    calls = []
    def aggregate(*args):
        calls.append(True)
        if len(calls) == 3:
            raise ValueError("corrupt aggregate in third factorial cell")
        result = actual(*args)
        if len(calls) == 2:
            result["score"] = 100.0  # Partial cell must never become the final selection.
        return result
    monkeypatch.setattr(module, "aggregate", aggregate)
    result = run_design_loop(snapshot=snapshot(), output_dir=tmp_path / "factorial",
                             llm_client=FakeLLM(joint=True), rounds=1)
    assert result["status"] == "inconclusive"
    assert result["stopped_reason"] == "incomplete_required_2x2_execution_failure"
    assert result["best"]["candidate_id"] == "reference"
    assert result["best"]["score"] != 100.0
    assert not (tmp_path / "factorial/round-01/rejected.json").exists()
    failed = json.loads((tmp_path / "factorial/incomplete-evaluations/attempt-001/result.json").read_text())
    assert failed["partial_cpu_results"] and "corrupt aggregate" in failed["reason"]


def test_executor_returns_nonzero_for_inconclusive_cube(tmp_path, monkeypatch):
    from scenario.balancing_cube.scenario_run import BalancingCubeScenario
    from scenario.jobs.executor import execute_run
    from scenario.jobs.spec import RunSpec
    root = tmp_path / "gpu-exit"
    root.mkdir()
    (root / "summary.json").write_text(json.dumps({"status": "inconclusive", "stopped_reason": "required_gpu_not_run_for_reference"}))
    monkeypatch.setattr(BalancingCubeScenario, "run", lambda *args, **kwargs: root)
    result = execute_run(RunSpec(scenario="balancing_cube", output_dir=root))
    assert result.exit_code != 0 and result.error == "required_gpu_not_run_for_reference"


@pytest.mark.parametrize('failure_stage', ['validation', 'summary'])
def test_final_sync_outage_is_inconclusive_and_preserves_retry_artifacts(tmp_path, monkeypatch, failure_stage):
    bridge = ssot_bridge(tmp_path)
    source = bridge.load_snapshot()
    deliver = bridge.store.import_records

    def fail_final_publication(records, **kwargs):
        if any(row['id'].endswith('.' + failure_stage) for row in records):
            raise OSError('simulated final publication outage')
        return deliver(records, **kwargs)

    monkeypatch.setattr(bridge.store, 'import_records', fail_final_publication)
    root = tmp_path / ('final-outage-' + failure_stage)
    result = run_design_loop(snapshot=source, output_dir=root, llm_client=FakeLLM(),
                             rounds=1, bridge=bridge)
    expected_phase = 'before' if failure_stage == 'validation' else 'after'
    assert result['status'] == 'inconclusive'
    assert result['stopped_reason'] == f'onepiece_sync_pending_{expected_phase}_summary'
    assert result['onepiece_sync']['after_summary_record']['pending'] > 0
    if failure_stage == 'validation':
        assert result['onepiece_sync']['before_summary_record']['pending'] > 0
    else:
        assert result['onepiece_sync']['before_summary_record']['pending'] == 0
    assert json.loads((root / 'summary.json').read_text()) == result
    assert json.loads((root / 'sync-status.json').read_text())['pending'] > 0
    outbox_before = (root / 'onepiece-outbox.json').read_bytes()
    publication_before = (root / 'publication/summary.json').read_bytes()
    monkeypatch.setattr(bridge.store, 'import_records', deliver)
    recovered = bridge.outbox(root)
    assert recovered.flush()['pending'] == 0
    assert recovered.flush()['pending'] == 0
    assert (root / 'publication/summary.json').read_bytes() == publication_before
    assert json.loads((root / 'summary.json').read_text()) == result
    queued = json.loads(outbox_before)
    restored = json.loads((root / 'onepiece-outbox.json').read_text())
    assert [e['record'] for e in queued] == [e['record'] for e in restored]
    assert bridge.store.check()['ok']


@pytest.mark.parametrize('enabled,expected_rounds', [(False, 1), (True, 3)])
def test_cli_iteration_enabled_flag_controls_actual_proposal_rounds(tmp_path, monkeypatch, enabled, expected_rounds):
    from typer.testing import CliRunner
    from tools.cli.main import app
    bridge = ssot_bridge(tmp_path)
    fake = FakeLLM()
    monkeypatch.setattr('core.llm.factory.build_llm_client', lambda config: fake)
    root = tmp_path / 'cli-iteration-flag'
    result = CliRunner().invoke(app, ['run', 'balancing_cube', '--backend', 'mujoco_cpu',
        '--design-mode', 'llm', '--iterate', '3', '--output-dir', str(root),
        '--set', f'ssot.path={bridge.store.path}',
        '--set', f'iteration.enabled={str(enabled).lower()}', '--json'])
    assert result.exit_code == 0, result.output
    summary = json.loads((root / 'summary.json').read_text())
    assert summary['iterations_requested'] == summary['iterations_completed'] == expected_rounds
    assert len(fake.prompts) == expected_rounds
    assert summary['status'] == 'completed'
    assert bridge.store.check()['ok']
