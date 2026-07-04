"""Tests for SSOS regression job spec building (scenario.jobs path)."""

from __future__ import annotations

import json
from pathlib import Path

from scenario.jobs.spec import RunSpec


def _build_regression_spec(
    *,
    backend: str = "ros2",
    agents_mode: str = "labeled_rule_base",
    steps: int | None = 5,
    output_dir: str | None = "/tmp/ea_regression/loop",
) -> RunSpec:
    """Mirror scripts/lib/ssos_docker.sh _ssos_write_job_spec."""
    overrides: dict = {
        "backend": {"kind": backend},
        "agents": {"mode": agents_mode},
    }
    if steps is not None:
        overrides["simulation"] = {"steps": steps}
    return RunSpec(
        scenario="ssos_eclss_loop",
        overrides=overrides,
        output_dir=Path(output_dir) if output_dir else None,
        recreate_output=True,
    )


def test_regression_job_spec_labeled_ros2():
    spec = _build_regression_spec()
    payload = json.loads(spec.to_json())
    assert payload["scenario"] == "ssos_eclss_loop"
    assert payload["overrides"]["backend"]["kind"] == "ros2"
    assert payload["overrides"]["agents"]["mode"] == "labeled_rule_base"
    assert payload["overrides"]["simulation"]["steps"] == 5
    assert payload["output_dir"] == "/tmp/ea_regression/loop"
    assert payload["recreate_output"] is True


def test_regression_job_spec_llm(tmp_path: Path):
    spec = _build_regression_spec(
        agents_mode="llm",
        steps=3,
        output_dir=str(tmp_path / "llm"),
    )
    payload = json.loads(spec.to_json())
    assert payload["overrides"]["agents"]["mode"] == "llm"
    assert payload["overrides"]["simulation"]["steps"] == 3
