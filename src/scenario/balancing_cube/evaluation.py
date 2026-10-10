"""Deterministic screening and CPU/GPU agreement using SSOT criteria at fixed dt."""
from __future__ import annotations

import math


def screening(summary, contract):
    checks = []
    for rule in contract["screening"]["criteria"]:
        value, limit, op = summary.get(rule["metric"]), rule["limit"], rule["operator"]
        if op == "==":
            passed = value == limit
        elif op in {"<=", ">="}:
            passed = (isinstance(value, (int, float)) and not isinstance(value, bool)
                      and math.isfinite(value) and (value <= limit if op == "<=" else value >= limit))
        else:
            raise ValueError("Unsupported verification operator")
        checks.append({**rule, "value": value, "passed": bool(passed)})
    duration = contract["screening"]["required_duration_s"]
    checks.append({"metric": "required_duration_s", "value": summary.get("simulated_duration_s"),
                   "limit": duration, "passed": summary.get("status") == "completed"
                   and summary.get("simulated_duration_s", -1) >= duration - 1e-6})
    return checks


def paired_metrics(cpu, gpu, contract, *, control_period_s):
    import numpy as np
    a, b = cpu["rows"], gpu["rows"]
    if len(a) < 2 or len(b) < 2:
        return {"passed": False, "state": "inconclusive", "reason": "insufficient_trajectory"}
    t, gt = np.array([r["time_s"] for r in a]), np.array([r["time_s"] for r in b])
    if (not np.isfinite(t).all() or not np.isfinite(gt).all()
            or not np.all(np.diff(t) > 0) or not np.all(np.diff(gt) > 0)):
        return {"passed": False, "state": "inconclusive", "reason": "invalid_timestamps"}
    agreement = contract["cpu_gpu_agreement"]
    cp, gp = cpu["summary"], gpu["summary"]
    needed = min(agreement["pre_divergence_time_window_s"],
                 cp["simulated_duration_s"], gp["simulated_duration_s"])
    if (max(t[0], gt[0]) > control_period_s + 1e-8
            or min(t[-1], gt[-1]) < needed - control_period_s - 1e-8):
        return {"passed": False, "state": "inconclusive", "reason": "incomplete_comparison_interval"}
    for rows, stamps in ((a, t), (b, gt)):
        keys = ("tilt_total_deg", "omega_x_deg_s", "omega_y_deg_s", "omega_z_deg_s", "pivot_displacement_mm")
        if any(not isinstance(r.get(key), (int, float)) or isinstance(r.get(key), bool)
               or not math.isfinite(r[key]) for r in rows for key in keys):
            return {"passed": False, "state": "inconclusive", "reason": "missing_or_nonfinite_series"}
        prefix = stamps[stamps <= needed + control_period_s]
        if len(prefix) < 2 or np.max(np.diff(prefix)) > 3 * control_period_s + 1e-8:
            return {"passed": False, "state": "inconclusive", "reason": "gap_in_comparison_prefix"}
    end = min(needed, t[-1], gt[-1])
    mask = t <= end + 1e-8
    def rmse(key):
        av = np.asarray([r[key] for r in a])[mask]
        bv = np.interp(t[mask], gt, [r[key] for r in b])
        return float(np.sqrt(np.mean((av - bv) ** 2)))
    values = {"tilt_rmse_deg": rmse("tilt_total_deg"),
              "omega_rmse_deg_s": max(rmse(f"omega_{axis}_deg_s") for axis in "xyz"),
              "pivot_position_rmse_mm": rmse("pivot_displacement_mm"),
              "wheel_peak_difference_rpm": abs(cpu["summary"]["peak_wheel_rpm"] - gpu["summary"]["peak_wheel_rpm"])}
    checks = []
    for rule in agreement["pre_divergence_tolerances"]:
        if "limit" in rule:
            limit = rule["limit"]
        elif rule["metric"] == "wheel_peak_difference_rpm":
            # Legacy snapshots express this one criterion as a declarative rule.
            # Accept its documented form, rather than executing arbitrary text.
            import re
            match = re.fullmatch(r"abs\(diff\) <= max\((\d+(?:\.\d+)?) rpm, (\d+(?:\.\d+)?) \* abs\(CPU peak rpm\)\)", rule.get("rule", ""))
            if not match:
                raise ValueError("Wheel agreement needs a numeric limit or registered rule")
            absolute, relative = map(float, match.groups())
            limit = max(absolute, relative * abs(cpu["summary"]["peak_wheel_rpm"]))
        else:
            raise ValueError("Agreement criterion missing numeric limit")
        value = values[rule["metric"]]
        checks.append(math.isfinite(value) and value <= limit)
    checks.extend([cp["status"] == gp["status"],
                   abs(cp["simulated_duration_s"] - gp["simulated_duration_s"]) <= agreement["termination_time_tolerance_s"],
                   [c["passed"] for c in screening(cp, contract)] == [c["passed"] for c in screening(gp, contract)]])
    near = []
    for rule in contract["screening"]["criteria"]:
        margin = agreement.get("near_gate_margins", {}).get(rule["metric"])
        if margin is not None and any(abs(s[rule["metric"]] - rule["limit"]) <= margin for s in (cp, gp)):
            near.append(rule["metric"])
    passed = all(checks) and not near
    return {"passed": passed, "state": "verified" if passed else "inconclusive",
            "values": values, "comparison_interval_s": [float(t[0]), float(end)],
            "near_gate_metrics": near, "half_step_adjudication_performed": False,
            "scope": "fixed_dt_full_episode_gates_and_prefix_trajectory; no_half_step_adjudication"}


def aggregate(records, snapshot, expected_keys):
    keys = [(r["domain_id"], r["condition_id"], r["seed"]) for r in records]
    if len(keys) != len(set(keys)) or set(keys) != set(expected_keys):
        raise ValueError("Incomplete/duplicate candidate trial matrix")
    if not records or any(not math.isfinite(value) for r in records for value in r["summary"].values()
                          if isinstance(value, (int, float))):
        raise ValueError("Empty or nonfinite simulation evidence")
    flags = [all(c["passed"] for c in screening(r["summary"], snapshot["contract"])) for r in records]
    rms = sum(r["summary"]["final_1s_tilt_rms_deg"] for r in records) / len(records)
    torque = sum(r["summary"]["continuous_torque_exceeded_fraction"] for r in records) / len(records)
    objective = snapshot["plan"]["objective"]
    return {"screening_pass_fraction": sum(flags) / len(flags), "all_screening_passed": all(flags),
            "score": sum(flags) / len(flags) - objective["rms_penalty"] * rms - objective["torque_proxy_penalty"] * torque,
            "numeric_cpu_verified": True,
            "numeric_gpu_verified": all(r.get("paired_metrics", {}).get("passed") is True for r in records),
            "physical_fidelity": None, "physical_verified": False,
            "electrical_energy_j": None, "temperature_prediction_c": None,
            "trial_count": len(records), "records": records}
