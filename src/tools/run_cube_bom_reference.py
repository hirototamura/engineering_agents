"""Catalogue Cube configurations and run a fixed BOM-reference assessment.

Example (from engineering_agents, with the current One-Piece package on PYTHONPATH):
  python -m tools.run_cube_bom_reference --store ../one-piece/projects/balancing-cube/store \
    --bom ../one-piece/projects/balancing-cube/references/remrc_bom_20261021.json \
    --output src/experiments/results/remrc-bom-reference-20261021
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import zipfile

from integrations.one_piece.mechanical_bridge import MechanicalBridge, atomic_json
from scenario.balancing_cube.adapter import BalancingCubeAdapter
from scenario.balancing_cube.bom_reference import (
    REVISION, REVIEWED, LOWER, PART_NAMES, build_reference, compare_requirements, component_for, hold_diagnostic,
)
from scenario.balancing_cube.design import digest, trial_matrix
from scenario.balancing_cube.evaluation import aggregate, screening

PROJECT = "balancing-cube"
STAMP = "2026-10-21T00:00:00Z"  # Revision date, not claimed execution timestamp.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(store, bom):
    from onepiece.model import make_record, ref, digest as record_digest
    history = store.records(PROJECT)
    by_ref = {(r["id"], r["revision"]): r for r in history}
    reviewed = by_ref[("cube.simulation.snapshot", REVIEWED)]
    lower = by_ref[("cube.simulation.snapshot", LOWER)]
    data = build_reference(reviewed["data"], lower["data"], bom)
    records = []

    def add(identifier, kind, data, *, links=None, product="cube.system"):
        record = make_record(project_id=PROJECT, id=identifier, revision=REVISION, kind=kind,
            product_node=product, data=data, links=links, created_at=STAMP,
            actor={"type": "agent", "id": "engineering-agents-bom-reference"})
        records.append(record)
        return record

    bom_record = add("cube.bom.remrc", "bill_of_materials", copy.deepcopy(bom))
    part_records = []
    for part in bom["parts"]:
        p = copy.deepcopy(part)
        p.update(name_en=PART_NAMES[p["part_id"]], bom_ref=ref(bom_record),
                 approval_state="reference_only", selected_hardware=False,
                 component_refs=[{"id": "cube.component." + c, "revision": REVIEWED} for c in component_for(p["part_id"])])
        part_records.append(add("cube.bom.remrc." + p["part_id"], "component_reference", p))
    requirements = [by_ref[(r["id"], r["revision"])] for r in data["context_refs"]["requirements"]]
    comparison = compare_requirements(requirements, {p["part_id"]: p for p in bom["parts"]})
    assessment = add("cube.analysis.remrc-bom-requirements", "analysis_result", {
        "scope": "Part coverage of 22 human-reviewed obligations; not requirement pass/fail or physical verification.",
        "requirement_snapshot_ref": ref(reviewed), "bom_ref": ref(bom_record),
        "comparison": comparison, "physical_verified": False,
        "external_equipment_missing": ["Independent calibrated camera", "Video/MCU synchronization", "Test logger", "Bus current measurement", "Temperature measurement"],
        "source_firmware": {"repository": bom["source_repository"], "period_ms": 15,
            "pwm_hz": 20000, "pwm_resolution_bits": 8, "complementary_weight": .996,
            "gyro_filter_alpha": .7, "executed_in_this_assessment": False},
        "motor_datasheet_scope": "Nidec VF-24H family sheet is for a geared product, not proof of 24H404H160 ratings. No rating is transferred.",
        "motor_datasheet_url": "https://moen.nidec.com/automation/-/media/Project/Nidec/MotionControl/PDFs/MK-Data-Sheets/VF-24H-BLDC-Product-Data-Sheet.pdf"})
    design = add("cube.design.remrc-bom-reference", "design", {
        "physics": data["model"]["physics"], "actuation": data["model"]["actuation"],
        "bom_ref": ref(bom_record), "component_refs": [ref(p) for p in part_records],
        "status": "assumption_based_reference", "adopted_baseline": False, "physical_verified": False,
        "mass_accounting": {"frame_includes_battery_kg": .049, "fixed_mass_remaining_budget_kg": .501,
            "frame_total_kg": .55, "rotating_assembly_kg_each": .06, "total_model_kg": .73,
            "note": "Inherited numerical mass budget; not a sum of BOM measurements. Motor rotor included in wheel aggregate; stator in frame."}})
    data["component_bom"]["bom_ref"] = ref(bom_record)
    data["component_bom"]["assessment_ref"] = ref(assessment)
    snapshot = add("cube.simulation.snapshot", "simulation_snapshot", data,
        links=[{"type": "derive", "target": ref(reviewed)}])
    for stage in ("exploration", "validation", "hold30"):
        add("cube.case.remrc-bom." + stage, "test_case", {
            "stage": stage, "snapshot_ref": ref(snapshot), "domain": "simulation_development",
            "status": "planned", "physical_verified": False,
            "plan": data["plan"][stage] if stage != "hold30" else {
                "count": 10, "seeds": list(range(2101, 2111)), "duration_s": 30,
                "initial_tilt_deg": [1.5, -1.0], "initial_yaw_rate_rad_s": .15,
                "disturbances": [], "domain": "nominal; fixed release, independent sensor noise seeds",
                "checks": "Duration ≥30 s, peak tilt ≤5 deg, whole-interval RMS ≤2 deg, body-origin drift proxy ≤2 mm, contact fraction ≥0.99.",
                "evaluation_scope": "Separate unapproved numerical diagnostic; does not alter the six-second contract or discharge hardware obligations."}},
            product="cube.verification")
    entries = []
    for code, name, role, revision, executable, geometry, authority in [
        ("CM-01", "Reviewed requirements and allocation", "requirements_view", REVIEWED, False,
         "The reviewed snapshot inherits numerical priors; this role selects requirements, not executable defaults.", "Human-reviewed statements/allocation. No hardware adoption."),
        ("CM-02", "Lower-face development configuration", "scenario_default", LOWER, True,
         "Optimized D-000544-52890 descendant; 166.235 mm, lower faces, retained MASS controller.", "Development reference; human-directed topology, no adopted hardware baseline."),
        ("CM-03", "Historical multi-agent experiment", "historical_campaign", "fixed-dt-mvp-2", True,
         "Upper-face configuration family. Each saved candidate has its own compiled mechanical/controller digest.", "Immutable historical evidence. Not the current requirement baseline."),
        ("CM-04", "BOM component reference", "fixed_reference_assessment", REVISION, True,
         "180 mm nominal proxy, 0.730 kg, lower faces. Component identity from BOM; dynamics unmeasured.", "Assumptions authorized for this run. No design iterations or hardware adoption."),
    ]:
        rec = snapshot if revision == REVISION else by_ref[("cube.simulation.snapshot", revision)]
        entry = add("cube.configuration." + code.lower(), "configuration", {
            "catalogue_code": code, "name": name, "role": role, "snapshot_ref": ref(rec),
            "snapshot_record_sha256": record_digest(rec), "runnable": executable,
            "geometry_and_scope": geometry, "authority": authority,
            "adopted_hardware_baseline": False,
            "requirements_refs": rec["data"]["context_refs"]["requirements"],
            "controller_sha256": digest(rec["data"]["controller"]),
            "comparison_design_ref": rec["data"].get("comparison_design_ref"),
            "selection_rule": "Select exact role/ID/revision. Never select by newest timestamp alone."})
        entries.append(entry)
    catalogue = add("cube.configuration.catalogue", "configuration_catalogue", {
        "entries": [ref(r) for r in entries], "reviewed_requirements_ref": ref(entries[0]),
        "scenario_default_ref": ref(entries[1]), "this_assessment_ref": ref(entries[3]),
        "default_changed": False, "history_rewritten": False,
        "additional_preview": {"path": "balancing-cube-simulation/config/first_trial_bottom.json",
            "role": "standalone ideal-pivot demonstration", "equivalent_to_contact_campaign": False},
        "change_control": "Append a new revision when inputs, selection, assumptions, controller or test conditions change. New runs pin that revision. Reviewed requirements and adopted baselines require human decisions."})
    store._check_references(history + records)
    return records, comparison, entries, catalogue


def execute(store_path, bom_path, output, *, resume=False):
    from onepiece import Store
    from onepiece.model import make_record, ref
    from environment.mujoco.backend import native_rollout
    from environment.mujoco.contact import build_contact_xml
    from datetime import datetime, timezone
    import mujoco
    import numpy
    import scipy
    output = Path(output)
    if output.exists() and not resume:
        raise FileExistsError("Run output already exists. Use a fresh directory or --resume for this exact run.")
    output.mkdir(parents=True, exist_ok=True)
    bom = json.loads(Path(bom_path).read_text())
    store = Store(store_path)
    records, comparison, entries, catalogue = prepare(store, bom)
    receipt = store.import_records(records)
    bridge = MechanicalBridge(store_path, snapshot_revision=REVISION)
    snapshot = bridge.load_snapshot()
    adapter = BalancingCubeAdapter(snapshot)
    compiled = adapter.compile({"id": "remrc-bom-reference", "family": "reference",
                                "hypothesis": "Assess one component reference under explicit priors; no optimization."})
    environment = {**adapter.reset(), "python": sys.version, "platform": platform.platform(),
        "numpy": numpy.__version__, "scipy": scipy.__version__, "mujoco": mujoco.__version__,
        "runner_sha256": sha(__file__), "reference_builder_sha256": sha(Path(__file__).parents[1] / "scenario/balancing_cube/bom_reference.py")}
    identity = digest({"compiled": compiled, "environment": environment})
    identity_path = output / "run-identity.json"
    if identity_path.exists() and json.loads(identity_path.read_text())["digest"] != identity:
        raise ValueError("Resume input/code/environment mismatch. Use a new output directory.")
    if resume and (output / "result-records.json").exists():
        saved = json.loads((output / "result-records.json").read_text())
        store.import_records(saved, artifacts_root=output)
        return json.loads((output / "summary.json").read_text())
    if not identity_path.exists():
        atomic_json(identity_path, {"digest": identity, "started_at": datetime.now(timezone.utc).isoformat()})
    for name, value in [("input-records.json", records), ("import-receipt.json", receipt), ("bom.json", bom),
                        ("requirements-comparison.json", comparison), ("catalogue.json", [r["data"] for r in entries]),
                        ("frozen-snapshot.json", snapshot), ("compiled.json", compiled), ("environment.json", environment)]:
        atomic_json(output / name, value)
    (output / "model.xml").write_text(build_contact_xml(compiled["config"]))
    code_root = Path(__file__).parents[1]
    for module in [*sorted((code_root / "environment/mujoco").glob("*.py")),
                   code_root / "scenario/balancing_cube/design.py", code_root / "scenario/balancing_cube/evaluation.py",
                   code_root / "scenario/balancing_cube/bom_reference.py", Path(__file__)]:
        dest = output / "source" / module.relative_to(code_root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(module.read_bytes())
    trials = []
    for stage in ("exploration", "validation"):
        trials += [{**t, "stage": stage} for t in trial_matrix(compiled["config"], snapshot, compiled["id"], stage)]
    for seed in range(2101, 2111):
        trials.append({"stage": "hold30", "config": copy.deepcopy(compiled["config"]),
            "key": ("nominal", "manual-release-no-pulse", seed),
            "case": {"id": f"remrc-bom-reference--hold30--{seed}", "seed": seed, "duration_s": 30,
                     "initial_tilt_deg": [1.5, -1], "initial_yaw_rate_rad_s": .15,
                     "control": True, "disturbances": []}})
    atomic_json(output / "test-plan.json", trials)
    results, failures = [], []
    for number, trial in enumerate(trials, 1):
        name = trial["stage"] + "/" + trial["case"]["id"]
        case_dir = output / "cases" / name
        case_dir.mkdir(parents=True, exist_ok=True)
        case_digest = digest({"run": identity, "trial": trial})
        result_path = case_dir / "result.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
            if result["case_digest"] != case_digest:
                raise ValueError("Saved case input mismatch")
        else:
            atomic_json(case_dir / "input.json", {"config": trial["config"], "case": trial["case"],
                                                  "controller": compiled["controller"], "case_digest": case_digest})
            (case_dir / "model.xml").write_text(build_contact_xml(trial["config"]))
            try:
                raw = native_rollout(trial["config"], trial["case"], compiled["controller"])
            except Exception as error:
                failure = {"case": name, "error": type(error).__name__ + ": " + str(error), "case_digest": case_digest}
                atomic_json(case_dir / "execution-error.json", failure)
                failures.append(failure)
                print(f"{number}/{len(trials)} {name}: EXECUTION FAILED", flush=True)
                continue
            result = {**raw, "case_digest": case_digest, "run_id": trial["case"]["id"],
                "stage": trial["stage"], "domain_id": trial["key"][0], "condition_id": trial["key"][1],
                "seed": trial["key"][2], "controller_digest": digest(compiled["controller"]),
                "gpu_state": "not_requested", "physical_verified": False,
                "screening": screening(raw["summary"], snapshot["contract"]) if trial["stage"] != "hold30" else None}
            if trial["stage"] == "hold30":
                result["hold_diagnostic"] = hold_diagnostic(raw)
            atomic_json(result_path, result)
            with (case_dir / "telemetry.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(raw["rows"][0]))
                writer.writeheader()
                writer.writerows(raw["rows"])
        result["artifact_path"] = result_path.relative_to(output).as_posix()
        results.append(result)
        print(f"{number}/{len(trials)} {name}: {result['summary']['status']} at {result['summary']['simulated_duration_s']:.3f}s", flush=True)
    summary = {"run_id": output.name, "snapshot_ref": {"id": "cube.simulation.snapshot", "revision": REVISION},
        "status": "incomplete" if failures else "completed", "execution_failures": failures,
        "requested_cases": len(trials), "completed_cases": len(results),
        "llm_calls": 0, "design_iterations": 0, "configuration_count": 1,
        "physics_timestep_s": .001, "control_period_s": .015,
        "controller_digest": digest(compiled["controller"]), "input_digest": compiled["input_digest"],
        "backend": "native MuJoCo", "mjx_status": "not_requested", "physical_verified": False,
        "electrical_energy_j": None, "temperature_prediction_c": None, "stages": {}}
    for stage in ("exploration", "validation"):
        group = [r for r in results if r["stage"] == stage]
        if len(group) == 12:
            agg = aggregate(group, snapshot, [t["key"] for t in trials if t["stage"] == stage])
            summary["stages"][stage] = {k: v for k, v in agg.items() if k != "records"}
        else:
            summary["stages"][stage] = {"status": "incomplete", "trial_count": len(group)}
    hold = [r for r in results if r["stage"] == "hold30"]
    summary["stages"]["hold30"] = {"trial_count": len(hold),
        "completed_30s": sum(r["hold_diagnostic"]["checks"]["duration_30s"] for r in hold),
        "numerical_analogues_passed": sum(r["hold_diagnostic"]["passed_numerical_analogues"] for r in hold),
        "scope": "Ten fixed-release, varied-noise simulations; not hardware R-REPEAT verification."}
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(output / "summary.json", summary)
    atomic_json(output / "results.json", results)
    compact = [{k: v for k, v in r.items() if k not in {"rows", "frames"}} for r in results]
    atomic_json(output / "case-summaries.json", compact)
    # Store compact results in canonical JSON. Preserve full evidence in hashed objects.
    archive = output / "evidence.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name not in {"evidence.zip", "result-records.json", "result-receipt.json", "index.html"}:
                bundle.write(path, path.relative_to(output))
    result_records = []
    for stage in ("exploration", "validation", "hold30"):
        result_records.append(make_record(project_id=PROJECT, id="cube.run." + output.name + "." + stage,
            revision=REVISION, kind="simulation_run", product_node="cube.verification",
            created_at=summary["finished_at"], actor={"type": "automation", "id": "engineering-agents-fixed-bom-run"},
            data={"snapshot_ref": summary["snapshot_ref"], "stage": stage, "run_summary": summary,
                  "case_results": [r for r in compact if r["stage"] == stage], "physical_verified": False,
                  "requirements_review_ref": {"id": "cube.simulation.snapshot", "revision": REVIEWED}},
            links=[{"type": "verify", "target": {"id": "cube.case.remrc-bom." + stage, "revision": REVISION},
                    "note": "Numerical development case only; not a hardware requirement pass."}],
            artifacts=[{"path": "evidence.zip", "sha256": sha(archive), "size_bytes": archive.stat().st_size}]))
    atomic_json(output / "result-records.json", result_records)
    result_receipt = store.import_records(result_records, artifacts_root=output)
    atomic_json(output / "result-receipt.json", {"import": result_receipt, "check": store.check(PROJECT)})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--bom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    summary = execute(args.store, args.bom, args.output, resume=args.resume)
    print(json.dumps(summary, indent=2))
    if summary["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
