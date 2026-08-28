"""Chained ssos_eclss_loop design iterate runs."""

from __future__ import annotations

import json
from pathlib import Path

from scenario.jobs.iterate import VERDICT_INCONCLUSIVE, run_design_iterate
from scenario.jobs.progress import IterateReporter
from scenario.jobs.spec import RunSpec


def _labeled_overrides(*, backend: str, steps: int, inject_failures: bool = True) -> dict:
    return {
        "backend": {"kind": backend},
        "simulation": {"steps": steps},
        "inject_failures": inject_failures,
        "agents": {
            "mode": "labeled_rule_base",
            "actor": {
                "mode": "labeled_rule_base",
                "team": {"count": 4, "id_prefix": "eclss_actor"},
            },
            "design": {
                "mode": "labeled_rule_base",
                "team": {"count": 4, "id_prefix": "eclss_designer"},
            },
        },
        "plant_sim": {"crew": {"size": 4}},
    }


def test_design_iterate_mock_applies_only_previous_applied_file(tmp_path: Path):
    chain_dir = tmp_path / "chain"
    summary = run_design_iterate(
        iterations=3,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="mock", steps=4),
        ),
    )
    assert summary["iterations_completed"] == 3
    assert (chain_dir / "01" / "summary.json").exists()
    assert (chain_dir / "02" / "summary.json").exists()
    assert (chain_dir / "03" / "summary.json").exists()
    assert (chain_dir / "chain_summary.json").exists()

    second = json.loads((chain_dir / "02" / "summary.json").read_text(encoding="utf-8"))
    apply_path = Path(second["apply_proposals_path"])
    assert apply_path == chain_dir / "01" / "applied_proposals.json"
    third = json.loads((chain_dir / "03" / "summary.json").read_text(encoding="utf-8"))
    assert Path(third["apply_proposals_path"]) == chain_dir / "02" / "applied_proposals.json"
    applied = json.loads(apply_path.read_text(encoding="utf-8"))
    assert all(c["change_kind"] != "set_parameter" for c in applied.get("changes") or [])
    assert all(c["change_kind"] != "graph_rewire" for c in applied.get("changes") or [])
    assert summary["verdict"] == VERDICT_INCONCLUSIVE
    assert (chain_dir / "baseline-replay" / "summary.json").exists()
    assert (chain_dir / "final-replay" / "summary.json").exists()


def test_design_iterate_no_paired_replay_is_inconclusive(tmp_path: Path):
    summary = run_design_iterate(
        iterations=1,
        chain_dir=tmp_path / "no-replay",
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="mock", steps=2),
        ),
        paired_replay=False,
    )
    assert summary["verdict"] == VERDICT_INCONCLUSIVE
    assert summary["replay_runs"] == []


def test_design_iterate_recreates_parent_directory(tmp_path: Path):
    chain_dir = tmp_path / "chain"
    chain_dir.mkdir()
    leftover = chain_dir / "99"
    leftover.mkdir()
    (leftover / "stale.txt").write_text("old\n", encoding="utf-8")
    run_design_iterate(
        iterations=1,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="mock", steps=2),
        ),
        recreate=True,
    )
    assert not leftover.exists()
    assert (chain_dir / "01" / "summary.json").exists()


