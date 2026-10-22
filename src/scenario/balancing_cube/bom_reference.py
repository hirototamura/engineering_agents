"""Fixed BOM reference assessment. No proposal generation or parameter search.

The BOM establishes component identity, not a calibrated digital twin. Numerical
priors are inherited explicitly and are never relabelled as measured part data.
"""
from __future__ import annotations

import copy
import math

from .design import digest

REVISION = "bom-reference-20261021-1"
REVIEWED = "reviewed-20261019-1"
LOWER = "bottom-corner-000-20261017-3"

PART_NAMES = {
    "P-001": "Outer panels", "P-002": "Reaction-wheel panels", "P-004": "Motor holders",
    "P-005": "Reaction wheels, standard hole", "P-006": "Reaction wheels, 6 mm hole",
    "P-007": "LED covers", "P-008": "Battery holders", "P-009": "Battery holder 2",
    "P-010": "Controller holder", "P-011": "Battery/controller holder",
    "E-001": "Nidec 24H404H160 motor/driver/encoder", "E-002": "ESP32 30-pin board",
    "E-003": "MPU6050 inertial sensor", "E-004": "3S 500 mAh LiPo battery",
    "E-005": "5 V regulator", "E-006": "Active buzzer", "E-007": "Buzzer transistor",
    "E-008": "10 kilohm resistor", "E-009": "33 kilohm resistor", "E-010": "6.8 kilohm resistor",
    "E-011": "100 nF capacitor", "E-012": "100 microfarad capacitor", "E-013": "Optional RGB LEDs",
    "H-001": "M2 screws", "H-002": "M3 screws", "H-003": "M4 screws", "H-004": "Nuts/washers",
    "W-001": "Motor harnesses", "W-002": "Battery connector/leads", "W-003": "Power/signal wiring",
    "W-004": "Assembly board", "W-005": "Insulation/fastening materials",
}


def component_for(part_id):
    if part_id == "E-001":
        return ["reaction-wheels", "motor-drivers"]
    if part_id == "E-002":
        return ["controller"]
    if part_id == "E-003":
        return ["imu"]
    if part_id in {"P-005", "P-006"}:
        return ["reaction-wheels"]
    if part_id.startswith("E-") or part_id.startswith("W-"):
        return ["power-bus"]
    return ["frame-housing", "vertex-contact"] if part_id in {"P-001", "P-002"} else ["frame-housing"]


