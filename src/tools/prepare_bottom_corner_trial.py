"""Prepare the user-requested corner-000 development model as a new SSOT revision.

No historical record, requirement approval, evaluation gate or adopted baseline
is overwritten. English requirements precede their Japanese translations.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

REVISION = "bottom-corner-000-20261017-3"
PROJECT = "balancing-cube"


def prepare(store, output):
    from onepiece.model import make_record, ref, digest
    from onepiece.store import current_records

    output = Path(output)
    if output.exists():
        raise ValueError("Use a new output directory; prepared inputs remain immutable")
    history = store.records(PROJECT)
    if any(r["revision"] == REVISION for r in history):
        raise ValueError("This revision already exists; retry the saved records.json import instead of preparing it again")
    by_ref = {(r["id"], r["revision"]): r for r in history}
    latest = {r["id"]: r for r in current_records(history)}
    source = by_ref[("cube.simulation.snapshot", "standards-draft-20261011-2")]
    data = copy.deepcopy(source["data"])
    now = datetime.now(timezone.utc).isoformat()
    records = []
    def edge(kind, target):
        return {"type": kind, "target": ref(target)}
    def add(identifier, kind, payload, product="cube.system", links=None):
        r = make_record(project_id=PROJECT, id=identifier, revision=REVISION,
            kind=kind, product_node=product, data=payload, links=links or [],
            actor={"type": "agent", "id": "bottom-corner-trial-preparation"}, created_at=now)
        records.append(r)
        return r
    old_mission = latest["M-VERTEX"]
    mission_data = copy.deepcopy(old_mission["data"])
    mission_data.update(name="Eight-corner balancing mission",
        statement="The Cube shall balance on each of its 8 corners with its 3 reaction wheels.",
        rationale="The user clarified that the mission covers all eight corners, not one selected corner.",
        source="Direct user clarification on 17 October 2026.", source_status="user_clarified_intent",
        status="draft", approval_state="pending_formal_wording_review", physical_verified=None,
        source_record={**ref(old_mission), "sha256": digest(old_mission)}, supersedes=ref(old_mission),
        acceptance_criteria={"domain": "hardware", "metric": "distinct_corners_demonstrated",
                             "operator": "==", "value": 8, "unit": "count"},
        verification_case_ref={"id": "cube.verify.M-VERTEX", "revision": REVISION},
        verification_status="not_run")
    mission_data["translations"] = {"ja": {
        "name": "8頂点での倒立保持ミッション",
        "statement": "Cubeは、3個のリアクションホイールを用いて8頂点のそれぞれで倒立保持しなければならない。",
        "rationale": "ユーザーは、ミッションの対象が選択した1頂点ではなく8頂点すべてであると明確にした。",
        "acceptance_criteria": "実機で保持を示した頂点の数が8であること。"}}
    mission = add("M-VERTEX", "requirement", mission_data,
        links=[edge("allocate", latest["cube.system"]), edge("derive", old_mission)])
    mission_case = add("cube.verify.M-VERTEX", "verification_case", {
        "requirement_refs": [ref(mission)], "verification_method": "test", "status": "planned",
        "domain": "hardware", "corners": [f"{i:03b}" for i in range(8)],
        "execution_status": "not_run", "physical_verified": None,
        "unresolved": ["Hardware procedure, hold duration and per-corner tolerances require review.",
                       "Seven other support-corner models and controller equilibria are not implemented by this change."]},
        product="cube.verification")
    def requirement(identifier, en, ja, parent, product):
        first = identifier == "R-FIRST-CORNER"
        return add(identifier, "requirement", {
            "name": en, "statement": en, "source_language": "en", "normative_modal": "shall",
            "obligation": "requirement", "record_role": "requirement",
            "level": "system" if identifier == "R-FIRST-CORNER" else "subsystem",
            "status": "draft", "approval_state": "pending_formal_wording_review",
            "source": "Direct user instruction on 17 October 2026.",
            "rationale": "Limit the first development trial while retaining the eight-corner mission.",
            "conditions": ["Body coordinates start at corner 000 and extend along the three positive cube edges.",
                           "Wheel centers use the declared face inset; the mounting faces do not change during a run."],
            "acceptance_criteria": {"domain": "simulation_configuration", "operator": "==", "unit": "1",
                "metric": "support_corner" if first else "wheel_centers_on_incident_faces",
                "value": "000" if first else True},
            "parent_ref": ref(parent), "verification_method": "inspection",
            "verification_status": "not_run", "physical_verified": None,
            "translations": {"ja": {"name": ja, "statement": ja}}}, product,
            [edge("derive", parent), edge("allocate", latest[product])])
    trial = requirement("R-FIRST-CORNER",
        "The first development simulation shall evaluate the Cube on corner 000.",
        "最初の開発シミュレーションは、Cubeを頂点000で評価しなければならない。", mission, "cube.system")
    mounting = requirement("R-WHEEL-MOUNT-000",
        "The first-trial model shall place its 3 reaction wheels on the faces incident to corner 000.",
        "初回試験モデルは、3個のリアクションホイールを頂点000に接する3面に配置しなければならない。",
        trial, "cube.actuation")
    parameter = add("D-WHEEL-MOUNT-SIDE", "parameter", {
        "name": "Reaction-wheel mounting faces", "value": "near_corner_000", "unit": "1",
        "model_path": "physics.wheel_mount_side", "origin": "user_design_choice",
        "status": "development_configuration", "automatic_change_allowed": False,
        "rationale": "Fixed first-trial topology; not an additional automatic design variable.",
        "translations": {"ja": {"name": "リアクションホイールの取付面"}}}, "cube.actuation",
        [edge("allocate", latest["cube.actuation"])])
    mounting["links"].append(edge("constrain", parameter))
    data["model"]["physics"]["wheel_mount_side"] = "near_corner_000"
    selected_controller = by_ref[("cube-f069bd6e148e43e0a411.candidate.10", "1")]
    data["controller"] = copy.deepcopy(selected_controller["data"]["controller"])
    data["controller_source_ref"] = ref(selected_controller)
    data["controller_design_snapshot_ref"] = ref(source)
    data["controller_design_plant"] = "Retain the measured MASS selection and its frozen upper-face nominal design plant. Lower-face native trials passed 12/12; two relinearized alternatives performed worse."
    data["controller_selection_evidence_ref"] = {"id": "cube.analysis.bottom000.current-controller", "revision": "1"}
    comparison_source = by_ref[(data["comparison_design_ref"]["id"], data["comparison_design_ref"]["revision"])]
    comparison_data = {k: copy.deepcopy(comparison_source["data"][k]) for k in ("physics", "actuation", "family", "parameters")}
    comparison_data["physics"]["wheel_mount_side"] = "near_corner_000"
    comparison_data.update(source_design_ref=ref(comparison_source), status="unverified_development_reference",
        adopted_baseline=False, physical_verified=False,
        hypothesis="Move the reference design's wheels to the three faces incident to corner 000; evaluate with the rebuilt nominal controller.")
    comparison = add("D-000544-52890.bottom000", "design", comparison_data,
        links=[edge("derive", comparison_source), edge("satisfy", mounting)])
    snapshot_ref = {"id": "cube.simulation.snapshot", "revision": REVISION}
    data.update(supersedes=ref(source), comparison_design_ref=ref(comparison), history_only=False,
        comparison_scope="Unverified lower-face descendant of D-000544-52890; not the historical best result or an adopted baseline.",
        trial_scope={"support_corner": "000", "mission_corner_count": 8,
            "implemented_support_corner_count": 1, "other_corners_verified": False,
            "physical_verified": False, "mounts_move_between_corners": False},
        source_change_note="User requested lower incident-face mounts for the first trial and an eight-corner mission. Numerical gates and timing are inherited unchanged.")
    refs = data["context_refs"]
    refs["requirements"] = [ref(mission) if r["id"] == "M-VERTEX" else r for r in refs["requirements"]] + [ref(trial), ref(mounting)]
    refs["kdps"].append(ref(parameter))
    entries = data["kdps"]["entries"] if isinstance(data["kdps"], dict) else data["kdps"]
    entries.append(copy.deepcopy(parameter["data"]))
    refs["model"] = snapshot_ref
    data["parameter_bindings"].append({"model_path": "physics.wheel_mount_side", "parameter_ref": ref(parameter),
        "value_source": "model", "registered_value": "near_corner_000", "resolved_value": "near_corner_000", "values_match": True})
    data["mission"]["mission"] = mission_data["statement"]
    data["mission"]["scope"] = "Eight-corner mission; this development model implements only support corner 000."
    for item in data["mission"].get("requirements", []):
        if item.get("id") == "M-VERTEX":
            item.update(name=mission_data["name"], statement=mission_data["statement"], status="draft", source_record=ref(mission))
    snapshot = add("cube.simulation.snapshot", "simulation_snapshot", data,
        links=[edge("derive", source)])
    previous = latest.get("cube.simulation.snapshot")
    if previous and previous["revision"].startswith("bottom-corner-000-"):
        data["supersedes"] = ref(previous)
        snapshot["links"].append(edge("derive", previous))
    mounting["links"].append(edge("constrain", snapshot))
    add("cube.model.parameter.wheel_mount_side", "model_parameter", {
        "model_path": "physics.wheel_mount_side", "value": "near_corner_000", "unit": "1",
        "value_source": ref(snapshot), "authoritative_field": "data.model.physics.wheel_mount_side",
        "registry_binding": data["parameter_bindings"][-1]}, "cube.actuation",
        [edge("allocate", latest["cube.actuation"])])
    for stage in ("exploration", "validation"):
        add("cube.case.bottom000." + stage, "test_case", {
            "stage": stage, "snapshot_ref": ref(snapshot), "requirement_refs": [ref(trial)],
            "status": "planned", "evidence_scope": "six-second numerical development; corner 000 only",
            "physical_verified": False}, "cube.verification")
    active_data = copy.deepcopy(latest["cube.system-model.active"]["data"])
    active_data.update(simulation_snapshot_ref=ref(snapshot), supersedes=ref(latest["cube.system-model.active"]),
        source_snapshot_ref=ref(source), scope="Lower-face first-trial model; eight-corner mission remains unverified; no adopted baseline.")
    add("cube.system-model.active", latest["cube.system-model.active"]["kind"], active_data,
        links=[edge("derive", latest["cube.system-model.active"])])
    store._check_references(history + records)
    output.mkdir(parents=True)
    for name, value in (("records.json", records), ("config.json", data["model"]),
                        ("controller.json", data["controller"]), ("source-snapshot.json", source)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return records


def main():
    from onepiece import Store
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--import-records", action="store_true")
    args = parser.parse_args()
    store = Store(args.store)
    records = prepare(store, args.output)
    if args.import_records:
        result = store.import_records(records)
        check = store.check(PROJECT)
        (args.output / "import-receipt.json").write_text(json.dumps({"import": result, "check": check}, indent=2) + "\n")
        if not check["ok"]:
            raise RuntimeError("One-Piece check failed")
        print(json.dumps({"import": result, "check": check}, indent=2))


if __name__ == "__main__":
    main()