def test_design_iterate_plant_sim_records_crew_remaining(tmp_path: Path):
    chain_dir = tmp_path / "plant-chain"
    summary = run_design_iterate(
        iterations=2,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides={
                **_labeled_overrides(backend="plant_sim", steps=50, inject_failures=True),
                "plant_sim": {"crew": {"size": 4}},
            },
        ),
    )
    assert summary["iterations_completed"] == 2
    first = json.loads((chain_dir / "01" / "summary.json").read_text(encoding="utf-8"))
    last = json.loads((chain_dir / "02" / "summary.json").read_text(encoding="utf-8"))
    assert first["crew_initial"] == 4
    assert "crew_remaining" in first
    assert "crew_remaining" in last
    assert last.get("inject_failures") is True
    assert summary["verdict"] in {"IMPROVED", "NOT_IMPROVED", VERDICT_INCONCLUSIVE}
    assert summary["crew_remaining_first"] == first["crew_remaining"]
    assert summary["crew_remaining_last"] == last["crew_remaining"]
    # Last sim verifies iteration-1 proposals; it may still emit unverified ones.
    assert last.get("apply_proposals_path")
    assert Path(last["apply_proposals_path"]).name == "applied_proposals.json"
    assert len(summary["replay_runs"]) == 2
    assert summary["replay_runs"][0]["design_mode"] == "none"
    assert summary["replay_runs"][1]["design_mode"] == "none"
    baseline = summary["crew_remaining_baseline_replay"]
    final_replay = summary["crew_remaining_final_replay"]
    if summary["verdict"] == "IMPROVED":
        assert final_replay > baseline
    elif summary["verdict"] == "NOT_IMPROVED":
        assert final_replay <= baseline
    final_apply = json.loads(
        (chain_dir / "final-replay" / "summary.json").read_text(encoding="utf-8")
    )
    verified = Path(last["apply_proposals_path"])
    assert Path(final_apply["apply_proposals_path"]) == verified


def test_design_iterate_continues_when_proposals_empty(tmp_path: Path):
    chain_dir = tmp_path / "empty-chain"
    overrides = _labeled_overrides(backend="mock", steps=2)
    overrides["agents"]["design"]["mode"] = "none"
    summary = run_design_iterate(
        iterations=3,
        chain_dir=chain_dir,
        base_spec=RunSpec(scenario="ssos_eclss_loop", overrides=overrides),
        paired_replay=False,
    )
    assert summary["iterations_completed"] == 3
    assert summary["stopped_reason"] == "paired replay disabled; no improvement claim"
    for index in (1, 2, 3):
        run_dir = chain_dir / f"{index:02d}"
        assert (run_dir / "summary.json").exists()
        assert not (run_dir / "design_proposals.json").exists()
        row = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        assert row.get("apply_proposals_path") in {None, ""}
        assert row.get("design_proposal_count", 0) == 0


def test_design_iterate_reports_step_and_iteration_progress(tmp_path: Path):
    class RecordingReporter(IterateReporter):
        def __init__(self) -> None:
            self.starts: list[tuple[int, str, str, int, int]] = []
            self.steps: list[tuple[int, int]] = []
            self.phases: list[str] = []
            self.ends: list[object] = []

        def on_run_start(
            self,
            *,
            index: int,
            total: int,
            label: str,
            steps: int,
            kind: str = "iteration",
        ) -> None:
            self.starts.append((index, kind, label, steps, total))

        def on_step(self, *, step: int, steps: int) -> None:
            self.steps.append((step, steps))

        def on_phase(self, detail: str) -> None:
            self.phases.append(detail)

        def on_run_end(self, row: dict) -> None:
            self.ends.append(row.get("iteration"))

    reporter = RecordingReporter()
    overrides = _labeled_overrides(backend="mock", steps=2)
    overrides["agents"]["design"]["mode"] = "none"
    run_design_iterate(
        iterations=2,
        chain_dir=tmp_path / "progress-chain",
        base_spec=RunSpec(scenario="ssos_eclss_loop", overrides=overrides),
        paired_replay=False,
        reporter=reporter,
    )
    assert [item[1] for item in reporter.starts] == ["iteration", "iteration"]
    assert [item[0] for item in reporter.starts] == [1, 2]
    assert reporter.steps == [(0, 2), (1, 2), (0, 2), (1, 2)]
    assert reporter.ends == [1, 2]


def test_design_llm_provenance_from_overrides():
    from scenario.jobs.iterate import design_llm_provenance

    assert design_llm_provenance(
        {"agents": {"design": {"llm": {"provider": "vllm", "model": "qwen", "temperature": 0.2}}}}
    ) == {"provider": "vllm", "model": "qwen", "temperature": 0.2}
