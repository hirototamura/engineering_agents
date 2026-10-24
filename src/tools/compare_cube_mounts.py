"""Fixed-dt mounting development tests and a small native MuJoCo–MJX fixture set.

This is not a design search or an eight-corner/physical qualification. Controllers
come from exact saved SSOT revisions; this runner does not synthesize gains.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from scenario.balancing_cube.design import digest, trial_matrix
from scenario.balancing_cube.evaluation import aggregate, paired_metrics, screening


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def geometry(config):
    import numpy as np
    from environment.mujoco.model import Plant, wheel_centers_body_m
    plant = Plant(config)
    return {"wheel_centers_body_m": wheel_centers_body_m(config).tolist(),
        "wheel_centers_world_m": (plant.r0 @ wheel_centers_body_m(config).T).T.tolist(),
        "mass_kg": float(plant.model.body_subtreemass[plant.body]),
        "com_above_corner_world_m": (plant.data.subtree_com[plant.body] - plant.data.xpos[plant.body]).tolist(),
        "frame_com_body_m": (config["physics"]["cube_side_m"] * np.asarray(config["physics"]["frame_com_fraction"])).tolist()}


def compare(store_path, output):
    from integrations.one_piece.mechanical_bridge import MechanicalBridge
    from environment.mujoco.backend import native_rollout
    from scenario.balancing_cube.adapter import BalancingCubeAdapter
    from tools.prepare_bottom_corner_trial import REVISION

    old = MechanicalBridge(store_path, snapshot_revision="standards-draft-20261011-2").load_snapshot()
    new = MechanicalBridge(store_path, snapshot_revision=REVISION).load_snapshot()
    if output.exists():
        raise ValueError("Use an empty output directory")
    output.mkdir(parents=True)
    configs = [old["reference_model"], new["reference_model"]]
    controllers = [old["controller"], new["controller"]]
    assert configs[0]["physics"].get("wheel_mount_side", "far_corner_000") == "far_corner_000"
    assert configs[1]["physics"]["wheel_mount_side"] == "near_corner_000"
    assert old["contract"] == new["contract"] and old["plan"] == new["plan"]
    summary = {"source_snapshot_refs": [old["source_snapshot_ref"], new["source_snapshot_ref"]],
        "snapshot_digests": [digest(old), digest(new)], "code_digests": BalancingCubeAdapter._code_digests(),
        "geometry": {"upper": geometry(configs[0]), "lower": geometry(configs[1])},
        "controllers": controllers, "cells": {}, "support_corner": "000",
        "other_seven_corners_verified": False, "physical_verified": False,
        "scope": "Matched development conditions; native MuJoCo 2x2, not hardware acceptance."}
    first_lower_trial = None
    for m in range(2):
        for c in range(2):
            cell = f"M{m}C{c}"
            trials = trial_matrix(configs[m], new, cell)
            records = []
            for i, trial in enumerate(trials):
                run = native_rollout(trial["config"], trial["case"], controllers[c])
                write(output / f"{cell}-case-{i+1:02}.json", run)
                records.append({"domain_id": trial["key"][0], "condition_id": trial["key"][1], "seed": trial["key"][2],
                    "summary": run["summary"], "screening": screening(run["summary"], new["contract"])})
                if m == c == 1 and i == 0:
                    first_lower_trial = trial
            score = aggregate(records, new, [t["key"] for t in trials])
            score["comparison_state"] = "not_run"
            summary["cells"][cell] = {"mount": "lower" if m else "upper", "controller": "selected_saved" if c else "historical_upper",
                "config_digest": digest(configs[m]), "controller_digest": digest(controllers[c]), **score}
            write(output / f"{cell}-result.json", summary["cells"][cell])
    fixtures = []
    for name in ("controlled_nominal", "no_control", "low_torque", "reversed_disturbance"):
        trial = copy.deepcopy(first_lower_trial)
        trial["case"]["id"] = name
        if name == "no_control":
            trial["case"]["control"] = False
        elif name == "low_torque":
            trial["config"]["physics"]["motor_torque_limit_nm"] = .003
            trial["config"]["actuation"]["peak_torque_nm"] = .003
        elif name == "reversed_disturbance":
            for disturbance in trial["case"].get("disturbances", []):
                disturbance["torque_world_nm"] = [-v for v in disturbance["torque_world_nm"]]
        fixtures.append({"id": name, "config": trial["config"], "case": trial["case"]})
    qualification = {"source_snapshot_ref": new["source_snapshot_ref"], "controller": controllers[1],
        "controller_digest": digest(controllers[1]), "contract": new["contract"], "fixtures": fixtures,
        "code_digests": summary["code_digests"], "scope": "Four fixtures for the lower-face reference; not qualification of the entire design envelope."}
    write(output / "qualification-input.json", qualification)
    (output / "qualification-input.sha256").write_text(hashlib.sha256((output / "qualification-input.json").read_bytes()).hexdigest() + "\n")
    write(output / "comparison.json", summary)
    return summary


def qualify(input_path, output):
    from environment.mujoco.backend import native_rollout, gpu_rollouts
    from scenario.balancing_cube.adapter import BalancingCubeAdapter
    expected = input_path.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != expected:
        raise ValueError("Qualification input SHA-256 mismatch")
    data = json.loads(input_path.read_text())
    if digest(data["controller"]) != data["controller_digest"] or data["code_digests"] != BalancingCubeAdapter._code_digests():
        raise ValueError("Saved controller or evaluator code changed")
    if output.exists():
        raise ValueError("Use an empty output directory")
    fixtures = data["fixtures"]
    names = [f["id"] for f in fixtures]
    if not names or len(set(names)) != len(names) or any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", n) for n in names):
        raise ValueError("Fixture IDs must be unique portable filenames")
    output.mkdir(parents=True)
    native = []
    for fixture in fixtures:
        try:
            result = native_rollout(fixture["config"], fixture["case"], data["controller"])
        except Exception as error:
            write(output / "qualification.json", {"state": "failed", "phase": "native_mujoco",
                "completed_native_fixtures": len(native), "failed_fixture": fixture["id"],
                "reason": f"{type(error).__name__}: {error}"})
            raise
        native.append(result)
        write(output / f"{fixture['id']}-native.json", result)
    accelerated = gpu_rollouts([f["config"] for f in fixtures], [f["case"] for f in fixtures], data["controller"])
    if accelerated["state"] != "completed":
        write(output / "qualification.json", {"state": "not_run", "reason": accelerated.get("reason")})
        raise RuntimeError("Requested MJX execution did not complete")
    comparisons = []
    for i, fixture in enumerate(fixtures):
        comparison = paired_metrics(native[i], accelerated["results"][i], data["contract"],
            control_period_s=fixture["config"]["physics"]["control_period_s"])
        comparisons.append({"id": fixture["id"], "native_status": native[i]["summary"]["status"],
            "mjx_status": accelerated["results"][i]["summary"]["status"], **comparison})
        write(output / f"{fixture['id']}-mjx.json", accelerated["results"][i])
    result = {"state": "verified_for_fixtures" if all(c["passed"] for c in comparisons) else "inconclusive",
        "source_snapshot_ref": data["source_snapshot_ref"], "input_sha256": expected,
        "controller_digest": data["controller_digest"], "comparisons": comparisons,
        "mjx_backend": accelerated["metadata"], "scope": data["scope"], "physical_verified": False}
    write(output / "qualification.json", result)
    return result


def render_geometry(comparison_dir, output):
    """A schematic from declared wheel centers and MuJoCo inertial COM, in mm."""
    import itertools
    import os
    import tempfile
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ea-cube-matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "ea-cube-cache"))
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from environment.mujoco.model import equilibrium_rotation

    comparison_dir, output = Path(comparison_dir), Path(output)
    data = json.loads((comparison_dir / "comparison.json").read_text())
    cfg = json.loads((comparison_dir / "qualification-input.json").read_text())["fixtures"][0]["config"]
    side, radius = cfg["physics"]["cube_side_m"], cfg["physics"]["wheel_radius_m"]
    r = equilibrium_rotation("vertex")
    vertices = np.array(list(itertools.product((0, side), repeat=3)))
    world = 1000 * vertices @ r.T
    extent = 1000 * side * np.sqrt(3)
    figure = plt.figure(figsize=(12, 6.4), facecolor="#faf9f5")
    for i, (name, title) in enumerate((("upper", "Historical upper-face mounts"), ("lower", "First-trial lower-face mounts")), 1):
        ax = figure.add_subplot(1, 2, i, projection="3d", facecolor="#faf9f5")
        for a in range(8):
            for b in range(a + 1, 8):
                if np.count_nonzero(vertices[a] != vertices[b]) == 1:
                    ax.plot(*world[[a, b]].T, color="#8d989c", linewidth=1.1, alpha=.8)
        centers = np.asarray(data["geometry"][name]["wheel_centers_body_m"])
        angles = np.linspace(0, 2 * np.pi, 100)
        for axis, center in enumerate(centers):
            others = [j for j in range(3) if j != axis]
            ring = np.tile(center, (len(angles), 1))
            ring[:, others[0]] += radius * np.cos(angles)
            ring[:, others[1]] += radius * np.sin(angles)
            ax.plot(*(1000 * ring @ r.T).T, color="#24566d", linewidth=2,
                    label="Reaction wheels" if axis == 0 else None)
        com = 1000 * np.array(data["geometry"][name]["com_above_corner_world_m"])
        ax.plot([0, com[0]], [0, com[1]], [0, com[2]], color="#b64628", linestyle="--", linewidth=1)
        ax.scatter(*com, color="#b64628", s=55, label="Combined center of mass")
        ax.scatter(0, 0, 0, color="#202d34", s=45, marker="^", label="Supporting corner 000")
        ax.text(0, 0, -18, "000", fontsize=10, ha="center")
        ax.set(xlim=(-extent / 2, extent / 2), ylim=(-extent / 2, extent / 2), zlim=(-25, extent),
               xlabel="World X (mm)", ylabel="World Y (mm)", zlabel="Height above corner (mm)")
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=19, azim=-58)
        ax.tick_params(labelsize=8)
        ax.set_title(f"{title}\nCOM height: {com[2]:.1f} mm", fontsize=14, pad=14)
        ax.grid(False)
        if i == 1:
            ax.legend(loc="upper left", bbox_to_anchor=(0, -.08), fontsize=9, frameon=False)
    figure.suptitle("Same mass and wheel inertia; mounting faces change", fontsize=18, y=.98)
    figure.text(.51, .06, "Source: D-000544-52890 geometry and native MuJoCo mass properties\n17 October 2026 · Corner 000 only · Model schematic; hardware is uncalibrated", fontsize=9, ha="center", color="#5b686e")
    figure.subplots_adjust(top=.84, bottom=.19, left=.02, right=.98, wspace=.06)
    output.mkdir(parents=True, exist_ok=False)
    for suffix in ("png", "svg"):
        figure.savefig(output / f"mounting-comparison.{suffix}", dpi=170)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--store", type=Path)
    group.add_argument("--qualification-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.store, args.output) if args.store else qualify(args.qualification_input, args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in {"cells", "controllers", "geometry"}}, indent=2))
    if args.qualification_input and result["state"] != "verified_for_fixtures":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
