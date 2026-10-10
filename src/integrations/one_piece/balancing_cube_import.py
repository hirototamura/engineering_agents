"""Lossless, bounded migration of the completed cube campaign into One Piece.

No simulator is run and no source is edited. Detailed trial rows and historical
half-timestep adjudication remain content-addressed artifacts. Canonical records
contain independently checked coverage and compact, condition-specific feedback.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ID = "balancing-cube"
SNAPSHOT_ID = "cube.simulation.snapshot"
REVISION = "legacy-20261009"
ACTOR = {"type": "automation", "id": "balancing-cube-history-importer"}
PRODUCTS = {
    "cube.system": "3リアクションホイール・頂点倒立Cube",
    "cube.mechanical": "筐体・重心・接触・ホイール",
    "cube.actuation": "モーター・電源・駆動制約",
    "cube.gnc": "姿勢推定・制御・計測",
    "cube.verification": "数値評価・実機検証基盤",
}


class ImportValidationError(ValueError):
    """The historical evidence does not support the proposed import."""


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _legacy_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _resolve(value: dict, path: str) -> Any:
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _leaves(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _leaves(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, f"{path}.{index}")
    elif isinstance(value, (int, float, bool)) or value is None:
        yield path, value


def _unit(path: str) -> str:
    """SI suffixes are explicit; dimensionless weights are labeled as weights."""
    key = path.split(".")[-1]
    if key.isdigit():
        key = path.split(".")[-2]
    for suffix, unit in [("kg_m2", "kg*m^2"), ("nm_s", "N*m*s"), ("deg_s", "deg/s"),
                         ("rad_s", "rad/s"), ("m_s2", "m/s^2"), ("m_s", "m/s"),
                         ("_mm", "mm"), ("_kg", "kg"), ("_nm", "N*m"),
                         ("_deg", "deg"), ("_hz", "Hz"), ("_s", "s"), ("_m", "m")]:
        if key.endswith(suffix):
            return unit
    return "weight (state-dependent units)" if "_q" in key or "_r" in key else "1"


def _owner(path: str) -> str:
    if path.startswith(("controller", "sensing")):
        return "cube.gnc"
    if path.startswith("actuation") or "motor" in path:
        return "cube.actuation"
    if path.startswith("evaluation"):
        return "cube.verification"
    return "cube.mechanical"


def _expected(stage: dict) -> set[tuple[str, str, int]]:
    return set(itertools.product([d["id"] for d in stage["domains"]],
                                 [c["id"] for c in stage["conditions"]], stage["seeds"]))


def _trial_index(path: Path, plan: dict, candidates: dict) -> tuple[dict, dict]:
    """Check exact sets, not just row counts; retain failure location aggregates."""
    seen = defaultdict(set)
    failures = defaultdict(lambda: defaultdict(lambda: {"trials": 0, "failed_trials": 0,
                                                         "criteria": Counter(), "statuses": Counter()}))
    origin_counts = Counter()
    totals = defaultdict(lambda: {"trials": 0, "passed_trials": 0, "criteria": Counter()})
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            cid, stage = row["candidate_id"], row["stage"]
            if cid not in candidates or stage not in ("exploration", "validation"):
                raise ImportValidationError(f"Unknown trial candidate or stage: {cid}/{stage}")
            origin = row.get("evidence_origin") or "original_campaign"
            key = (cid, stage, origin)
            triple = (row["domain_id"], row["condition_id"], int(row["seed"]))
            if triple in seen[key]:
                raise ImportValidationError(f"Duplicate trial condition: {key}/{triple}")
            seen[key].add(triple)
            if triple not in _expected(plan[stage]):
                raise ImportValidationError(f"Unexpected trial condition: {key}/{triple}")
            origin_counts[origin] += 1
            item = failures[key][triple[:2]]
            item["trials"] += 1
            failed = [x for x in row.get("failure_criteria", "").split("|") if x]
            # Analyzer CSV uses a JSON list for failure criteria.
            raw = row.get("failure_criteria", "")
            if raw.startswith("["):
                failed = json.loads(raw)
            item["failed_trials"] += bool(failed)
            totals[key]["trials"] += 1
            totals[key]["passed_trials"] += row.get("passed", "").lower() == "true"
            totals[key]["criteria"].update(failed)
            item["criteria"].update(failed)
            item["statuses"][row.get("status", "unknown")] += 1
    coverage = {}
    feedback = {}
    for key, actual in seen.items():
        expected = _expected(plan[key[1]])
        if actual != expected:
            raise ImportValidationError(f"Incomplete trial matrix for {key}: missing={sorted(expected-actual)}")
        coverage[key] = {"expected": len(expected), "actual": len(actual), "complete": True,
                         "expected_set_sha256": _digest(sorted(expected)),
                         "actual_set_sha256": _digest(sorted(actual))}
        feedback[key] = [{"domain_id": d, "condition_id": c, **value,
                          "criteria": dict(value["criteria"]), "statuses": dict(value["statuses"])}
                         for (d, c), value in sorted(failures[key].items())]
    return {"sets": coverage, "totals": totals, "origin_counts": dict(origin_counts)}, feedback


def _compact(summary: dict) -> dict:
    # Scores alone are insufficient: retain per-domain metrics and failure classes.
    keys = ("job_id", "state", "worker", "error", "score", "pass_fraction", "all_pass",
            "numeric_verified", "trials", "passed_trials", "coverage_complete", "failures",
            "metrics", "agreement_statuses", "gate_sources", "accelerated", "cost")
    result = {k: summary[k] for k in keys if k in summary}
    result["domains"] = [{k: v for k, v in d.items() if k != "metrics"} for d in summary.get("domains", [])]
    return result


def build_records(source: str | Path, *, project_id: str = PROJECT_ID) -> tuple[list[dict], dict]:
    """Build deterministic records, validating the legacy summary against raw CSV."""
    from onepiece import make_record, ref

    source = Path(source).resolve()
    report_dir = source / "report"
    analysis = _read(report_dir / "analysis.json")
    snapshot = _read(report_dir / "sources/snapshot.json")
    controller = _read(report_dir / "sources/controller.json")
    supplemental = _read(report_dir / "supplemental-confirmations.json")
    candidates = {c["id"]: c for c in analysis["candidates"]}
    if len(candidates) != len(analysis["candidates"]):
        raise ImportValidationError("Duplicate candidate IDs")
    if len(candidates) != analysis["overview"]["candidate_count"]:
        raise ImportValidationError("Candidate count disagrees with overview")
    prior_ids = analysis["prior46"]["ids"]
    if len(set(prior_ids)) != analysis["prior46"]["count"] or set(prior_ids) - candidates.keys():
        raise ImportValidationError("Invalid prior-candidate coverage")
    prior_counts = dict(Counter(candidates[c]["status"] for c in prior_ids))
    if prior_counts != analysis["prior46"]["status_counts"]:
        raise ImportValidationError("Prior-candidate outcomes disagree with candidate records")
    trial_coverage, trial_feedback = _trial_index(report_dir / "trials.csv", snapshot["plan"], candidates)
    # Every completed exploration and every original/supplemental confirmation must exist.
    supplemental_ids = [r["candidate_id"] for r in supplemental["results"] if r["state"] == "completed"]
    if len(set(supplemental_ids)) != len(supplemental_ids) or set(supplemental_ids) - candidates.keys():
        raise ImportValidationError("Duplicate/unknown supplemental candidate")
    campaign = _read(report_dir / "sources/campaign.json")
    if _legacy_digest(snapshot) != campaign["snapshot_digest"] or _legacy_digest(snapshot["contract"]) != campaign["contract_digest"] or _legacy_digest(controller) != campaign["controller_digest"]:
        raise ImportValidationError("Frozen snapshot/controller/contract digest mismatch")
    for field in ("contract_digest", "controller_digest"):
        if supplemental["provenance"].get(field) != campaign[field]:
            raise ImportValidationError("Supplemental " + field + " mismatch")
    for entry in supplemental["results"]:
        if entry["state"] == "completed" and entry["result"]["candidate_input_digest"] != candidates[entry["candidate_id"]]["input_digest"]:
            raise ImportValidationError("Supplemental input digest mismatch")
    if supplemental["provenance"]["source_campaign_revision"] != analysis["provenance"]["campaign_revision"]:
        raise ImportValidationError("Supplemental campaign mismatch")
    counts = analysis["overview"]["counts"]
    expected_groups = {(cid, "exploration", "original_campaign") for cid, c in candidates.items()
                       if c["exploration"]["state"] == "completed"}
    original_validation_ids = set()
    for cid, c in candidates.items():
        original = c.get("original_validation", c["validation"])
        if original.get("state") == "completed":
            original_validation_ids.add(cid)
            expected_groups.add((cid, "validation", "original_campaign"))
    expected_groups.update((cid, "validation", "supplemental_native_cpu") for cid in supplemental_ids)
    if expected_groups != set(trial_coverage["sets"]):
        raise ImportValidationError("Trial coverage groups differ from candidate/stage records")
    actual_passes = sum(c["status"] == "confirmed_numerical_pass" for c in candidates.values())
    if actual_passes != counts["confirmed_pass"]:
        raise ImportValidationError("Confirmed pass count disagrees with candidate records")
    created_at = analysis["overview"]["launch"]["finished_at"]
    records = []

    def add(id: str, kind: str, data: dict, *, revision=REVISION,
            product="cube.system", links=None, artifacts=None):
        record = make_record(project_id=project_id, id=id, kind=kind, revision=revision,
                             product_node=product, data=data, links=links, artifacts=artifacts,
                             actor=ACTOR, created_at=created_at)
        records.append(record)
        return record

    def edge(type: str, target: str, revision=REVISION, **details):
        return {"type": type, "target": ref(target, revision), **details}

    for id, label in PRODUCTS.items():
        add(id, "product", {"name": label, "status": "concept", "physical_verified": None},
            product=id)

    mission = snapshot["mission"]
    mrev = mission["revision"]
    hierarchy = {
        "cube.req.system": ("システム要求草案", "system", "cube.system", "M-VERTEX", mrev),
        "cube.req.operation": ("運用要求草案", "operational", "cube.system", "cube.req.system", REVISION),
        "cube.req.mechanical": ("機械・調達要求草案", "subsystem", "cube.mechanical", "cube.req.system", REVISION),
        "cube.req.gnc": ("GNC要求草案", "subsystem", "cube.gnc", "cube.req.system", REVISION),
        "cube.req.verification": ("検証基盤要求草案", "verification_platform", "cube.verification", "cube.req.system", REVISION),
    }
    for id, (name, level, owner, parent, prev) in hierarchy.items():
        add(id, "requirement", {"name": name, "level": level, "status": "draft", "value": None,
                                "unit": "1", "imported_hierarchy_draft": True,
                                "source": "既存要求を閲覧するための取込時階層草案。人間の確定なし"},
            product=owner, links=[edge("derive", parent, prev), edge("allocate", owner)])
    requirements = []
    for req in mission["requirements"]:
        id = req["id"]
        group = "cube.req.mechanical" if id.startswith("C-") else "cube.req.operation" if id in {"R-HOLD", "R-REPEAT"} else "cube.req.gnc" if id in {"R-YAW", "R-VISION", "R-SYNC"} else "cube.req.verification"
        owner = hierarchy[group][2]
        links = [edge("allocate", owner)]
        if id != "M-VERTEX":
            links.append(edge("derive", group, note="draft decomposition; original source had no parent"))
        requirements.append(add(id, "requirement", {**req, "level": "mission" if id == "M-VERTEX" else hierarchy[group][1],
                                                   "original_record": True, "physical_verified": None},
                                revision=mrev, product=owner if id != "M-VERTEX" else "cube.system", links=links))
    krev = snapshot["kdps"]["revision"]
    parameters = []
    bindings = []
    for param in snapshot["kdps"]["entries"]:
        path = param.get("model_path")
        product = _owner(path or "")
        links = [edge("allocate", product)]
        parameters.append(add(param["id"], "parameter", dict(param), revision=krev, product=product, links=links))
        if path:
            try:
                actual = _resolve(snapshot["model"], path)
            except (KeyError, IndexError, ValueError):
                raise ImportValidationError("KDP model_path is not in frozen model: " + path)
            bindings.append({"model_path": path, "parameter_ref": ref(param["id"], krev),
                             "value_source": "model", "registered_value": param["value"],
                             "resolved_value": actual, "values_match": param["value"] == actual,
                             "note": "historical model is authoritative; registry preserved without overwrite"})
    bound = {b["model_path"]: b for b in bindings}
    for path, value in _leaves(snapshot["model"]):
        if path.startswith("reference"):
            continue
        binding = bound.get(path)
        add("cube.model." + path, "model_parameter",
            {"name": path, "model_path": path, "value": value,
             "unit": next((p["data"]["unit"] for p in parameters if p["data"].get("model_path") == path), _unit(path)),
             "value_source": ref(SNAPSHOT_ID, REVISION), "authoritative_field": "data.model." + path,
             "registry_binding": binding, "status": "unmeasured_model_prior"}, product=_owner(path),
            links=[edge("allocate", _owner(path))])
    bounds = {"side_m": [.14, .22], "print_mass_ref_kg": [.08, .25], "wheel_mass_kg": [.035, .09],
              "wheel_radius_ratio": [.23, .40], "inner_radius_ratio": [.65, .92], "wheel_thickness_m": [.004, .010]}
    refs = {"model": ref(SNAPSHOT_ID, REVISION), "contract": ref(SNAPSHOT_ID, REVISION),
            "plan": ref(SNAPSHOT_ID, REVISION), "families": ref(SNAPSHOT_ID, REVISION),
            "requirements": [ref(r) for r in requirements], "kdps": [ref(p) for p in parameters]}
    historical_snapshot = add(SNAPSHOT_ID, "simulation_snapshot", {**snapshot, "controller": controller, "design_bounds": bounds,
                                            "context_refs": refs, "parameter_bindings": bindings,
                                            "history_only": True, "source_campaign_revision": analysis["provenance"]["campaign_revision"],
                                            "new_run_policy": "fixed_timestep_cpu_gpu_no_half_step",
                                            "physical_fidelity": None},
        links=[])
    best_reference = analysis.get("best", {}).get("original_confirmed", [])
    if best_reference:
        best_id = best_reference[0]["id"]
        if best_id not in candidates or candidates[best_id]["validation_origin"] != "original_campaign":
            raise ImportValidationError("Comparison reference must have original paired CPU/GPU evidence")
        add(SNAPSHOT_ID, "simulation_snapshot", {
            **historical_snapshot["data"], "history_only": False,
            "comparison_design_ref": ref(best_id, REVISION),
            "comparison_scope": "best original paired numerical reference; not human-adopted baseline",
            "controller_design_plant": "model remains the frozen nominal LQR linearization plant",
        }, revision="fixed-dt-mvp-1", links=[edge("derive", SNAPSHOT_ID)])

    # Register originals and derived evidence once, not one artifact copy per candidate.
    artifact_specs = {
        "analysis": report_dir / "analysis.json", "trials": report_dir / "trials.csv",
        "candidates": report_dir / "candidates.csv", "prior46": report_dir / "prior46.csv",
        "legacy-report": report_dir / "index.html", "replay": report_dir / "replay.json",
        "supplemental": report_dir / "supplemental-confirmations.json",
        "best-video": report_dir / "best-stress.mp4", "baseline-video": report_dir / "baseline-stress.mp4",
        "gnc-data": source / "gnc-report/gnc-data.json", "gnc-report": source / "gnc-report/index.html",
    }
    campaign_path = source / Path(analysis["provenance"]["campaign_directory"]).name
    artifact_specs.update({"campaign-" + p.name.replace(".", "-"): p for p in sorted(campaign_path.iterdir()) if p.is_file()})
    for p in sorted((report_dir / "models").glob("*.xml")):
        artifact_specs["replay-" + p.stem] = p
    for p in sorted(source.glob("*.zip")):
        artifact_specs["bundle-" + p.stem] = p
    artifact_list = []
    for name, path in artifact_specs.items():
        if not path.is_file():
            if name in {"trials", "analysis", "replay", "supplemental", "gnc-data"}:
                raise ImportValidationError("Required artifact missing: " + str(path))
            continue
        artifact = {"path": path.relative_to(source).as_posix(), "sha256": _sha(path),
                    "size_bytes": path.stat().st_size, "uri": path.as_uri()}
        artifact_list.append(artifact)
        add("cube.artifact." + name, "artifact", {"name": name, "history_only": True,
                                                 "data_origin": "simulation", "physical_fidelity": None},
            product="cube.verification", artifacts=[artifact])
    required_raw = campaign_path / "jobs.sqlite"
    if not required_raw.is_file():
        raise ImportValidationError("Original SQLite artifact is required")

    for stage in ("exploration", "validation"):
        add("cube.case." + stage, "test_case", {"stage": stage, "expected_conditions": sorted(_expected(snapshot["plan"][stage])), "snapshot_ref": ref(SNAPSHOT_ID, REVISION), "history_only": True}, product="cube.verification")
    # Direction is specification/requirement -> parameter/design, never reverse.
    for requirement in requirements:
        requirement["links"].extend(edge("constrain", p["id"], krev) for p in parameters if requirement["id"] in p["data"].get("requirements", []))
    for cid, c in candidates.items():
        data = {k: c.get(k) for k in ("family", "parent_id", "hypothesis", "parameters", "physics", "actuation", "assumptions", "input_digest", "status", "original_status", "validation_origin")}
        data.update({"physical_fidelity": None, "adopted_baseline": False, "history_only": True,
                     "controller_ref": ref(SNAPSHOT_ID, REVISION)})
        links = [edge("satisfy", "M-VERTEX", mrev, note="design intent declaration, not verification evidence"),
                 ]
        if c.get("parent_id") in candidates:
            data["parent_ref"] = ref(c["parent_id"], REVISION)
            links.append(edge("derive", c["parent_id"]))
        add(cid, "design", data, links=links)
        stages = [("exploration", "original_campaign", c["exploration"])]
        if cid in original_validation_ids:
            stages.append(("validation", "original_campaign", c.get("original_validation", c["validation"])))
        if cid in supplemental_ids:
            stages.append(("validation", "supplemental_native_cpu", c["validation"]))
        for stage, origin, summary in stages:
            key = (cid, stage, origin)
            coverage = trial_coverage["sets"].get(key)
            if not coverage:
                raise ImportValidationError("Missing completed stage coverage: " + str(key))
            totals = trial_coverage["totals"][key]
            if totals["trials"] != summary["trials"] or totals["passed_trials"] != summary["passed_trials"] or dict(totals["criteria"]) != summary["failures"]:
                raise ImportValidationError("CSV/summary outcomes disagree: " + str(key))
            add(f"cube.eval.{cid}.{stage}.{origin}", "evaluation",
                {"candidate_id": cid, "design_ref": ref(cid, REVISION), "stage": stage,
                 "verification_origin": origin, "history_only": True,
                 "half_timestep_evidence": origin == "supplemental_native_cpu" or "native_cpu_half_step" in summary.get("gate_sources", {}),
                 "claims_new_gpu_pair": False if origin == "supplemental_native_cpu" else None,
                 "physical_fidelity": None, "coverage": coverage, "summary": _compact(summary),
                 "conditions": trial_feedback[key],
                 "raw_trial_selector": {"artifact_ref": ref("cube.artifact.trials", REVISION),
                                        "candidate_id": cid, "stage": stage, "evidence_origin": origin}},
                product="cube.verification", links=[edge("verify", "M-VERTEX", mrev, note="numerical development evidence only; physical requirement not demonstrated"),
                                                     edge("verify", "cube.case." + stage)])

    add("cube.eval.specification", "specification",
        {"name": "固定された数値開発評価規約", "scope": "numerical_development_only",
         "success_criteria": analysis["criteria"], "snapshot_ref": ref(SNAPSHOT_ID, REVISION), "history_only": True},
        product="cube.verification", links=[edge("constrain", cid) for cid in candidates])
    add("cube.verification.coverage", "verification_coverage",
        {"candidate_count": len(candidates), "expected_candidate_count": analysis["overview"]["candidate_count"],
         "complete": True, "candidate_set_sha256": _digest(sorted(candidates)),
         "exploration_candidates": len(expected_groups & {(cid, "exploration", "original_campaign") for cid in candidates}),
         "original_validation_candidates": len(original_validation_ids), "supplemental_candidates": len(supplemental_ids),
         "trial_origin_counts": trial_coverage["origin_counts"],
         "expected_sets": {stage: sorted(_expected(snapshot["plan"][stage])) for stage in ("exploration", "validation")},
         "prior46": {"ids": prior_ids, "counts": prior_counts, "complete": True},
         "source": ref("cube.artifact.trials", REVISION)}, product="cube.verification",
        links=[])
    summary_data = {k: analysis[k] for k in ("overview", "timeline", "benchmark", "telemetry", "criteria", "failure_analysis", "agreement", "limitations", "null_unmeasured")}
    summary_data.update({"history_only": True, "physical_fidelity": None,
                         "prior46": {k: analysis["prior46"][k] for k in ("count", "ids", "status_counts", "original_status_counts")},
                         "best": {k: [c["id"] for c in analysis["best"].get(k, [])] for k in ("confirmed", "original_confirmed", "supplemental_confirmed", "provisional")},
                         "provenance": analysis["provenance"], "supplemental_provenance": supplemental["provenance"],
                         "historical_policy_note": "Original CPU half-step adjudication and supplemental dt/2 checks are imported as history only. New campaigns never use half-step adjudication."})
    add("cube.campaign.summary", "campaign_summary", summary_data, product="cube.verification",
        links=[])
    add("cube.iteration.legacy", "iteration",
        {"status": "completed", "candidate_count": len(candidates), "history_only": True,
         "outcome": "numerical_development_evidence", "best_design_ref": ref(analysis["best"]["original_confirmed"][0]["id"], REVISION),
         "adopted_baseline": None, "next_action": "Human review of assumptions, requirements/evaluation and baseline; bounded new configuration trials.",
         "physical_verified": None, "changes": "Legacy mechanical exploration with a common fixed nominal controller."},
        links=[])
    result = {"schema_version": "1.0", "project_id": project_id, "records": len(records),
              "kinds": dict(Counter(r["kind"] for r in records)), "candidates": len(candidates),
              "original_requirements": len(requirements), "kdps": len(parameters),
              "prior46": prior_counts, "best_original": analysis["best"]["original_confirmed"][0]["id"],
              "verification_origins": trial_coverage["origin_counts"],
              "canonical_bytes": len(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()),
              "artifact_bytes": sum(a["size_bytes"] for a in artifact_list),
              "source_unchanged": True, "hardware_physical_validity": None}
    return records, result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="gpu-results-final directory")
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--records", type=Path, help="optional portable canonical records JSON")
    parser.add_argument("--report", type=Path, help="optional offline HTML report")
    args = parser.parse_args(argv)
    from onepiece import Store
    records, summary = build_records(args.source, project_id=args.project_id)
    store = Store(args.store)
    summary["import"] = store.import_records(records, artifacts_root=args.source)
    check = store.check(args.project_id)
    summary["check"] = check
    if not check["ok"]:
        raise ImportValidationError("Imported store failed integrity check: " + str(check))
    if args.records:
        args.records.parent.mkdir(parents=True, exist_ok=True)
        args.records.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if args.report:
        from onepiece.report import report
        summary["report"] = str(report(store, args.report, project_id=args.project_id))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
