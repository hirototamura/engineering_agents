"""Independently reproduce historical CPU summaries at the fixed 1 ms timestep.

Usage: python scripts/verify_cube_reproduction.py --source <gpu-results-final>
The historical DB is opened immutable/read-only. No half-step run is performed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
from pathlib import Path


def verify(source: Path) -> dict:
    from environment.mujoco.backend import native_rollout

    replay = json.loads((source / "report/replay.json").read_text())
    campaigns = sorted(p.parent for p in source.glob("*/jobs.sqlite"))
    if len(campaigns) != 1:
        raise ValueError("Expected exactly one historical campaign")
    campaign = campaigns[0]
    controller = json.loads((campaign / "controller.json").read_text())
    metrics = ("simulated_duration_s", "peak_tilt_deg", "final_1s_tilt_rms_deg",
               "peak_wheel_rpm", "peak_motor_torque_nm", "peak_pivot_displacement_mm",
               "peak_slip_speed_m_s", "continuous_torque_exceeded_fraction")
    cases = []
    with sqlite3.connect((campaign / "jobs.sqlite").resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        for case in replay["cases"]:
            row = db.execute("SELECT result FROM jobs WHERE candidate_id=? AND stage='validation'",
                             (case["candidate_id"],)).fetchone()
            if row is None:
                raise ValueError("Missing historical verification")
            historical = json.loads(row[0])
            saved = next(r for r in historical["records"] if r["run_id"] == case["source_run_id"])["cpu_summary"]
            config = copy.deepcopy(case["config"])
            config["physics"]["timestep_s"] = 0.001
            actual = native_rollout(config, case["case"], controller)
            differences = {key: actual["summary"][key] - saved[key] for key in metrics}
            status = actual["summary"]["status"] == saved["status"]
            cases.append({"case": case["id"], "passed": status and all(abs(v) <= 1e-8 for v in differences.values()),
                          "same_status": status, "difference": differences, "fixed_dt_s": 0.001,
                          "comparison_source": "original_validation.cpu_summary_at_1ms",
                          "frames": len(actual["frames"]), "controller": "saved_K",
                          "half_step_performed": False, "new_gpu_execution": False,
                          "physical_validation": False})
    return {"passed": all(case["passed"] for case in cases), "cases": cases,
            "absolute_metric_tolerance": 1e-8,
            "controller_sha256": hashlib.sha256((campaign / "controller.json").read_bytes()).hexdigest(),
            "scope": "fixed-timestep CPU reproduction; not new GPU agreement or physical validation"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.source.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "cases": len(result["cases"]), "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
