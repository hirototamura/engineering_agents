"""Provenance export tests for EPS recovery traces (EPS-4)."""

from __future__ import annotations

import json
from pathlib import Path

from integrations.one_piece.client import build_provenance_records
from scenario.runner import run_scenario


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_build_provenance_includes_eps_recovery_record(tmp_path: Path):
    run_dir = run_scenario(
        "scrubber_degradation",
        output_dir=tmp_path / "labeled",
        overrides={"agents": {"mode": "labeled_rule_base"}},
        recreate_output=True,
    )
    records = build_provenance_records(run_dir)
    recovery = [r for r in records if r.get("change_kind") == "request_eps_boost"]
    assert recovery, "expected EPS boost recovery provenance"
    assert recovery[0]["record_type"] == "recovery"
    assert recovery[0]["trace"]["event_kind"] == "/eclss/events/recovery_applied"
    assert recovery[0]["actor"].startswith("engineer_")
    assert recovery[0]["trace"]["message"]
    assert recovery[0]["trace"]["reasoning"]
    assert recovery[0]["trace"]["decision_source"] == "rule"
