from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from scenario.ssos_eclss_loop.design_eval import mark_final_eligibility
from scenario.ssos_eclss_loop.unified_evaluation import (
    capacity_aware_config,
    reconcile_scheduler_semantics,
)


def _scenario() -> dict:
    path = Path(__file__).parents[2] / "src" / "scenario" / "ssos_eclss_loop" / "scenario.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_capacity_aware_command_bounds_follow_candidate_hardware():
    config = _scenario()
    config = copy.deepcopy(config)
    config["plant_sim"]["ogs"]["max_o2_kg_day"] = 80.0
    config["plant_sim"]["wrs"]["max_feed_l_per_operation"] = 20.0
    prepared = capacity_aware_config(config)
    bounds = prepared["evaluation"]["actor_decision"]["command_bounds"]
    assert bounds["oxygen_generation"]["input_water_mass"][1] > 1.0
    assert bounds["water_recovery"]["urine_volume"][1] >= 20.0


def test_scheduler_rejection_penalizes_actor_not_device(tmp_path: Path):
    event = {
        "step": 3,
        "kind": "/eclss/events/operational_rejected",
        "command": {"kind": "air_revitalisation", "payload": {"initial_co2_mass": 1.8}},
        "result": {"success": False, "details": {"reason": "subsystem_busy"}},
    }
    (tmp_path / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    payload = {
        "status": "scored",
        "scores": {
            "total": 20.0,
            "max_score": 100,
            "axes": {
                "actor_decision": {
                    "status": "scored",
                    "score": 10.0,
                    "max_score": 10,
                    "metrics": {
                        "latency_quality": 1.0,
                        "validity_quality": 1.0,
                        "episodes": [],
                        "attempts": [{"step": 3, "kind": "air_revitalisation", "valid": True, "reasons": []}],
                    },
                },
                "physical_response": {
                    "status": "scored",
                    "score": 10.0,
                    "max_score": 10,
                    "metrics": {"valid_operation_count": 1, "operations": []},
                },
            },
        },
    }
    result = reconcile_scheduler_semantics(
        payload, tmp_path, {"actor_decision": {"latency_weight": 0.5}}
    )
    attempt = result["scores"]["axes"]["actor_decision"]["metrics"]["attempts"][0]
    assert attempt["valid"] is False
    assert "subsystem_busy" in attempt["reasons"]
    response = result["scores"]["axes"]["physical_response"]
    assert response["status"] == "not_observed"
    assert response["score"] is None


def test_physics_gate_is_hard_design_eligibility_not_score():
    record = {
        "simulated": True,
        "constraint_evaluation": {"preflight_status": "valid", "constraint_status": "feasible"},
        "outcome": {
            "backend": "plant_sim",
            "crew_initial": 50,
            "crew_remaining": 50,
            "physics_gate_passed": False,
            "evaluation_score": 100.0,
        },
    }
    marked = mark_final_eligibility(
        record,
        baseline_outcome={"crew_initial": 50, "crew_remaining": 0},
        evidence_complete=True,
    )
    assert marked["final_eligible"] is False
    assert "physics_gate_not_passed" in marked["final_ineligible_reasons"]


def test_run_writes_one_evaluation_that_matches_its_summary(tmp_path: Path):
    """summary.json and evaluation.json must describe the same measurement.

    The evaluator ran twice per run: once through the unified entry before the
    design pass, then again afterwards with a differently prepared config. The
    second write replaced the first, so the score a human opened was not the
    score the designer reasoned from.
    """
    from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

    run_dir = SsosEclssLoopScenario().run(
        output_dir=tmp_path / "run",
        overrides={
            "simulation": {"steps": 6},
            "backend": {"kind": "plant_sim"},
            "agents": {"actor": {"mode": "labeled_rule_base"}, "design": {"mode": "none"}},
        },
        recreate_output=True,
    )

    # Guard against a vacuous assertion: the two evaluators only disagree when
    # the run contains execution-gate rejections, so require some.
    events = [
        json.loads(line)
        for line in (Path(run_dir) / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scheduling = [
        event
        for event in events
        if ((event.get("result") or {}).get("details") or {}).get("reason")
        in {"subsystem_busy", "duplicate_command_this_step"}
    ]
    assert scheduling, "run produced no scheduling rejection; the assertion below proves nothing"

    summary = json.loads((Path(run_dir) / "summary.json").read_text(encoding="utf-8"))
    evaluation = json.loads((Path(run_dir) / "evaluation.json").read_text(encoding="utf-8"))

    assert summary["evaluation_score"] == evaluation["scores"]["total"]
    assert summary["evaluation_compact"]["score"] == evaluation["scores"]["total"]
    assert summary["evaluation_status"] == evaluation["status"]
