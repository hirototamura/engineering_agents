from __future__ import annotations

import pathlib
import subprocess
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, check=check, capture_output=False)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if old not in content:
        raise RuntimeError(f"needle not found in {path}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


def rejection_reason_expr() -> str:
    return ""  # marker only


# Merge #62 into the #61-derived integration branch. Resolve only the known
# overlapping files here; any new conflict is a hard failure so we do not hide
# upstream changes.
run("git", "fetch", "origin", "feat/eclss-evaluation-scorecard", "trunk")
merge = run("git", "merge", "--no-commit", "--no-ff", "origin/feat/eclss-evaluation-scorecard", check=False)
conflicts = subprocess.check_output(
    ["git", "diff", "--name-only", "--diff-filter=U"], cwd=ROOT, text=True
).splitlines()
known = {
    ".gitignore",
    "src/environment/ssos/eclss/plant_sim/backend.py",
    "src/scenario/ssos_eclss_loop/scenario.yaml",
    "src/scenario/ssos_eclss_loop/scenario_run.py",
}
unknown = sorted(set(conflicts) - known)
if unknown:
    raise RuntimeError(f"unexpected merge conflicts: {unknown}")
for path in conflicts:
    run("git", "checkout", "--ours", "--", path)

# .gitignore: retain #61 ignores and keep the #62 checked-in evaluation browser.
gitignore = read(".gitignore")
line = "!src/experiments/results/evaluation.html"
if line not in gitignore:
    marker = "!src/experiments/results/.gitkeep"
    if marker in gitignore:
        gitignore = gitignore.replace(marker, marker + "\n" + line, 1)
    else:
        gitignore += "\n" + line + "\n"
    write(".gitignore", gitignore)

# plant_sim backend: keep #61 busy guard and add #62 audit ledgers.
backend_path = "src/environment/ssos/eclss/plant_sim/backend.py"
backend = read(backend_path)
if '"initial_captured_co2_kg"' not in backend:
    needle = '            "simulation_time_s": s.simulation_time_s,\n'
    ledger = '''            "simulation_time_s": s.simulation_time_s,\n            # Persist enough cumulative bookkeeping for the deterministic\n            # evaluator to independently audit each candidate run.\n            "initial_captured_co2_kg": self.config.initial_captured_co2_kg,\n            "initial_urine_buffer_l": self.config.initial_urine_buffer_l,\n            "initial_grey_water_l": self.config.initial_grey_water_l,\n'''
    backend = backend.replace(needle, ledger, 1)
    needle2 = '            "total_water_shortfall_l": s.total_water_shortfall_l,\n'
    ledger2 = '''            "total_water_shortfall_l": s.total_water_shortfall_l,\n            "total_unrecoverable_crew_water_l": s.total_unrecoverable_crew_water_l,\n            "total_co2_generated_kg": s.total_co2_generated_kg,\n            "total_o2_consumed_kg": s.total_o2_consumed_kg,\n            "total_potable_water_consumed_l": s.total_potable_water_consumed_l,\n            "total_urine_generated_l": s.total_urine_generated_l,\n            "total_condensate_generated_l": s.total_condensate_generated_l,\n            "total_o2_generated_kg": s.total_o2_generated_kg,\n            "total_electrolysis_water_kg": s.total_electrolysis_water_kg,\n            "total_sabatier_co2_used_kg": s.total_sabatier_co2_used_kg,\n            "total_water_regenerated_l": s.total_water_regenerated_l,\n            "total_wrs_recovered_water_l": s.total_wrs_recovered_water_l,\n            "total_o2_delivered_kg": s.total_o2_delivered_kg,\n            "total_co2_delivered_kg": s.total_co2_delivered_kg,\n            "total_product_water_delivered_l": s.total_product_water_delivered_l,\n            "total_external_grey_water_submitted_l": s.total_external_grey_water_submitted_l,\n'''
    if needle2 not in backend:
        raise RuntimeError("plant_sim ledger insertion point missing")
    backend = backend.replace(needle2, ledger2, 1)
    write(backend_path, backend)

# scenario.yaml: preserve #61 design constraints and append #62 evaluation config.
scenario_path = "src/scenario/ssos_eclss_loop/scenario.yaml"
scenario = read(scenario_path)
if "\nevaluation:\n" not in scenario:
    theirs = subprocess.check_output(
        ["git", "show", "origin/feat/eclss-evaluation-scorecard:" + scenario_path],
        cwd=ROOT,
        text=True,
    )
    block_start = theirs.index("# Deterministic post-run scorecard")
    block_end = theirs.index("\nagents:\n", block_start)
    eval_block = theirs[block_start:block_end].rstrip() + "\n\n"
    marker = "\nagents:\n"
    if marker not in scenario:
        raise RuntimeError("agents marker missing in scenario.yaml")
    scenario = scenario.replace(marker, "\n" + eval_block + "agents:\n", 1)
    write(scenario_path, scenario)

# Shared wrapper around #62's evaluator. It derives command bounds from the
# installed candidate configuration and attributes busy/duplicate rejection to
# actor scheduling rather than device response.
unified = r'''"""Integration layer between deterministic run evaluation and tool-use design.

The canonical score formulas remain in :mod:`evaluation`. This module only adapts
run-specific design capacity into actor command validity, reconciles execution-gate
rejections, writes the canonical evaluation artifacts, and exposes a compact diagnosis
to the design agent through ``summary.json``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Mapping

from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2
from scenario.ssos_eclss_loop.evaluation import (
    OPERATIONAL_APPLIED,
    OPERATIONAL_REJECTED,
    _response_quality,
    evaluate_run,
)
from scenario.ssos_eclss_loop.evaluation_browser import write_evaluation_browser
from scenario.ssos_eclss_loop.evaluation_html import render_evaluation_html

_SCHEDULING_REJECTIONS = {"subsystem_busy", "duplicate_command_this_step"}
_SECONDS_PER_DAY = 86400.0


def _finite(value: Any) -> bool:
    try:
        import math
        return not isinstance(value, bool) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _raise_upper(bounds: Dict[str, Any], kind: str, field: str, derived: float) -> None:
    command = bounds.setdefault(kind, {})
    limits = command.get(field)
    lower = 0.0
    upper = 0.0
    if isinstance(limits, (list, tuple)) and len(limits) == 2:
        lower = float(limits[0]) if _finite(limits[0]) else 0.0
        upper = float(limits[1]) if _finite(limits[1]) else 0.0
    command[field] = [lower, max(upper, float(derived) * 1.05)]


def capacity_aware_config(scenario_config: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an evaluation config whose actor payload bounds follow installed hardware."""
    config = copy.deepcopy(dict(scenario_config))
    evaluation = config.setdefault("evaluation", {})
    decision = evaluation.setdefault("actor_decision", {})
    bounds = decision.setdefault("command_bounds", {})
    plant = config.get("plant_sim") if isinstance(config.get("plant_sim"), Mapping) else {}
    time_cfg = plant.get("time") if isinstance(plant.get("time"), Mapping) else {}
    ogs = plant.get("ogs") if isinstance(plant.get("ogs"), Mapping) else {}
    wrs = plant.get("wrs") if isinstance(plant.get("wrs"), Mapping) else {}

    ogs_day = float(ogs.get("max_o2_kg_day", 0.0) or 0.0)
    ogs_seconds = float(time_cfg.get("ogs_operation_seconds", 1200.0) or 1200.0)
    water_per_operation = max(0.0, ogs_day * ogs_seconds / _SECONDS_PER_DAY * WATER_PER_O2)
    _raise_upper(bounds, "oxygen_generation", "input_water_mass", water_per_operation)

    wrs_batch = max(0.0, float(wrs.get("max_feed_l_per_operation", 0.0) or 0.0))
    _raise_upper(bounds, "water_recovery", "urine_volume", wrs_batch)
    return config


def _read_jsonl(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _rejection_reason(event: Mapping[str, Any]) -> str | None:
    reason = event.get("reason")
    if reason:
        return str(reason)
    result = event.get("result") if isinstance(event.get("result"), Mapping) else {}
    details = result.get("details") if isinstance(result.get("details"), Mapping) else {}
    reason = details.get("reason")
    return str(reason) if reason else None


def reconcile_scheduler_semantics(
    payload: Dict[str, Any], run_dir: Path, evaluation_config: Mapping[str, Any]
) -> Dict[str, Any]:
    """Treat execution-gate rejection as actor scheduling evidence, not device failure."""
    axes = ((payload.get("scores") or {}).get("axes") or {})
    decision = axes.get("actor_decision")
    if not isinstance(decision, dict):
        return payload
    metrics = decision.get("metrics") if isinstance(decision.get("metrics"), dict) else {}
    attempts = metrics.get("attempts") if isinstance(metrics.get("attempts"), list) else []
    events = [
        event
        for event in _read_jsonl(Path(run_dir) / "events.jsonl")
        if event.get("kind") in {OPERATIONAL_APPLIED, OPERATIONAL_REJECTED}
    ]
    if len(attempts) != len(events):
        return payload

    for attempt, event in zip(attempts, events):
        reason = _rejection_reason(event)
        if reason not in _SCHEDULING_REJECTIONS:
            continue
        attempt["valid"] = False
        reasons = attempt.setdefault("reasons", [])
        if reason not in reasons:
            reasons.append(reason)

    validity = sum(1 for item in attempts if item.get("valid")) / len(attempts) if attempts else 1.0
    latency = float(metrics.get("latency_quality", 1.0) or 0.0)
    latency_weight = float(((evaluation_config.get("actor_decision") or {}).get("latency_weight", 0.5)))
    latency_weight = max(0.0, min(1.0, latency_weight))
    metrics["validity_quality"] = round(validity, 6)
    decision["score"] = round(10.0 * (latency_weight * latency + (1.0 - latency_weight) * validity), 6)

    response = axes.get("physical_response")
    if isinstance(response, dict):
        eligible = []
        for attempt, event in zip(attempts, events):
            if _rejection_reason(event) in _SCHEDULING_REJECTIONS:
                continue
            if attempt.get("valid"):
                eligible.append(event)
        if not eligible:
            response.update(
                {
                    "status": "not_observed",
                    "score": None,
                    "max_score": 10,
                    "metrics": {"valid_operation_count": 0, "operations": []},
                }
            )
        else:
            operations = [_response_quality(event, evaluation_config) for event in eligible]
            score = 10.0 * sum(float(item.get("quality") or 0.0) for item in operations) / len(operations)
            response.update(
                {
                    "status": "scored",
                    "score": round(score, 6),
                    "max_score": 10,
                    "metrics": {"valid_operation_count": len(operations), "operations": operations},
                }
            )

    all_scores = [axis.get("score") for axis in axes.values()]
    complete = all(_finite(score) for score in all_scores)
    payload["scores"]["total"] = round(sum(float(score) for score in all_scores), 6) if complete else None
    payload["status"] = "scored" if complete else "incomplete"
    return payload


def compact_evaluation(payload: Mapping[str, Any]) -> Dict[str, Any]:
    scores = payload.get("scores") if isinstance(payload.get("scores"), Mapping) else {}
    axes = scores.get("axes") if isinstance(scores.get("axes"), Mapping) else {}
    survival = axes.get("actor_survival") if isinstance(axes.get("actor_survival"), Mapping) else {}
    trajectory = axes.get("environment_trajectory") if isinstance(axes.get("environment_trajectory"), Mapping) else {}
    recovery = axes.get("resource_recovery") if isinstance(axes.get("resource_recovery"), Mapping) else {}
    decision = axes.get("actor_decision") if isinstance(axes.get("actor_decision"), Mapping) else {}
    response = axes.get("physical_response") if isinstance(axes.get("physical_response"), Mapping) else {}
    return {
        "status": payload.get("status"),
        "physics_gate_passed": bool((payload.get("physics_gate") or {}).get("passed", False)),
        "score": scores.get("total"),
        "max_score": scores.get("max_score"),
        "survival": survival.get("metrics"),
        "tcl": (axes.get("tcl") or {}).get("metrics") if isinstance(axes.get("tcl"), Mapping) else None,
        "environment": trajectory.get("metrics"),
        "resource_recovery": recovery.get("metrics"),
        "actor_decision": decision.get("metrics"),
        "device_response": response.get("metrics"),
    }


def finalize_run_evaluation(
    run_dir: Path,
    *,
    scenario_config: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate one completed run before design and return an enriched summary."""
    run_path = Path(run_dir)
    config = capacity_aware_config(scenario_config)
    payload = evaluate_run(run_path, scenario_config=config, summary=summary)
    payload = reconcile_scheduler_semantics(payload, run_path, config.get("evaluation") or {})

    json_path = run_path / "evaluation.json"
    html_path = run_path / "evaluation.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_evaluation_html(payload), encoding="utf-8")
    write_evaluation_browser(run_path.parent, default_run_id=run_path.name)

    updated = dict(summary)
    score_block = payload.get("scores") if isinstance(payload.get("scores"), Mapping) else {}
    updated.update(
        {
            "evaluation_path": str(json_path),
            "evaluation_html_path": str(html_path),
            "evaluation_status": payload.get("status"),
            "evaluation_score": score_block.get("total"),
            "evaluation_max_score": score_block.get("max_score"),
            "physics_gate_passed": bool((payload.get("physics_gate") or {}).get("passed", False)),
            "evaluation_compact": compact_evaluation(payload),
        }
    )
    return updated


__all__ = [
    "capacity_aware_config",
    "compact_evaluation",
    "finalize_run_evaluation",
    "reconcile_scheduler_semantics",
]
'''
write("src/scenario/ssos_eclss_loop/unified_evaluation.py", unified)

# Run evaluator BEFORE the tool-use designer. Candidate runs use the same
# scenario runner with design disabled, so they automatically receive identical
# evaluation artifacts before run_design_candidate inspects them.
run_path = "src/scenario/ssos_eclss_loop/scenario_run.py"
run_text = read(run_path)
import_marker = "from scenario.ssos_eclss_loop.design_proposals import (\n"
if "from scenario.ssos_eclss_loop.unified_evaluation import finalize_run_evaluation" not in run_text:
    pos = run_text.index(import_marker)
    # Insert after the design_proposals import block rather than parsing imports.
    end = run_text.index("\n)\n", pos) + len("\n)\n")
    run_text = (
        run_text[:end]
        + "from scenario.ssos_eclss_loop.unified_evaluation import finalize_run_evaluation\n"
        + run_text[end:]
    )

needle = '        if design_mode in {"labeled_rule_base", "llm"} and agents_config:\n'
if "summary = finalize_run_evaluation(" not in run_text:
    evaluation_call = '''        # Canonical run measurement precedes design reasoning. The tool-use\n        # designer therefore sees the same deterministic diagnosis used by the\n        # dashboard, and candidate runs are evaluated identically.\n        summary = finalize_run_evaluation(\n            run_dir, scenario_config=config, summary=summary\n        )\n\n'''
    if needle not in run_text:
        raise RuntimeError("design block marker missing from scenario_run.py")
    run_text = run_text.replace(needle, evaluation_call + needle, 1)
write(run_path, run_text)

# Expose evaluator results through the existing design feature/candidate tools and
# make physics validity a hard design eligibility condition. The total score is
# deliberately NOT a ranking key.
design_eval_path = "src/scenario/ssos_eclss_loop/design_eval.py"
design_eval = read(design_eval_path)
if '"physics_gate_passed": summary.get("physics_gate_passed")' not in design_eval:
    marker = '        "design_mode": summary.get("design_mode"),\n'
    addition = '''        "design_mode": summary.get("design_mode"),\n        "physics_gate_passed": summary.get("physics_gate_passed"),\n        "evaluation_status": summary.get("evaluation_status"),\n        "evaluation_score": summary.get("evaluation_score"),\n        "evaluation_compact": summary.get("evaluation_compact"),\n'''
    if marker not in design_eval:
        raise RuntimeError("design outcome marker missing")
    design_eval = design_eval.replace(marker, addition, 1)

if 'reasons.append("physics_gate_not_passed")' not in design_eval:
    marker = '    if not evidence_complete:\n        reasons.append("evidence_incomplete")\n\n'
    addition = '''    if not evidence_complete:\n        reasons.append("evidence_incomplete")\n\n    # The deterministic evaluator is a measurement gate, not a score objective.\n    # A plant_sim candidate whose persisted physics cannot be audited is never\n    # eligible regardless of survival, mass, or model-written prose.\n    if outcome.get("backend") == "plant_sim" and outcome.get("physics_gate_passed") is not True:\n        reasons.append("physics_gate_not_passed")\n\n'''
    if marker not in design_eval:
        raise RuntimeError("eligibility marker missing")
    design_eval = design_eval.replace(marker, addition, 1)
write(design_eval_path, design_eval)

# Surface compact evaluation in candidate comparison output without using score
# as an objective. compute_eclss_features already returns `outcome`, so it now
# carries the canonical evaluator diagnosis too.
design_tools_path = "src/scenario/ssos_eclss_loop/design_tools.py"
design_tools = read(design_tools_path)
if '"physics_gate_passed": outcome.get("physics_gate_passed")' not in design_tools:
    marker = '            "final_product_water_reserve_l": outcome.get("final_product_water_reserve_l"),\n'
    addition = '''            "final_product_water_reserve_l": outcome.get("final_product_water_reserve_l"),\n            "physics_gate_passed": outcome.get("physics_gate_passed"),\n            "evaluation_compact": outcome.get("evaluation_compact"),\n'''
    if marker not in design_tools:
        raise RuntimeError("ranking row marker missing")
    design_tools = design_tools.replace(marker, addition, 1)
write(design_tools_path, design_tools)

# Integration-specific tests. Existing #61/#62 suites remain the primary
# regression net; these cover the semantic contract between them.
test_text = r'''from __future__ import annotations

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
'''
write("tests/scenario/test_ssos_unified_design_evaluation.py", test_text)

# Resolve all merge paths and make sure no conflict markers survived.
run("git", "add", "-A")
remaining = subprocess.check_output(
    ["git", "diff", "--name-only", "--diff-filter=U"], cwd=ROOT, text=True
).strip()
if remaining:
    raise RuntimeError(f"unresolved conflicts remain: {remaining}")
