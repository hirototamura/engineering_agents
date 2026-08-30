"""Unit tests for the analysis experiment harness CLI construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.analysis.design_space import CAPACITY_AXES
from tools.analysis.experiments import (
    RunSpec,
    _command,
    capacity_set_flags,
    chain_specs,
    execute,
)


START = {
    "plant_sim.ars.capacity_kg_day": 26.0,
    "plant_sim.ogs.max_o2_kg_day": 42.0,
}


def test_capacity_set_flags_emit_every_named_axis():
    flags = capacity_set_flags(START)
    assert flags == [
        "--set", "plant_sim.ars.capacity_kg_day=26.0",
        "--set", "plant_sim.ogs.max_o2_kg_day=42.0",
    ]


def test_capacity_set_flags_reject_unknown_axes():
    with pytest.raises(ValueError, match="not design variables"):
        capacity_set_flags({"plant_sim.not_an_axis": 1.0})


def test_iterate_command_bakes_start_capacity_as_set_not_proposals(tmp_path):
    spec = chain_specs((3,), start_capacity=START)[0]
    proposal = tmp_path / "must-not-be-used.json"
    cmd = _command(spec, tmp_path / spec.run_id, proposal)
    joined = " ".join(cmd)
    assert "--iterate" in cmd
    assert "--apply-proposals" not in cmd
    assert str(proposal) not in cmd
    assert "plant_sim.ars.capacity_kg_day=26.0" in joined
    assert "plant_sim.ogs.max_o2_kg_day=42.0" in joined
    for axis in CAPACITY_AXES:
        if axis not in START:
            assert axis not in joined


def test_single_run_command_still_uses_apply_proposals(tmp_path):
    spec = RunSpec(run_id="grid-01", capacity=dict(START))
    proposal = tmp_path / "grid-01.json"
    cmd = _command(spec, tmp_path / spec.run_id, proposal)
    assert "--apply-proposals" in cmd
    assert str(proposal) in cmd
    assert "--iterate" not in cmd
    assert "plant_sim.ars.capacity_kg_day=" not in " ".join(cmd)


def test_execute_does_not_write_a_proposal_file_for_iterate(tmp_path, monkeypatch):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class Result:
            returncode = 0
            stderr = ""

        (tmp_path / "chain-labeled_rule_base-n03").mkdir()
        return Result()

    monkeypatch.setattr("tools.analysis.experiments.subprocess.run", fake_run)
    spec = chain_specs((3,), start_capacity=START)[0]
    outcome = execute(spec, tmp_path, cache=False)
    assert outcome.ok
    assert "--apply-proposals" not in captured["cmd"]
    assert not (tmp_path / "_proposals").exists()
    assert "plant_sim.ogs.max_o2_kg_day=42.0" in " ".join(captured["cmd"])
