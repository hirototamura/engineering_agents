"""CLI integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tools.cli.main import app

runner = CliRunner()

# scenario.yaml ships with iteration.enabled true; pin a single sim when the test is not about chaining.
NO_CHAIN = ("--set", "iteration.enabled=false")


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_scenarios_lists_registered_scenarios():
    result = runner.invoke(app, ["scenarios"])
    assert result.exit_code == 0
    assert "scrubber_degradation" in result.stdout
    assert "ssos_eclss_loop" in result.stdout


def test_run_scrubber_short(tmp_path: Path):
    output_dir = tmp_path / "cli-run"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert str(output_dir) in result.stdout.replace("\n", "")
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["steps"] == 2


def test_run_unknown_scenario():
    result = runner.invoke(app, ["run", "missing_scenario"])
    assert result.exit_code == 2
    assert "Unknown scenario" in result.output


def test_run_rejects_invalid_agents_mode():
    result = runner.invoke(
        app,
        ["run", "scrubber_degradation", "--agents-mode", "labelled_rule_base"],
    )
    assert result.exit_code == 2
    assert "Unsupported agents mode" in result.output


def test_run_rejects_invalid_backend():
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", *NO_CHAIN, "--backend", "ros3"],
    )
    assert result.exit_code == 2
    assert "Unsupported backend kind" in result.output


def test_run_ssos_rejects_actor_and_agents_mode_together():
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--agents-mode",
            "llm",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "only one of --actor-mode and --agents-mode" in result.output


def test_run_ssos_actor_and_design_mode_dry_run(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "llm",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["overrides"]["agents"]["actor"]["mode"] == "labeled_rule_base"
    assert payload["overrides"]["agents"]["design"]["mode"] == "llm"


def test_run_ssos_bare_defaults_plant_sim_labeled_llm(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", "--dry-run", "--write-spec", str(spec_path)],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    overrides = payload["overrides"]
    assert overrides["backend"]["kind"] == "plant_sim"
    assert overrides["agents"]["actor"]["mode"] == "labeled_rule_base"
    assert overrides["agents"]["design"]["mode"] == "llm"
    assert payload["approve_provisional"] is True
    assert "inject_failures" not in overrides
    assert "inject_failures: false" in result.stdout
    assert "iterate: 50" in result.stdout
    assert "actor=labeled_rule_base" in result.stdout
    assert "design=llm" in result.stdout
    assert "backend: plant_sim" in result.stdout
    assert "INFO" in result.output
    assert "auto-approves LLM design proposals" in result.output


def test_run_ssos_actor_flag_without_design_inherits(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    design = ((payload["overrides"].get("agents") or {}).get("design") or {})
    assert design.get("mode") is None
    assert "design=llm" not in result.stdout


def test_run_rejects_invalid_design_mode():
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", *NO_CHAIN, "--backend", "mock", "--design-mode", "wizard"],
    )
    assert result.exit_code == 2
    assert "Unsupported design mode" in result.output


def test_run_rejects_invalid_agents_mode_via_set():
    result = runner.invoke(
        app,
        ["run", "scrubber_degradation", "--set", "agents.mode=evil"],
    )
    assert result.exit_code == 2
    assert "Unsupported agents mode" in result.output


def test_run_scrubber_default_agents_mode_from_scenario(tmp_path: Path):
    output_dir = tmp_path / "default-mode"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["agents_mode"] == "none"


def test_run_ssos_mock_env_with_docker(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SSOS_ECLSS_BACKEND", "mock")
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: "/usr/bin/docker")
    output_dir = tmp_path / "mock-env"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()


def test_run_ssos_without_docker_blocks(monkeypatch):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "ros2",
            "--agents-mode",
            "none",
            "--steps",
            "1",
        ],
    )
    assert result.exit_code == 3
    assert "Docker is required" in result.output


def test_run_ssos_mock_without_docker_allowed(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    output_dir = tmp_path / "mock-run"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()


def test_run_ssos_inject_failures_flag(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    output_dir = tmp_path / "inject-failures"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--agents-mode",
            "none",
            "--steps",
            "12",
            "--inject-failures",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    telemetry = [
        json.loads(line)
        for line in (output_dir / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_step = {row["step"]: row for row in telemetry if not row.get("post_ops")}
    assert summary["inject_failures"] is True
    assert by_step[9]["ars_failure_enabled"] is False
    assert by_step[10]["ars_failure_enabled"] is True


def test_run_ssos_plant_sim_without_docker_allowed(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    output_dir = tmp_path / "plant-sim-run"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "plant_sim",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary.get("backend") == "plant_sim"


def test_run_dry_run_write_spec(tmp_path: Path):
    spec_path = tmp_path / "job.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    assert spec_path.exists()
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["scenario"] == "scrubber_degradation"


def test_job_run_from_spec(tmp_path: Path):
    output_dir = tmp_path / "job-run"
    spec_path = tmp_path / "job.json"
    spec_path.write_text(
        json.dumps(
            {
                "scenario": "scrubber_degradation",
                "overrides": {"agents": {"mode": "none"}, "simulation": {"steps": 2}},
                "output_dir": str(output_dir),
                "recreate_output": True,
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["job", "run", str(spec_path), "--quiet"])
    assert result.exit_code == 0
    assert (output_dir / "summary.json").exists()


def test_run_writes_duration_wall_s(tmp_path: Path):
    output_dir = tmp_path / "duration-run"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--steps",
            "2",
            "--output-dir",
            str(output_dir),
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert "duration_wall_s" in summary
    assert summary["duration_wall_s"] >= 0


def test_run_rejects_invalid_llm_provider():
    result = runner.invoke(
        app,
        ["run", "scrubber_degradation", "--llm-provider", "llamacpp", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "Unsupported LLM provider" in result.output


def test_run_llm_provider_vllm_dry_run_writes_spec(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "llm",
            "--llm-provider",
            "vllm",
            "--llm-model",
            "qwen3-32b",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["overrides"]["agents"]["mode"] == "llm"
    assert payload["overrides"]["agents"]["llm"]["provider"] == "vllm"
    assert payload["overrides"]["agents"]["llm"]["model"] == "qwen3-32b"
    assert payload["overrides"]["agents"]["llm"]["base_url"].endswith("/v1")


def test_run_llm_provider_from_env_writes_spec(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "llm",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["overrides"]["agents"]["llm"]["provider"] == "vllm"
    assert payload["overrides"]["agents"]["llm"]["model"] == "qwen3-8b"
    assert "10.10.0.108:8000" in payload["overrides"]["agents"]["llm"]["base_url"]


def test_run_ssos_plan_shows_actor_and_design_modes():
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "llm",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "actor=labeled_rule_base" in result.stdout
    assert "design=llm" in result.stdout


def test_run_ssos_llm_provider_only_patches_llm_side(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "llm",
            "--llm-provider",
            "ollama",
            "--dry-run",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    actor_llm = ((payload["overrides"].get("agents") or {}).get("actor") or {}).get("llm") or {}
    design_llm = ((payload["overrides"].get("agents") or {}).get("design") or {}).get("llm") or {}
    assert actor_llm.get("provider") != "ollama"
    assert design_llm.get("provider") == "ollama"


def test_preflight_targets_cover_both_ssos_llm_sides():
    from tools.cli.commands.run import _preflight_llm_targets

    both = _preflight_llm_targets(
        "ssos_eclss_loop",
        {"agents": {"actor": {"mode": "llm"}, "design": {"mode": "llm"}}},
    )
    assert [side for side, _cfg in both] == ["actor", "design"]
    design_only = _preflight_llm_targets(
        "ssos_eclss_loop",
        {"agents": {"actor": {"mode": "labeled_rule_base"}, "design": {"mode": "llm"}}},
    )
    assert [side for side, _cfg in design_only] == ["design"]


def test_iterate_rejects_scrubber():
    result = runner.invoke(app, ["run", "scrubber_degradation", "--iterate", "2", "--dry-run"])
    assert result.exit_code == 2
    assert "ssos_eclss_loop" in result.output


def test_iterate_rejects_ros2_backend():
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", "--iterate", "2", "--backend", "ros2", "--dry-run"],
    )
    assert result.exit_code == 2
    assert "plant_sim" in result.output


def test_iterate_rejects_apply_proposals(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "2",
            "--apply-proposals",
            str(tmp_path / "design_proposals.json"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "apply-proposals" in result.output


def test_iterate_dry_run_defaults(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "3",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert str(tmp_path / "chain") in result.stdout
    assert "approve_provisional: true" in result.stdout
    assert "inject_failures: false" in result.stdout
    assert "INFO" in result.output
    assert "auto-approves LLM design proposals" in result.output


def test_iterate_inherits_inject_failures_from_scenario(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    chain_dir = tmp_path / "chain-no-fail"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "1",
            "--backend",
            "mock",
            "--actor-mode",
            "none",
            "--design-mode",
            "none",
            "--steps",
            "2",
            "--no-paired-replay",
            "--output-dir",
            str(chain_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((chain_dir / "01" / "summary.json").read_text(encoding="utf-8"))
    assert summary["inject_failures"] is False


def test_iterate_inject_failures_flag_overrides_scenario(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    chain_dir = tmp_path / "chain-fail"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "1",
            "--backend",
            "mock",
            "--actor-mode",
            "none",
            "--design-mode",
            "none",
            "--steps",
            "2",
            "--inject-failures",
            "--no-paired-replay",
            "--output-dir",
            str(chain_dir),
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    summary = json.loads((chain_dir / "01" / "summary.json").read_text(encoding="utf-8"))
    assert summary["inject_failures"] is True


def test_iterate_rejects_defaults_set():
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--set",
            "iteration.defaults.inject_failures=true",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "iteration.defaults was removed" in result.output


def test_iterate_yaml_enabled_via_set(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--set",
            "iteration.enabled=true",
            "--set",
            "iteration.count=2",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "iterate: 2" in result.stdout


def test_iterate_set_count_wins_over_yaml_count(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "2",
            "--set",
            "iteration.count=9",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "iterate: 2" in result.stdout


def test_iterate_no_paired_replay_overrides_yaml(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "2",
            "--no-paired-replay",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "paired_replay: false" in result.stdout


def test_iterate_set_paired_replay_false(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "2",
            "--set",
            "iteration.paired_replay=false",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "paired_replay: false" in result.stdout


def test_ssos_without_iterate_does_not_chain(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        ["run", "ssos_eclss_loop", *NO_CHAIN, "--dry-run", "--write-spec", str(spec_path)],
    )
    assert result.exit_code == 0
    assert "iterate:" not in result.stdout


def test_ssos_bare_run_chains_from_yaml(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "iterate: 50" in result.stdout


def test_yaml_chain_without_iterate_flag_uses_live_reporter(monkeypatch, tmp_path: Path):
    from tools.cli.output import ChainLiveReporter

    captured: dict = {}

    def fake_run_design_iterate(**kwargs):
        captured["reporter"] = kwargs.get("reporter")
        return {
            "iterations_requested": 5,
            "iterations_completed": 5,
            "runs": [],
            "replay_runs": [],
            "verdict": "INCONCLUSIVE",
            "chain_summary_path": str(tmp_path / "chain_summary.json"),
        }

    monkeypatch.setattr("tools.cli.commands.iterate.run_design_iterate", fake_run_design_iterate)
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--backend",
            "mock",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
        ],
    )
    assert result.exit_code == 0
    assert isinstance(captured.get("reporter"), ChainLiveReporter)
    assert captured["reporter"].iterations == 50


def test_single_ssos_run_hooks_step_progress(monkeypatch, tmp_path: Path):
    from scenario.jobs.spec import RunResult

    captured: dict = {}

    def fake_execute(spec, on_step=None, on_phase=None):
        captured["on_step"] = on_step
        captured["on_phase"] = on_phase
        run_dir = tmp_path / "single"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text("{}", encoding="utf-8")
        return RunResult(run_dir=run_dir, summary={}, duration_s=0.1, exit_code=0)

    monkeypatch.setattr("tools.cli.commands.run.execute_run", fake_execute)
    monkeypatch.delenv("EA_RUN_IN_CONTAINER", raising=False)
    monkeypatch.setattr("tools.cli.ssos_host.shutil.which", lambda _: None)
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--backend",
            "mock",
            "--actor-mode",
            "none",
            "--design-mode",
            "none",
            "--steps",
            "3",
            "--output-dir",
            str(tmp_path / "single-out"),
        ],
    )
    assert result.exit_code == 0
    assert captured.get("on_step") is not None
    assert captured.get("on_phase") is not None


def test_iterate_omitted_scenario_defaults_to_ssos(tmp_path: Path):
    result = runner.invoke(
        app,
        ["run", "--iterate", "2", "--backend", "mock", "--output-dir", str(tmp_path / "chain"), "--dry-run"],
    )
    assert result.exit_code == 0
    assert str(tmp_path / "chain") in result.stdout
    assert "INFO" in result.output


def test_run_ssos_no_approve_provisional_skips_info(tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            *NO_CHAIN,
            "--dry-run",
            "--no-approve-provisional",
            "--write-spec",
            str(spec_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(spec_path.read_text(encoding="utf-8"))
    assert payload["approve_provisional"] is False
    assert "auto-approves LLM design proposals" not in result.output


def test_run_scrubber_does_not_note_approve_provisional(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "run",
            "scrubber_degradation",
            "--agents-mode",
            "none",
            "--dry-run",
            "--output-dir",
            str(tmp_path / "scrubber"),
        ],
    )
    assert result.exit_code == 0
    assert "auto-approves LLM design proposals" not in result.output


def test_chain_exit_code_fails_on_run_or_incomplete_chain():
    from tools.cli import exit_codes
    from tools.cli.commands.iterate import chain_exit_code

    assert chain_exit_code(
        {
            "iterations_requested": 2,
            "iterations_completed": 2,
            "runs": [{"exit_code": 0}, {"exit_code": 0}],
            "replay_runs": [{"exit_code": 0}],
        }
    ) == exit_codes.SUCCESS
    assert chain_exit_code(
        {
            "iterations_requested": 2,
            "iterations_completed": 1,
            "runs": [{"exit_code": 0}, {"exit_code": 1}],
            "stopped_reason": "iteration 2 failed",
        }
    ) == exit_codes.RUN_FAILURE
    assert chain_exit_code(
        {
            "iterations_requested": 2,
            "iterations_completed": 2,
            "runs": [{"exit_code": 0}, {"exit_code": 0}],
            "replay_runs": [{"exit_code": 1}],
        }
    ) == exit_codes.RUN_FAILURE
    assert chain_exit_code(
        {
            "iterations_requested": 3,
            "iterations_completed": 2,
            "runs": [{"exit_code": 0}, {"exit_code": 0}],
            "stopped_reason": "frozen requirements hash changed",
        }
    ) == exit_codes.RUN_FAILURE


def test_iterate_exits_nonzero_when_a_chained_run_fails(monkeypatch, tmp_path: Path):
    def fake_run_design_iterate(**_kwargs):
        return {
            "iterations_requested": 2,
            "iterations_completed": 1,
            "stopped_reason": "iteration 2 failed",
            "runs": [
                {"iteration": 1, "exit_code": 0, "crew_remaining": 4, "crew_lost": 0},
                {"iteration": 2, "exit_code": 1, "crew_remaining": None, "crew_lost": None},
            ],
            "replay_runs": [],
            "verdict": "INCONCLUSIVE",
            "chain_summary_path": str(tmp_path / "chain_summary.json"),
        }

    monkeypatch.setattr("tools.cli.commands.iterate.run_design_iterate", fake_run_design_iterate)
    result = runner.invoke(
        app,
        [
            "run",
            "ssos_eclss_loop",
            "--iterate",
            "2",
            "--backend",
            "mock",
            "--actor-mode",
            "labeled_rule_base",
            "--design-mode",
            "labeled_rule_base",
            "--output-dir",
            str(tmp_path / "chain"),
        ],
    )
    assert result.exit_code == 1
    assert "iteration 2 failed" in result.output


# --------------------------------------------------------------------------- #
# the chain's final answer reaches the terminal
# --------------------------------------------------------------------------- #
def _chain_summary_with(final_answer: dict) -> dict:
    return {
        "verdict": "IMPROVED",
        "crew_remaining_first": 29,
        "crew_remaining_last": 50,
        "crew_remaining_baseline_replay": 29,
        "crew_remaining_final_replay": 50,
        "claim": "unified design applied across chained sims",
        "final_answer": final_answer,
    }


def test_the_terminal_names_the_design_the_chain_answers_with(capsys):
    from tools.cli.output import print_chain_summary

    print_chain_summary(
        _chain_summary_with(
            {
                "status": "provisional_final",
                "selected_candidate_id": "i1/candidate_002",
                "iteration": 1,
                "fields": {"plant_sim.ars.capacity_kg_day": 52.0},
                "crew_remaining": 50,
                "crew_initial": 50,
                "reason": "over budget",
                "requires_supervisor_approval": True,
                "candidates_considered": 7,
                "path": "chain/chain_final_answer.json",
            }
        ),
        skip_runs_table=True,
    )
    out = capsys.readouterr().out
    assert "Final answer" in out
    assert "i1/candidate_002" in out
    assert "50/50" in out
    assert "needs a human to approve" in out


def test_the_terminal_says_when_the_chain_has_no_design_to_hand_over(capsys):
    """Not silence, and not the verdict standing in for an answer."""
    from tools.cli.output import print_chain_summary

    print_chain_summary(
        _chain_summary_with(
            {
                "status": "rejected_final",
                "selected_candidate_id": None,
                "reason": "no candidate keeps every occupant alive within the bounds",
                "candidates_considered": 7,
                "path": "chain/chain_final_answer.json",
            }
        ),
        skip_runs_table=True,
    )
    out = capsys.readouterr().out
    # The chain improved. It still has nothing to build, and says so.
    assert "IMPROVED" in out
    assert "rejected_final" in out
    assert "no candidate keeps every occupant alive" in out
