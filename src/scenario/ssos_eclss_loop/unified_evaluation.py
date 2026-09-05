"""Integration layer between deterministic run evaluation and tool-use design.

The canonical score formulas remain in :mod:`evaluation`. This module only adapts
run-specific design capacity into actor command validity, reconciles execution-gate
rejections, writes the canonical evaluation artifacts, and exposes a compact diagnosis
to the design agent through ``summary.json``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2
from scenario.ssos_eclss_loop.evaluation import (
    DECISION_MAX,
    OPERATIONAL_APPLIED,
    OPERATIONAL_REJECTED,
    RESPONSE_MAX,
    _response_quality,
    evaluate_run,
)
from scenario.ssos_eclss_loop.evaluation_browser import write_evaluation_browser
from scenario.ssos_eclss_loop.evaluation_html import render_evaluation_html
from scenario.ssos_eclss_loop.integrity_guard import evidence_status, integrity_summary
from scenario.ssos_eclss_loop.physics_gate import run_physics_gate

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
    decision["score"] = round(
        DECISION_MAX * (latency_weight * latency + (1.0 - latency_weight) * validity), 6
    )

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
                    "max_score": RESPONSE_MAX,
                    "metrics": {"valid_operation_count": 0, "operations": []},
                }
            )
        else:
            operations = [_response_quality(event, evaluation_config) for event in eligible]
            score = (
                RESPONSE_MAX
                * sum(float(item.get("quality") or 0.0) for item in operations)
                / len(operations)
            )
            response.update(
                {
                    "status": "scored",
                    "score": round(score, 6),
                    "max_score": RESPONSE_MAX,
                    "metrics": {"valid_operation_count": len(operations), "operations": operations},
                }
            )

    all_scores = [axis.get("score") for axis in axes.values()]
    scored = [float(score) for score in all_scores if _finite(score)]
    complete = len(scored) == len(all_scores)
    payload["scores"]["total"] = round(sum(scored), 6) if scored else None
    payload["scores"]["complete"] = complete
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
    # Where the marks went, axis by axis. A total on its own tells a designer
    # that something is wrong; this tells them what, which is the difference
    # between changing the design and enlarging it at random.
    breakdown = {
        name: {
            "score": axis.get("score"),
            "max": axis.get("max_score"),
            "status": axis.get("status"),
        }
        for name, axis in axes.items()
        if isinstance(axis, Mapping)
    }
    lost = sorted(
        (
            (
                round(float(a["max"]) - float(a["score"]), 3),
                name,
            )
            for name, a in breakdown.items()
            if isinstance(a.get("score"), (int, float)) and isinstance(a.get("max"), (int, float))
        ),
        reverse=True,
    )
    return {
        "status": payload.get("status"),
        "physics_gate_passed": bool((payload.get("physics_gate") or {}).get("passed", False)),
        "score": scores.get("total"),
        "max_score": scores.get("max_score"),
        "axes": breakdown,
        # Biggest loss first, so the worst axis is the one that is read first.
        "points_lost": [{"axis": name, "points": points} for points, name in lost if points > 0],
        "survival": survival.get("metrics"),
        "tcl": (axes.get("tcl") or {}).get("metrics") if isinstance(axes.get("tcl"), Mapping) else None,
        "environment": trajectory.get("metrics"),
        "resource_recovery": recovery.get("metrics"),
        "actor_decision": decision.get("metrics"),
        "device_response": response.get("metrics"),
    }


def _admissibility(
    payload: Dict[str, Any],
    *,
    integrity: Mapping[str, Any],
    gate: Mapping[str, Any],
    backend: str,
) -> Dict[str, Any]:
    """Refuse a score the run is not entitled to (spec §14).

    A run that rewrote the yardstick is inadmissible however it scored, and so
    is one whose physics could not be shown to hold. The physics condition only
    applies to a backend that simulates physics: on the loop mock there is
    nothing for the ledgers to close over, and calling that invalid would say
    the run cheated when it merely was not that kind of run.
    """
    reasons: list[str] = []
    integrity_state = evidence_status(integrity)
    if integrity_state == "invalid":
        reasons.append("scoring_bar_modified")
    elif integrity_state == "unknown":
        reasons.append("integrity_unknown")
    if backend == "plant_sim" and gate.get("status") != "passed":
        reasons.append("physics_gate_" + str(gate.get("status")))
    if reasons:
        payload["status"] = "invalid"
        payload["invalid_reasons"] = reasons
    return payload


def finalize_run_evaluation(
    run_dir: Path,
    *,
    scenario_config: Mapping[str, Any],
    summary: Mapping[str, Any],
    integrity: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate one completed run before design and return an enriched summary."""
    run_path = Path(run_dir)
    config = capacity_aware_config(scenario_config)
    payload = evaluate_run(run_path, scenario_config=config, summary=summary)
    payload = reconcile_scheduler_semantics(payload, run_path, config.get("evaluation") or {})

    # The audit is telemetry-only and replaces the evaluator's own gate rather
    # than sitting beside it: two physics verdicts on one run is how the
    # measurement and the artifact drift apart.
    gate = run_physics_gate(run_path)
    payload["physics_gate"] = gate
    (run_path / "physics_gate.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    payload["integrity"] = integrity_summary(integrity)
    payload = _admissibility(
        payload,
        integrity=integrity,
        gate=gate,
        backend=str(summary.get("backend") or ""),
    )

    json_path = run_path / "evaluation.json"
    html_path = run_path / "evaluation.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_evaluation_html(payload), encoding="utf-8")
    write_evaluation_browser(
        run_path.parent,
        default_run_id=run_path.name,
        output_path=run_path / "evaluation_browser.html",
    )

    updated = dict(summary)
    score_block = payload.get("scores") if isinstance(payload.get("scores"), Mapping) else {}
    updated.update(
        {
            "evaluation_path": str(json_path),
            "evaluation_html_path": str(html_path),
            "evaluation_status": payload.get("status"),
            "evaluation_invalid_reasons": payload.get("invalid_reasons") or [],
            "evaluation_score": score_block.get("total"),
            "evaluation_max_score": score_block.get("max_score"),
            "physics_gate_passed": bool(gate.get("passed", False)),
            "physics_gate_status": gate.get("status"),
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