def compare_requirements(requirements, parts):
    """Part coverage and remaining work; never marks hardware requirements passed."""
    all_ids = list(parts)
    housing = [k for k in parts if k.startswith("P-")]
    balance = ["P-001", "P-002", "P-004", "P-005", "E-001", "E-002", "E-003", "E-004"]
    drive = ["E-001", "E-004", "E-005", "W-001", "W-002", "W-003"]
    items = {
        "C-BUDGET": (all_ids, "unresolved", "The BOM has no price column. Alternatives and fastener quantities are unresolved. No reliable total cost is available.", "Obtain delivered prices, shipping/tax and the approved budget. Resolve options before totaling."),
        "C-FIT-INSTALL": (all_ids, "unresolved", "Candidate battery dimensions are 56 × 30 × 19 mm. The housing envelope, assembly coordinates and other part dimensions are absent.", "Check pinned STL/CAD against each selected part, including battery packaging and shaft interfaces."),
        "C-FIT-MATERIAL": (housing, "partial", "PLA is planned; the precise filament and approved printer/material list are unresolved.", "Confirm the printer, material list and print recipe."),
        "C-FIT-PRINT": (housing, "unresolved", "STL filenames are recorded, but no verified mesh bounds or printer build limits are supplied.", "Measure each mesh bounding box in its print orientation and compare with the selected printer."),
        "C-JAPAN": (all_ids, "partial", "Several Japanese seller candidates are listed. Exact motor availability, international shipping and some hardware suppliers remain unresolved.", "Confirm the exact purchased variants and delivery to Japan for all purchased parts."),
        "C-PRINT": (housing, "partial", "The reference uses printed panels and holders. Manufacturability on the specified printer is not established.", "Close C-FIT-PRINT and C-FIT-MATERIAL, then inspect the first prints."),
        "M-VERTEX": (balance, "architecture_present", "Three orthogonal reaction-wheel assemblies, sensing and control are represented. The complete physical system has not been tested.", "Assemble and test the cube. Corner 000 is the only implemented simulation equilibrium; eight-corner intent remains open."),
        "R-HOLD": (balance, "unverified", "Part identity alone cannot establish 30 s of unsupported balance.", "Use the separate 30 s numerical diagnostic to plan, not replace, the physical hold test."),
        "R-TILT": (balance, "unverified", "Mass, inertia, motor torque, sensor calibration and release conditions determine tilt performance.", "Measure peak tilt over the full physical hold interval with independent metrology."),
        "R-RMS": (balance, "unverified", "The reviewed limit concerns the whole hold interval. The historical score uses only the final second.", "Record whole-interval tilt RMS separately from the historical settling score."),
        "R-DRIFT": (["P-001", "P-002", "E-002", "E-003"], "unverified", "Corner material, radius and floor friction are not measured. No external position metrology is listed.", "Measure contact-point movement; simulator body-origin drift is only a proxy."),
        "R-REPEAT": (balance, "unverified", "The BOM does not establish repeatability. Repeated random sensor seeds are not ten physical releases.", "Define fixed hardware conditions and run ten independent physical trials."),
        "R-YAW": (["E-002", "E-003", "E-001"], "partial", "The IMU has a gyro and firmware uses a yaw signal. Persistent yaw RMS logging is not demonstrated.", "Add time-stamped gyro telemetry and a defined RMS window. The 5 deg/s value is a target, not an approved gate."),
        "R-DRIVE-TORQUE": (["E-001", "P-005"], "unresolved", "The exact 24H404H160 torque-speed/braking curve is absent. EC45 and other 24H product ratings are not substitutes.", "Measure torque versus speed and PWM at the actual bus voltage, including braking."),
        "R-DRIVE-SPEED": (["E-001", "P-005", "H-001", "H-002", "H-003"], "unresolved", "Encoder connections exist. Rotor count calibration and the approved printed-wheel speed limit are absent.", "Calibrate counts/revolution and approve a mechanical wheel/fastener speed limit."),
        "R-DRIVE-TEMP": (["E-001", "E-005"], "missing_measurement", "No temperature sensor or calibrated thermal model is listed.", "Add motor/driver/regulator temperature measurement and approved limits."),
        "R-DRIVE-VOLTAGE": (drive + ["E-008", "E-009"], "partial", "The 3S battery and divider support voltage monitoring. Exact component operating limits, calibration and voltage sag are unresolved.", "Confirm electrical interfaces and measure voltage through the complete discharge/load range."),
        "R-DRIVE-CURRENT": (drive, "missing_measurement", "No bus-current sensor or approved current limits are in the BOM.", "Add current measurement and validate power wiring, connectors and protection."),
        "R-VISION": ([], "missing_equipment", "The onboard MPU6050 is not independent attitude metrology. No camera/calibration equipment is listed.", "Add the external camera/metrology system and demonstrate ≤0.5 deg standard uncertainty."),
        "R-SYNC": (["E-002"], "missing_equipment", "Bluetooth/MCU availability does not demonstrate video-to-MCU timing uncertainty ≤5 ms.", "Provide a synchronization marker, time-stamped logs and a calibrated time relation."),
        "R-MODEL": (all_ids, "unverified", "There are no paired physical measurements to calibrate or validate this model.", "Measure mass/inertia, actuation, sensing and contact, then compare matched physical and numerical trials."),
        "R-TRACE": (["E-002"], "partial", "Versioned software records can identify this run. The BOM alone does not provide hardware serial/build identity or a test logger.", "Keep configuration hashes and exact revisions; add as-built serials, calibration IDs and hardware logs."),
    }
    selected = [r for r in requirements if r["data"].get("record_role") == "requirement"]
    if {r["id"] for r in selected} != set(items):
        raise ValueError("Reviewed requirement suite changed; review the BOM comparison mapping")
    result = []
    for req in selected:
        ids, status, finding, action = items[req["id"]]
        if not set(ids) <= set(parts):
            raise ValueError("Unknown part in requirement comparison")
        result.append({"requirement_ref": {"id": req["id"], "revision": req["revision"]},
            "statement": req["data"]["statement"], "acceptance_criteria": req["data"]["acceptance_criteria"],
            "part_ids": ids, "coverage_status": status, "finding": finding, "next_evidence": action,
            "requirement_approval_state": req["data"]["approval_state"],
            "hardware_verification_status": "not_run", "physical_verified": False})
    return result


