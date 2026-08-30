"""Chained ssos_eclss_loop design iterate runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scenario.jobs.iterate import VERDICT_INCONCLUSIVE, resolve_iteration, run_design_iterate
from scenario.jobs.progress import IterateReporter
from scenario.jobs.spec import RunSpec
from scenario.ssos_eclss_loop.chain_memory import (
    CHAIN_MEMORY_FILENAME,
    MAX_MEMORY_BYTES,
    load_chain_memory,
)


def test_resolve_iteration_disabled_without_cli():
    settings = resolve_iteration(
        {"iteration": {"enabled": False, "count": 5, "paired_replay": True}}
    )
    assert settings.chain is False
    assert settings.count == 5


def test_resolve_iteration_cli_iterate_enables_chain():
    settings = resolve_iteration(
        {"iteration": {"enabled": False, "count": 5}},
        cli_iterate=10,
    )
    assert settings.chain is True
    assert settings.count == 10


def test_resolve_iteration_yaml_enabled():
    settings = resolve_iteration({"iteration": {"enabled": True, "count": 3}})
    assert settings.chain is True
    assert settings.count == 3
    assert "defaults" not in settings.as_dict()


def test_resolve_iteration_cli_flags_override_yaml():
    settings = resolve_iteration(
        {
            "iteration": {
                "enabled": True,
                "count": 5,
                "paired_replay": True,
                "approve_provisional": True,
                "run_id": "from-yaml",
            }
        },
        cli_paired_replay=False,
        cli_approve_provisional=False,
        cli_run_id="from-cli",
    )
    assert settings.paired_replay is False
    assert settings.approve_provisional is False
    assert settings.run_id == "from-cli"


def test_resolve_iteration_missing_block_does_not_chain():
    settings = resolve_iteration({})
    assert settings.chain is False


def test_resolve_iteration_rejects_defaults_block():
    with pytest.raises(ValueError, match="iteration.defaults was removed"):
        resolve_iteration({"iteration": {"defaults": {"inject_failures": True}}})


def test_resolve_iteration_count_out_of_range_when_chaining():
    with pytest.raises(ValueError, match="1–50"):
        resolve_iteration({"iteration": {"enabled": True, "count": 99}})


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
                "tool_use": {"enabled": False},
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
        iteration_record={"chain": True, "count": 3},
        measure_limits=False,
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
    assert applied.get("changes")
    assert summary["verdict"] == VERDICT_INCONCLUSIVE
    assert summary["iteration"]["count"] == 3
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


def test_iterate_apply_document_drops_thresholds_and_blocks_provisional():
    from scenario.jobs.iterate import iterate_apply_document

    adopted = iterate_apply_document(
        {
            "design_domain": "ssos_graph",
            "changes": [
                {
                    "change_kind": "action_profile",
                    "payload": {
                        "subsystem": "ars",
                        "action": "air_revitalisation",
                        "fields": {"initial_co2_mass": 2.0},
                    },
                },
                {
                    "change_kind": "set_parameter",
                    "payload": {"target": "thresholds.co2_storage_high_kg", "value": 1.0},
                },
                {
                    "change_kind": "capacity_profile",
                    "payload": {
                        "backend": "plant_sim",
                        "fields": {"plant_sim.ars.capacity_kg_day": 4.0},
                    },
                },
            ],
        }
    )
    assert adopted is not None
    kinds = [c["change_kind"] for c in adopted["changes"]]
    assert "set_parameter" not in kinds
    assert "action_profile" in kinds
    assert "capacity_profile" in kinds

    blocked = iterate_apply_document(
        {
            "design_domain": "ssos_graph",
            "final_status": "provisional_final",
            "changes": [
                {
                    "change_kind": "action_profile",
                    "payload": {
                        "subsystem": "ars",
                        "action": "air_revitalisation",
                        "fields": {"initial_co2_mass": 2.0},
                    },
                }
            ],
        }
    )
    assert blocked is None

    approved = iterate_apply_document(
        {
            "design_domain": "ssos_graph",
            "final_status": "provisional_final",
            "changes": [
                {
                    "change_kind": "action_profile",
                    "payload": {
                        "subsystem": "ars",
                        "action": "air_revitalisation",
                        "fields": {"initial_co2_mass": 2.0},
                    },
                }
            ],
        },
        approve_provisional=True,
    )
    assert approved is not None


def test_the_chain_leaves_each_round_a_note_from_the_ones_before_it(tmp_path: Path):
    """Iterations read only their own run, so what carries over has to be written.

    Without this a design that kept the whole crew alive is gone the moment the
    next iteration proposes something else, and nothing in the chain can tell
    the designer that it ever existed.
    """
    chain_dir = tmp_path / "chain"
    run_design_iterate(
        iterations=3,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="mock", steps=4),
        ),
        paired_replay=False,
    )

    note = chain_dir / CHAIN_MEMORY_FILENAME
    assert note.exists()
    # One file at the root, updated in place -- not a copy under each iteration.
    assert not (chain_dir / "01" / CHAIN_MEMORY_FILENAME).exists()
    assert note.stat().st_size <= MAX_MEMORY_BYTES

    memory = json.loads(note.read_text(encoding="utf-8"))
    assert memory["schema_version"] == "1.0"
    assert memory["updated_after_iteration"] == 3
    assert memory["objective"]["primary"] == "maximize_crew_remaining"
    assert memory["proposal_guidance"]["prefer_complete_capacity_profile"] is True
    # What was installed for the last round, read off its config.
    last = memory["last_effective_design"]
    assert last["iteration"] == 3
    assert set(last["fields"]) == {
        "plant_sim.ars.capacity_kg_day",
        "plant_sim.ogs.max_o2_kg_day",
        "plant_sim.wrs.max_feed_l_per_operation",
    }
    # Every iteration after the first can see it from its own run directory.
    for index in (1, 2, 3):
        assert load_chain_memory(chain_dir / f"{index:02d}") == memory


def test_the_chain_measures_its_own_limits_before_designing_against_them(tmp_path: Path):
    """Where each subsystem stops working is found by trying it, once, up front.

    It used to be calculated and asserted. The calculation was wrong for the
    water recycler, and because it arrived as a rule rather than a result, no
    round of an observed fifty-iteration chain ever tested any of the three.
    """
    from scenario.ssos_eclss_loop.floor_probe import MEASURED_LIMITS_FILENAME

    chain_dir = tmp_path / "chain"
    summary = run_design_iterate(
        iterations=2,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="plant_sim", steps=8, inject_failures=False),
        ),
        paired_replay=False,
    )

    path = chain_dir / MEASURED_LIMITS_FILENAME
    assert path.exists()
    measured = json.loads(path.read_text(encoding="utf-8"))
    assert measured["simulations"] > 0
    assert set(measured["smallest_surviving_machine"]) == {
        "plant_sim.ars.capacity_kg_day",
        "plant_sim.ogs.max_o2_kg_day",
        "plant_sim.wrs.max_feed_l_per_operation",
    }
    assert summary["survival_limits"]["status"] == measured["status"]

    # And what was measured reaches the round that has to design against it.
    memory = load_chain_memory(chain_dir / "02")
    limits = memory["measured_limits"]
    assert limits["by_subsystem"]
    for row in limits["by_subsystem"].values():
        assert "smallest_that_kept_everyone" in row
    # Observations, not instructions.
    assert "do_not_reduce_below_best_without_reason" not in memory["proposal_guidance"]


def test_the_chain_hands_on_a_whole_machine_not_just_what_changed(tmp_path: Path):
    chain_dir = tmp_path / "chain"
    run_design_iterate(
        iterations=2,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="mock", steps=4),
        ),
        paired_replay=False,
        measure_limits=False,
    )
    applied = json.loads(
        (chain_dir / "01" / "applied_proposals.json").read_text(encoding="utf-8")
    )
    capacity = [c for c in applied["changes"] if c["change_kind"] == "capacity_profile"]
    for change in capacity:
        assert set(change["payload"]["fields"]) == {
            "plant_sim.ars.capacity_kg_day",
            "plant_sim.ogs.max_o2_kg_day",
            "plant_sim.wrs.max_feed_l_per_operation",
        }


def test_the_chain_writes_a_final_answer_beside_its_verdict(tmp_path: Path):
    """A chain that improved still has to say what to build, or that it cannot.

    The verdict answers "did this get anywhere". It is not an answer to "what
    do we build", and a run that reports only the verdict leaves the reader to
    guess which design it meant.
    """
    chain_dir = tmp_path / "chain"
    summary = run_design_iterate(
        iterations=2,
        chain_dir=chain_dir,
        base_spec=RunSpec(
            scenario="ssos_eclss_loop",
            overrides=_labeled_overrides(backend="mock", steps=4),
        ),
        paired_replay=False,
    )

    answer_path = chain_dir / "chain_final_answer.json"
    assert answer_path.exists()
    answer = json.loads(answer_path.read_text(encoding="utf-8"))
    assert answer["iterations_considered"] == 2
    assert answer["status"] in {
        "approved_final",
        "provisional_final",
        "rejected_final",
        "not_comparable",
    }
    # Whatever it decided, the chain summary carries it and points at the file.
    assert summary["final_answer"]["status"] == answer["status"]
    assert Path(summary["final_answer"]["path"]) == answer_path
    # A design is only handed over if it kept everyone alive.
    selected = answer.get("selected")
    if selected is not None:
        assert selected["crew_remaining"] == selected["crew_initial"]
