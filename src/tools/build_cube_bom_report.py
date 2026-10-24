"""Project the fixed BOM assessment into a portable HTML report and CSV views."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def build(run_dir, output):
    run_dir, output = Path(run_dir), Path(output)
    sources = []
    def load(name):
        content = (run_dir / name).read_bytes()
        sources.append({"file": name, "sha256": hashlib.sha256(content).hexdigest()})
        return json.loads(content)
    result = {name: load(file) for name, file in {
        "summary": "summary.json", "catalogue": "catalogue.json", "bom": "bom.json",
        "requirements": "requirements-comparison.json", "compiled": "compiled.json",
        "snapshot": "frozen-snapshot.json", "environment": "environment.json", "plan": "test-plan.json",
    }.items()}
    raw = load("results.json")
    from scenario.balancing_cube.bom_reference import PART_NAMES
    for part in result["bom"]["parts"]:
        part["name_en"] = PART_NAMES[part["part_id"]]
    # Original sampling is retained in all plots. Compact arrays avoid repeating
    # field names 20,000+ times. The HTML does not fetch external data/libraries.
    columns = ["time_s", "tilt_total_deg", "tilt_x_deg", "tilt_y_deg", "omega_z_deg_s",
               "wheel_x_rpm", "wheel_y_rpm", "wheel_z_rpm", "motor_x_nm", "motor_y_nm", "motor_z_nm",
               "pivot_displacement_mm", "normal_force_n", "slip_speed_m_s", "absolute_mechanical_work_j"]
    result["columns"] = columns
    result["cases"] = [{**{k: v for k, v in r.items() if k not in {"rows", "frames"}},
        "samples": [[row[k] for k in columns] for row in r["rows"]],
        "poses": [[f["time_s"], *f["position_m"], *f["quaternion_wxyz"], *f["wheel_angle_rad"]] for f in r["frames"]]}
        for r in raw]
    result["sources"] = sources
    result["raw_results_path"] = str(run_dir.resolve())
    result["evidence_archive_sha256"] = hashlib.sha256((run_dir / "evidence.zip").read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("cube_bom_report.html").read_text()
    output.write_text(template.replace("__REPORT_DATA__", data))
    comparison = run_dir / "requirements-comparison.csv"
    with comparison.open("w", newline="", encoding="utf-8-sig") as stream:
        cols = ["requirement", "revision", "statement", "parts", "coverage_status", "finding", "next_evidence", "hardware_verification_status"]
        writer = csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        for row in result["requirements"]:
            writer.writerow({"requirement": row["requirement_ref"]["id"], "revision": row["requirement_ref"]["revision"],
                "statement": row["statement"], "parts": ", ".join(row["part_ids"]),
                **{key: row[key] for key in cols[4:]}})
    with (run_dir / "case-summaries.csv").open("w", newline="") as stream:
        cols = ["stage", "domain", "condition", "seed", "status", "duration_s", "peak_tilt_deg", "final_1s_rms_deg",
                "whole_interval_rms_deg", "peak_wheel_rpm", "drift_proxy_mm", "continuous_torque_fraction", "failed_checks"]
        writer = csv.DictWriter(stream, fieldnames=cols)
        writer.writeheader()
        for row in raw:
            s = row["summary"]
            writer.writerow(dict(zip(cols, [row["stage"], row["domain_id"], row["condition_id"], row["seed"], s["status"],
                s["simulated_duration_s"], s["peak_tilt_deg"], s["final_1s_tilt_rms_deg"],
                row.get("hold_diagnostic", {}).get("whole_interval_tilt_rms_deg"), s["peak_wheel_rpm"],
                s["peak_pivot_displacement_mm"], s["continuous_torque_exceeded_fraction"],
                ", ".join(c["metric"] for c in row["screening"] if not c["passed"]) if row["screening"] else
                ", ".join(k for k, v in row["hold_diagnostic"]["checks"].items() if not v)])))
    return {"html": str(output.resolve()), "case_count": len(raw), "source_count": len(sources),
            "samples": sum(len(r["rows"]) for r in raw), "bytes": output.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.run_dir, args.output), indent=2))


if __name__ == "__main__":
    main()