def build_reference(reviewed_snapshot, lower_snapshot, bom):
    """Build a fixed reference with explicit provenance and preserved controller."""
    if len(bom["parts"]) != 32 or len({p["part_id"] for p in bom["parts"]}) != 32:
        raise ValueError("Unexpected or duplicate BOM parts")
    parts = {p["part_id"]: p for p in bom["parts"]}
    if parts["E-001"]["quantity_reference"] != 3 or parts["E-004"]["reference_mass_g"] != 49:
        raise ValueError("BOM reference changed; revise the numerical recipe explicitly")
    if any(p["measured_mass_g"] is not None for p in parts.values()):
        raise ValueError("Measured masses are now present; review the assumption-based recipe")
    data = copy.deepcopy(reviewed_snapshot)
    cfg = copy.deepcopy(lower_snapshot["model"])
    cfg["revision"] = REVISION
    cfg["reference"].update(bom_sha256=bom["source_sha256"],
        note="BOM identities mapped to an inherited numerical proxy. No measured geometry, mass or motor calibration.")
    cfg["component_reference"] = {
        "motor": "Nidec 24H404H160 (identity only; envelope uncalibrated)",
        "controller_board": "ESP32 30-pin", "imu": "MPU6050 (ideal tilt/gyro proxy)",
        "battery": {"nominal_voltage_v": 11.1, "capacity_ah": 0.5, "reference_mass_kg": 0.049,
                    "nominal_energy_wh": 5.55, "source_cells": ["BOM!H21", "BOM!I21"],
                    "status": "candidate specification, not measured; no electrical simulation"},
        "firmware": {"control_period_ms": 15, "pwm_frequency_hz": 20000, "pwm_bits": 8,
                     "executed": False, "note": "Source firmware is inspected, not emulated. Frozen SI LQR is used."}}
    cfg["actuation"]["note"] = "Inherited generic 0.06 Nm / 200 rad/s envelope; NOT a Nidec rating. 0.04 Nm is a comparison threshold, not a thermal rating."
    cfg["evaluation"]["note"] = "Inherited numerical development stop conditions, distinct from hardware acceptance."
    controller = copy.deepcopy(lower_snapshot["controller"])
    data.update(model=cfg, controller=controller, families={}, history_only=False,
        comparison_design_ref={"id": "cube.design.remrc-bom-reference", "revision": REVISION},
        source_snapshot_ref={"id": "cube.simulation.snapshot", "revision": REVIEWED},
        controller_design_snapshot_ref=copy.deepcopy(lower_snapshot["controller_design_snapshot_ref"]),
        controller_source_ref=copy.deepcopy(lower_snapshot["controller_source_ref"]),
        controller_design_plant="Frozen MASS-selected K from the lower-face trial, retained without tuning. This is not remrc firmware execution.",
        trial_scope={"support_corner": "000", "implemented_support_corner_count": 1,
                     "mission_corner_count": 8, "physical_verified": False, "other_corners_verified": False},
        assessment_scope="Human-requested fixed component reference; zero LLM calls, zero design proposals, no adopted hardware baseline.")
    data["context_refs"]["model"] = {"id": "cube.simulation.snapshot", "revision": REVISION}
    data.pop("controller_selection_evidence_ref", None)
    # Keep approved registry values intact while recording the exact resolved model values.
    for binding in data.get("parameter_bindings", []):
        value = cfg
        for part in binding["model_path"].split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        binding["resolved_value"] = value
        binding["values_match"] = value == binding["registered_value"]
    assumptions = [
        {"field": "physics.cube_side_m", "value": cfg["physics"]["cube_side_m"], "unit": "m", "origin": "inherited_nominal_assumption", "parts": ["P-001", "P-002"], "gap": "No STL bounds or assembled dimensions."},
        {"field": "physics.frame_mass_kg", "value": cfg["physics"]["frame_mass_kg"], "unit": "kg", "origin": "inherited_aggregate_assumption", "parts": [p for p in parts if p not in {"P-005", "P-006", "P-007", "E-013"}], "gap": "0.049 kg candidate battery is INCLUDED, not added again; remaining 0.501 kg is an unresolved fixed-mass budget including stators. Rotor mass is in each wheel aggregate."},
        {"field": "physics.wheel_mass_kg", "value": cfg["physics"]["wheel_mass_kg"], "unit": "kg/assembly", "origin": "inherited_aggregate_assumption", "parts": ["P-005", "E-001", "H-001", "H-002", "H-003"], "gap": "Each aggregate includes print, weights/fasteners and motor rotor. No measured mass or split."},
        {"field": "physics.wheel_radius_m", "value": cfg["physics"]["wheel_radius_m"], "unit": "m", "origin": "inherited_nominal_assumption", "parts": ["P-005"], "gap": "No verified STL geometry; 6 mm hole variant excluded."},
        {"field": "physics.wheel_axial_inertia_kg_m2", "value": cfg["physics"]["wheel_axial_inertia_kg_m2"], "unit": "kg m^2", "origin": "inherited_thin_ring_approximation", "parts": ["P-005", "E-001"], "gap": "Equivalent ring inertia; print infill/weights/rotor distribution unmeasured."},
        {"field": "actuation.peak_torque_nm", "value": cfg["actuation"]["peak_torque_nm"], "unit": "N m", "origin": "inherited_generic_proxy", "parts": ["E-001"], "gap": "No exact-part torque curve. This is not an EC45 or Nidec specification."},
        {"field": "actuation.no_load_speed_rad_s", "value": cfg["actuation"]["no_load_speed_rad_s"], "unit": "rad/s", "origin": "inherited_generic_proxy", "parts": ["E-001"], "gap": "Uncalibrated symmetric acceleration/braking envelope."},
        {"field": "sensing", "value": cfg["sensing"], "unit": "mixed, keys carry units", "origin": "inherited_ideal_sensor_proxy", "parts": ["E-003", "E-001"], "gap": "No MPU6050 raw accelerometer/filter, drift or encoder quantization model."},
        {"field": "contact", "value": cfg["contact"], "unit": "mixed, keys carry units", "origin": "inherited_contact_assumption", "parts": ["P-001", "P-002"], "gap": "Corner radius, floor friction and compliance unmeasured."},
        {"field": "controller", "value": {"sha256": digest(controller)}, "unit": "SI gains", "origin": "retained_saved_controller", "parts": ["E-002"], "gap": "No code generation, target timing validation or PWM-to-torque transfer calibration."},
    ]
    data["component_bom"] = {"source_sha256": bom["source_sha256"], "reference_mass_not_measured": True,
                             "assumptions": assumptions, "selection_rules": bom["selection_rules"]}
    return data


