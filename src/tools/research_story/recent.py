"""Traceable article projections of October 17 experiments.

MJX scores are a retrospective read of saved MJX summaries. They do not replace
the score used by the original search to choose its incumbent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scenario.balancing_cube.evaluation import screening

STUDY = "mass-inspired-cube10-20261017t060309z-context-v3"
BOTTOM = "bottom000-first-trial-20261017"
FIELDS = ("time_s", "position_m", "quaternion_wxyz", "wheel_angle_rad", "tilt_total_deg",
          "wheel_x_rpm", "wheel_y_rpm", "wheel_z_rpm", "motor_x_nm", "motor_y_nm",
          "motor_z_nm", "speed_governor_active", "torque_limited", "pivot_displacement_mm")


def measured_score(result: dict, snapshot: dict, summary_key="gpu_summary") -> dict:
    """Fail closed on missing MJX evidence; never substitute native summaries."""
    records = result["records"]
    if len(records) != 12:
        raise ValueError("Article score requires all twelve cases")
    identities = {(r["domain_id"], r["condition_id"], r["seed"]) for r in records}
    if len(identities) != 12:
        raise ValueError("Duplicate article cases")
    cases = []
    for r in records:
        s = r[summary_key]
        gates = screening(s, snapshot["contract"])
        cases.append({"domain": r["domain_id"], "condition": r["condition_id"], "seed": r["seed"],
                      "passed": all(g["passed"] for g in gates), "summary": s,
                      "failures": [g for g in gates if not g["passed"]]})
    mean_rms = sum(r["summary"]["final_1s_tilt_rms_deg"] for r in cases) / 12
    mean_torque = sum(r["summary"]["continuous_torque_exceeded_fraction"] for r in cases) / 12
    passed = sum(c["passed"] for c in cases)
    objective = snapshot["plan"]["objective"]
    return {"score": passed / 12 - objective["rms_penalty"] * mean_rms
            - objective["torque_proxy_penalty"] * mean_torque,
            "passed": passed, "trial_count": 12, "cases": cases,
            "mean_final_tilt_rms_deg": mean_rms,
            "mean_continuous_torque_exceeded_fraction": mean_torque,
            "summary_source": summary_key, "objective": objective}


def extend(workspace: Path, data: dict) -> dict:
    sources = {s["path"]: s for s in data["sources"]}

    def read(path):
        path = Path(path)
        raw = (workspace / path).read_bytes()
        sources[path.as_posix()] = {"path": path.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        return json.loads(raw)

    results = Path("engineering_agents/experiments/balancing_cube/results")

    def candidates(folder, snapshot):
        found = []
        for path in sorted((workspace / folder / "candidates").glob("*/result.json")):
            rel = path.relative_to(workspace)
            r = read(rel)
            compiled = read(rel.with_name("compiled.json"))
            m = measured_score(r, snapshot)
            found.append({"candidate_id": r["candidate_id"], "round": r["round"],
                          "matrix_cell": r["matrix_cell"], "score": m["score"], "passed": m["passed"],
                          "failed_case_count": 12 - m["passed"], "all_screening_passed": m["passed"] == 12,
                          "failure_metrics": sorted({g["metric"] for c in m["cases"] for g in c["failures"]}),
                          "mean_final_tilt_rms_deg": m["mean_final_tilt_rms_deg"],
                          "mean_continuous_torque_exceeded_fraction": m["mean_continuous_torque_exceeded_fraction"],
                          "proposal": compiled["proposal"], "source": rel.as_posix(),
                          "input_digest": r["input_digest"], "controller_digest": r["controller_digest"],
                          "archive_selection_score": r["score"]})
        return found

    for run in data["runs"]:
        folder = results / run["name"]
        snapshot = read(folder / "frozen-snapshot.json")
        run["mjx"] = {"candidates": candidates(folder, snapshot),
                      "separate_cases": measured_score(read(folder / "validation/result.json"), snapshot),
                      "analysis": "Retrospective MJX projection; original selection used the archived native-summary score."}

    folder = results / STUDY
    report = read(folder / "report-evidence.json")
    recent = {"study_id": STUDY, "snapshot_ref": report["verification"]["source_snapshot_ref"],
              "llm": {k: v for k, v in report["manifest"]["llm"].items() if k != "base_url"},
              "model_root": report["manifest"]["model_root"],
              "budget": report["manifest"]["comparison_budget"], "arms": {},
              "original_dispatch_state": read(folder / "study-results.json")["state"]}
    for mode in ("multi_agent", "single_agent"):
        arm = report["arms"][mode]
        summary = report["results"]["arms"][mode]
        snapshot = read(folder / mode / "frozen-snapshot.json")
        cs = candidates(folder / mode, snapshot)
        rounds = [{"round": n, "best_score": max(c["score"] for c in cs if c["round"] <= n)} for n in range(11)]
        selected = next(c for c in cs if c["candidate_id"] == summary["best"]["candidate_id"])
        wf = summary["proposal_workflow"]
        recent["arms"][mode] = {
            "candidates": cs, "rounds": rounds, "selected": selected,
            "attempted": summary["proposal_rounds_recorded"], "completed": summary["iterations_completed"],
            "rejected": [{"round": f["round"], "reason": f["reason"]} for f in arm["failures"]],
            "wall_time_s": summary["wall_time_s"], "workflow_usage": wf,
            "workflow_updates": [{"round": r["round"], "in": r["workflow_in"], "out": r["workflow_out"],
                                   "evolution": r["evolution"]} for r in arm["rounds"]],
            "fresh_mjx": measured_score(read(folder / "fresh-audit" / mode / "result.json"), snapshot),
        }
    recent["starting_fresh_mjx"] = measured_score(read(folder / "baseline-fresh-audit/result.json"), snapshot)
    data["multi_agent_study"] = recent

    bottom = read(results / BOTTOM / "mounting-report-data.json")
    final = read(results / BOTTOM / "validation/result.json")
    lower_compiled = read(results / BOTTOM / "validation/compiled.json")
    upper_result = read(folder / "multi_agent/validation/result.json")
    upper_compiled = read(folder / "multi_agent/validation/compiled.json")
    replays = []
    for result, compiled in ((upper_result, upper_compiled), (final, lower_compiled)):
        r = next(r for r in result["records"] if (r["domain_id"], r["condition_id"], r["seed"]) == ("heavy-delay-prior-confirm", "confirm-b", 812))
        replays.append({"frames": [{k: f[k] for k in FIELDS} for f in r["frames"]],
                        "physics": compiled["config"]["physics"], "actuation": compiled["config"]["actuation"],
                        "summary": r["summary"], "status": r["summary"]["status"],
                        "origin": "recorded native MuJoCo", "case": "heavy-delay-prior-confirm / confirm-b / 812"})
    read("integration-validation/bottom-corner-20261017/native-final/comparison.json")
    alternatives = []
    for label, path in (
        ("nominal_relinearized", "native-comparison/M1C1-result.json"),
        ("reference_relinearized", "reference-controller-check/result.json"),
    ):
        alternative = read("integration-validation/bottom-corner-20261017/" + path)
        alternatives.append({"controller": label, "score": alternative["score"],
                             "passed": round(alternative["screening_pass_fraction"] * 12)})
    data["mounting"] = {"geometry": bottom["geometry"], "source_snapshot_refs": bottom["source_snapshot_refs"],
                        "cells": {k: {a: v[a] for a in ("score", "screening_pass_fraction", "controller_digest")} for k, v in bottom["cells"].items()},
                        "replays": replays, "known_heavy_case": bottom["known_heavy_case"],
                        "existing_confirmation": bottom["existing_confirmation"],
                        "relinearized_alternatives": alternatives,
                        "source": (results / BOTTOM / "mounting-report-data.json").as_posix(),
                        "report": (results / BOTTOM / "bottom-corner-trial-report.html").as_posix(),
                        "full_matrix_implementation": "native MuJoCo", "full_matrix_mjx": "not_run",
                        "physical_verified": False, "other_seven_corners_verified": False}
    data["schema_version"] = 3
    data["evidence_cut"] = "2026-10-17"
    data["article_revision"] = "2026-10-18"
    data["sources"] = list(sources.values())
    return data
