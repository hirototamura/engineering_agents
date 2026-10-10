"""Compile allowlisted mechanical and LQR design data, never evaluation code."""
from __future__ import annotations

import copy
import hashlib
import json
import math

MECHANICAL_BOUNDS = {
    "side_m": (0.14, 0.22), "print_mass_ref_kg": (0.08, 0.25),
    "wheel_mass_kg": (0.035, 0.09), "wheel_radius_ratio": (0.23, 0.40),
    "inner_radius_ratio": (0.65, 0.92), "wheel_thickness_m": (0.004, 0.010),
}
CONTROL_BOUNDS = {"tilt_q_scale": (0.25, 4.0), "rate_q_scale": (0.25, 4.0),
                  "momentum_q_scale": (0.25, 4.0), "yaw_rate_gain_nm_s": (0.0, 0.12)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def bounded(value, bounds, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not bounds[0] <= value <= bounds[1]:
        raise ValueError(f"{name} outside allowlisted bounds {bounds}")
    return float(value)


def compile_mechanical(proposal, snapshot):
    allowed = {"id", "family", "parameters", "control", "parent_id", "hypothesis", "proposer"}
    if not isinstance(proposal, dict):
        raise ValueError("Proposal must be a JSON object")
    if set(proposal) - allowed or any(not isinstance(proposal.get(key), str) or not proposal[key].strip()
                                    for key in ("id", "hypothesis")):
        raise ValueError("Proposal requires id/hypothesis and only allowlisted design fields")
    cfg = copy.deepcopy(snapshot["model"])
    family = proposal.get("family")
    p = proposal.get("parameters", {})
    if not isinstance(p, dict):
        raise ValueError("parameters must be a JSON object")
    if family == "reference":
        if p:
            raise ValueError("Reference mechanics cannot be overridden")
        return copy.deepcopy(snapshot.get("reference_model", cfg))
    if not isinstance(family, str) or family not in snapshot["families"] or set(p) != set(MECHANICAL_BOUNDS):
        raise ValueError("Registered family and exactly six mechanical variables required")
    # SSOT may tighten bounds. It cannot expand the explicitly authorized set.
    limits = snapshot.get("design_bounds", {})
    p = {key: bounded(value, (max(MECHANICAL_BOUNDS[key][0], limits.get(key, MECHANICAL_BOUNDS[key])[0]),
                              min(MECHANICAL_BOUNDS[key][1], limits.get(key, MECHANICAL_BOUNDS[key])[1])), key)
         for key, value in p.items()}
    spec = snapshot["families"][family]
    numeric = [v for key, v in spec.items() if key.endswith(("_assumption", "_nm", "_rad_s"))]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in numeric):
        raise ValueError("Invalid motor family priors")
    if not 0 <= spec["rotor_mass_kg_assumption"] < spec["total_motor_mass_kg_assumption"]:
        raise ValueError("Motor rotating/fixed mass split is invalid")
    side, mass = p["side_m"], p["wheel_mass_kg"]
    radius = side * p["wheel_radius_ratio"]
    if radius + .008 >= side / 2:
        raise ValueError("Wheel clearance invalid")
    inner = radius * p["inner_radius_ratio"]
    printed = p["print_mass_ref_kg"] * (side / .18) ** 3
    frame = 3 * (spec["total_motor_mass_kg_assumption"] - spec["rotor_mass_kg_assumption"]) + spec["other_fixed_mass_kg_assumption"] + printed
    axial = .5 * mass * (radius ** 2 + inner ** 2) + spec["rotor_axial_inertia_kg_m2_assumption"]
    transverse = .25 * mass * (radius ** 2 + inner ** 2) + mass * p["wheel_thickness_m"] ** 2 / 12 + spec["rotor_transverse_inertia_kg_m2_assumption"]
    if 2 * transverse < axial:
        raise ValueError("Inertia triangle inequality violated")
    cfg["physics"].update(cube_side_m=side, frame_mass_kg=frame,
        frame_inertia_kg_m2=[frame * side ** 2 / 6] * 3,
        wheel_mass_kg=mass + spec["rotor_mass_kg_assumption"], wheel_radius_m=radius,
        wheel_thickness_m=p["wheel_thickness_m"], wheel_axial_inertia_kg_m2=axial,
        wheel_transverse_inertia_kg_m2=transverse, motor_torque_limit_nm=spec["torque_cap_nm"])
    cfg.setdefault("actuation", {}).update(peak_torque_nm=spec["torque_cap_nm"],
        continuous_torque_nm=spec["torque_comparison_threshold_nm"],
        no_load_speed_rad_s=spec["no_load_speed_rad_s"])
    return cfg


def compile_controller(proposal, snapshot):
    if not isinstance(proposal, dict):
        raise ValueError("Proposal must be a JSON object")
    control = proposal.get("control", {})
    if not isinstance(control, dict):
        raise ValueError("control must be a JSON object")
    if set(control) - set(CONTROL_BOUNDS):
        raise ValueError("Only three Q group multipliers and yaw gain may change; R is fixed")
    if not control:
        return copy.deepcopy(snapshot["controller"])
    # Controller changes are designed at the frozen nominal plant, so mechanical
    # comparisons within each new controller campaign receive identical gains.
    from environment.mujoco.control import Regulator
    cfg = copy.deepcopy(snapshot["model"])
    settings = {key: 1.0 for key in ("tilt_q_scale", "rate_q_scale", "momentum_q_scale")}
    settings["yaw_rate_gain_nm_s"] = cfg["controller"]["yaw_rate_gain_nm_s"]
    settings.update({key: bounded(value, CONTROL_BOUNDS[key], key) for key, value in control.items()})
    q = cfg["controller"]["vertex_q"]
    cfg["controller"]["vertex_q"] = [value * settings[key] for key, values in (
        ("tilt_q_scale", q[:2]), ("rate_q_scale", q[2:4]), ("momentum_q_scale", q[4:])) for value in values]
    cfg["controller"]["yaw_rate_gain_nm_s"] = settings["yaw_rate_gain_nm_s"]
    result = Regulator(cfg, "vertex").as_dict()
    result["design_parameters"] = settings
    result["fixed_r"] = cfg["controller"]["vertex_r"]
    return result


def trial_matrix(config, snapshot, candidate_id, stage="exploration"):
    partition = snapshot["plan"][stage]
    keys, result = set(), []
    for domain in partition["domains"]:
        cfg = copy.deepcopy(config)
        scale = domain.get("frame_mass_scale", 1.0)
        cfg["physics"]["frame_mass_kg"] *= scale
        cfg["physics"]["frame_inertia_kg_m2"] = [value * scale for value in cfg["physics"]["frame_inertia_kg_m2"]]
        cfg.setdefault("contact", {}).update({key: domain[key] for key in ("sliding_friction", "corner_radius_m")})
        cfg.setdefault("sensing", {})["control_delay_s"] = domain["control_delay_s"]
        for condition in partition["conditions"]:
            for seed in partition["seeds"]:
                key = (domain["id"], condition["id"], seed)
                if key in keys:
                    raise ValueError("Duplicate trial key in frozen matrix")
                keys.add(key)
                case = copy.deepcopy(condition)
                case.update(id=candidate_id + "--" + "--".join(map(str, key)), seed=seed,
                            duration_s=snapshot["contract"]["screening"]["required_duration_s"])
                result.append({"config": cfg, "case": case, "key": key})
    if not result:
        raise ValueError("Frozen trial matrix is empty")
    return result