def hold_diagnostic(result):
    """30 s numerical analogues, clearly separate from the six-second score."""
    rows, summary = result["rows"], result["summary"]
    # Uniform control-period samples. Include the initial release sample.
    rms = math.sqrt(sum(r["tilt_total_deg"] ** 2 for r in rows) / len(rows))
    yaw = math.sqrt(sum(r["omega_z_deg_s"] ** 2 for r in rows) / len(rows))
    checks = {"duration_30s": summary["status"] == "completed" and summary["simulated_duration_s"] >= 30 - 1e-6,
              "peak_tilt_le_5deg": summary["peak_tilt_deg"] <= 5,
              "whole_interval_tilt_rms_le_2deg": rms <= 2,
              "body_origin_drift_proxy_le_2mm": summary["peak_pivot_displacement_mm"] <= 2,
              "contact_fraction_ge_0_99": summary["contact_fraction"] >= .99}
    return {"checks": checks, "passed_numerical_analogues": all(checks.values()),
            "whole_interval_tilt_rms_deg": rms, "whole_interval_yaw_rms_deg_s": yaw,
            "yaw_5deg_s_is_target_only": True, "physical_verified": False,
            "scope": "Numerical diagnostic only; body-origin drift is not measured contact-point displacement. No physical repeatability claim."}
