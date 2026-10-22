"""Versioned SSOT input and durable outbox for mechanical design scenarios.

The physical runner never imports One Piece. Scenario orchestration uses this
adapter; a failed sync leaves a durable outbox entry and the run evidence intact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path


_CONTEXT_EXCLUSIONS = Path(__file__).with_name("agent_context_exclusions.json")


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class MechanicalBridge:
    def __init__(self, store_path, *, project_id="balancing-cube",
                 snapshot_id="cube.simulation.snapshot", snapshot_revision="fixed-dt-mvp-2"):
        from onepiece import Store
        self.store = Store(store_path)
        self.project_id = project_id
        self.snapshot_id, self.snapshot_revision = snapshot_id, snapshot_revision

    def load_snapshot(self):
        check = self.store.check(self.project_id)
        if not check["ok"]:
            raise ValueError("SSOT integrity check failed: " + "; ".join(check["errors"]))
        all_records = self.store.records(self.project_id)
        selected = next((r for r in all_records if r["kind"] == "simulation_snapshot"
                         and r["id"] == self.snapshot_id and r["revision"] == self.snapshot_revision), None)
        if selected is None:
            raise ValueError("A versioned simulation snapshot must first be imported into One Piece")
        snapshot = copy.deepcopy(selected["data"])
        by_ref = {(r["id"], r["revision"]): r for r in all_records}
        context_refs = snapshot.get("context_refs", {})
        def resolve(name, kind):
            refs = context_refs.get(name)
            if not refs:
                raise ValueError("Frozen SSOT snapshot requires exact " + name + " references")
            resolved = []
            for reference in refs:
                record = by_ref.get((reference.get("id"), reference.get("revision")))
                if record is None or record["kind"] != kind:
                    raise ValueError("Missing/mismatched frozen SSOT " + name + " revision")
                resolved.append(copy.deepcopy(record))
            return resolved
        snapshot["requirements"] = resolve("requirements", "requirement")
        parameters = resolve("kdps", "parameter")
        raw = snapshot["kdps"]
        entries = raw["entries"] if isinstance(raw, dict) else raw
        if [p["data"] for p in parameters] != entries:
            raise ValueError("Frozen KDP payload differs from its exact SSOT records")
        for binding in snapshot.get("parameter_bindings", []):
            value = snapshot["model"]
            for part in binding["model_path"].split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
            if binding.get("value_source") != "model" or value != binding.get("resolved_value"):
                raise ValueError("SSOT model parameter binding disagrees with authoritative model")
        comparison = snapshot.get("comparison_design_ref")
        if comparison:
            design = by_ref.get((comparison.get("id"), comparison.get("revision")))
            if design is None or design["kind"] != "design":
                raise ValueError("Missing exact numerical comparison design revision")
            reference = copy.deepcopy(snapshot["model"])
            mechanics = design["data"]["physics"]
            variable_fields = {"cube_side_m", "frame_mass_kg", "frame_inertia_kg_m2", "wheel_mass_kg",
                               "wheel_radius_m", "wheel_thickness_m", "wheel_axial_inertia_kg_m2",
                               "wheel_transverse_inertia_kg_m2", "motor_torque_limit_nm"}
            for key, value in mechanics.items():
                if key not in variable_fields and value != reference["physics"].get(key):
                    raise ValueError("Comparison design changes frozen physical field: " + key)
            reference["physics"].update(copy.deepcopy(mechanics))
            reference["actuation"].update(copy.deepcopy(design["data"]["actuation"]))
            snapshot["reference_model"] = reference
        snapshot["source_snapshot_ref"] = {"id": selected["id"], "revision": selected["revision"]}
        design_source = snapshot.get("controller_design_snapshot_ref")
        if design_source is not None:
            source = by_ref.get((design_source.get("id"), design_source.get("revision")))
            if source is None or source["kind"] != "simulation_snapshot":
                raise ValueError("Missing exact controller design-plant snapshot")
            # This is a projection of an exact canonical source, not a second
            # authoritative plant. A tested controller can be retained after a
            # hardware change; subsequent Q edits keep its declared design plant.
            snapshot["controller_design_model"] = copy.deepcopy(source["data"]["model"])
        inherited_model = context_refs.get("model")
        snapshot["test_case_refs"] = {r["data"]["stage"]: {"id": r["id"], "revision": r["revision"]}
                                      for r in all_records if r["kind"] == "test_case"
                                      and r["data"].get("snapshot_ref") == inherited_model}
        snapshot["run_policy"] = {"fixed_timestep": True, "half_step_adjudication": False,
                                  "control_changes_require_new_campaign": True,
                                  "simultaneous_changes_require_2x2": True,
                                  "physical_verification": False}
        # The historical snapshot remains immutable; new runs use an explicitly
        # labelled child. No historical half-step outcome is claimed as a new run.
        snapshot["history_only"] = False
        return snapshot

    def context(self):
        # The immutable One-Piece store also contains records from offline
        # acceptance runs. Exclude those exact run families before applying
        # recency limits, or they can crowd current engineering evidence out
        # of the PI context. Canonical history remains untouched.
        exclusions = json.loads(_CONTEXT_EXCLUSIONS.read_text(encoding="utf-8"))
        if exclusions.get("schema_version") != "1.0" or exclusions.get("project_id") != self.project_id:
            raise ValueError("Invalid One-Piece agent-context exclusion manifest")
        excluded_runs = tuple(exclusions.get("excluded_run_ids", []))
        if (not excluded_runs
                or any(not isinstance(run_id, str) or not run_id.startswith("cube-") for run_id in excluded_runs)
                or len(set(excluded_runs)) != len(excluded_runs)):
            raise ValueError("Invalid One-Piece agent-context excluded run IDs")
        records = self.store.records(self.project_id)
        context = self.store.context(self.project_id, max_designs=len(records), max_evidence=len(records),
            kinds=["design", "design_candidate", "design_proposal", "simulation_run", "design_policy", "iteration", "analysis_result"],
            snapshot_ref={"id": self.snapshot_id, "revision": self.snapshot_revision})

        def is_excluded(record):
            identifier = record.get("id", "")
            return any(identifier == run_id or identifier.startswith(run_id + ".") for run_id in excluded_runs)

        all_visible = [record for record in context["records"] if not is_excluded(record)]
        design_kinds = {"design", "design_candidate", "candidate"}
        proposal_kinds = {"design_proposal"}
        evidence_kinds = {"evidence", "evaluation", "artifact", "simulation_run", "trial", "verification", "analysis_result"}
        source_snapshot = next((r for r in all_visible if r["kind"] == "simulation_snapshot"
                                and r["id"] == self.snapshot_id and r["revision"] == self.snapshot_revision), None)
        if source_snapshot is None:
            raise ValueError("Agent context does not contain the selected One-Piece snapshot")
        language_ref = source_snapshot["data"].get("language_profile_ref")
        if language_ref:
            language_profile = next((r for r in records if r["id"] == language_ref.get("id")
                                     and r["revision"] == language_ref.get("revision")), None)
            if language_profile is not None and not any(
                    (r["id"], r["revision"]) == (language_profile["id"], language_profile["revision"])
                    for r in all_visible):
                all_visible.append(language_profile)
        pinned = source_snapshot["data"].get("comparison_design_ref")
        pinned_key = (pinned.get("id"), pinned.get("revision")) if pinned else None
        designs = [r for r in all_visible if r["kind"] in design_kinds
                   and (r["id"], r["revision"]) != pinned_key]
        evidence = [r for r in all_visible if r["kind"] in evidence_kinds]
        proposals = [r for r in all_visible if r["kind"] in proposal_kinds]
        keep_designs = {(r["id"], r["revision"]) for r in designs[-5:]}
        keep_evidence = {(r["id"], r["revision"]) for r in evidence[-8:]}
        keep_proposals = {(r["id"], r["revision"]) for r in proposals[-5:]}
        # The exact comparison design and the campaign summary are required
        # context, independent of the bounded design/evidence windows.
        selected = [r for r in all_visible if (
            r["kind"] not in (design_kinds | evidence_kinds | proposal_kinds)
            or (r["id"], r["revision"]) == pinned_key
            or (r["kind"] in design_kinds and (r["id"], r["revision"]) in keep_designs)
            or (r["kind"] in proposal_kinds and (r["id"], r["revision"]) in keep_proposals)
            or (r["kind"] in evidence_kinds and (r["id"], r["revision"]) in keep_evidence)
        )]
        selected_keys = {(r["id"], r["revision"]) for r in selected}

        def data_refs(value, path="data"):
            if isinstance(value, dict):
                if set(value) == {"id", "revision"} and all(isinstance(value[k], str) for k in value):
                    yield path, value
                else:
                    for key, child in value.items():
                        yield from data_refs(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    yield from data_refs(child, f"{path}.{index}")

        omitted_refs = []
        for record in selected:
            for edge in record.get("links", []):
                target = edge["target"]
                if (target["id"], target["revision"]) not in selected_keys:
                    reason = ("agent_context_acceptance_exclusion" if is_excluded(target)
                              else "context_filter_or_limit")
                    omitted_refs.append({"source": {"id": record["id"], "revision": record["revision"]},
                                         "type": edge["type"], "target": target,
                                         "reason": reason})
            for path, target in data_refs(record.get("data", {})):
                if (target["id"], target["revision"]) not in selected_keys:
                    reason = ("agent_context_acceptance_exclusion" if is_excluded(target)
                              else "context_filter_or_limit")
                    omitted_refs.append({"source": {"id": record["id"], "revision": record["revision"]},
                                         "type": "data_reference", "path": path,
                                         "target": target, "reason": reason})
        context["records"] = selected
        context["counts"].update(
            returned=len(selected),
            designs=len(keep_designs) + (1 if pinned_key and pinned_key in selected_keys else 0),
            bounded_designs=len(keep_designs),
            pinned_designs=1 if pinned_key and pinned_key in selected_keys else 0,
            evidence=len(keep_evidence),
            proposals=len(keep_proposals),
        )
        context["limits"] = {"max_designs": 5, "max_evidence": 8, "max_proposals": 5}
        context["omitted_record_count"] = max(0, context["counts"]["project_records"] - len(selected))
        context["omitted_references"] = omitted_refs
        context["excluded_acceptance_runs"] = list(excluded_runs)
        return context

    def outbox(self, run_dir):
        return MechanicalOutbox(self, run_dir)


class MechanicalOutbox:
    def __init__(self, bridge, run_dir):
        self.bridge, self.root = bridge, Path(run_dir).resolve()
        self.path = self.root / "onepiece-outbox.json"
        self.entries = json.loads(self.path.read_text()) if self.path.exists() else []

    def enqueue(self, *, id, kind, data, links=None, artifacts=None, revision="1", actor_id="mechanical-design-loop"):
        from onepiece import make_record
        record = make_record(project_id=self.bridge.project_id, id=id, kind=kind,
            revision=revision, product_node="cube.system", data=data, links=links or [],
            artifacts=artifacts or [], actor={"type": "agent", "id": actor_id})
        # Persist exact bytes before the first delivery; retries preserve timestamps
        # and cannot accidentally create a conflicting record revision.
        existing = next((e for e in self.entries if e["record"]["id"] == id
                         and e["record"]["revision"] == str(revision)), None)
        if existing:
            if any(existing["record"][key] != record[key] for key in
                   ("kind", "product_node", "actor", "data", "links", "artifacts")):
                raise ValueError("Outbox ID/revision is immutable")
            return existing["record"]
        self.entries.append({"record": record, "state": "pending", "attempts": 0, "error": None})
        atomic_json(self.path, self.entries)
        return record

    def artifact(self, path):
        path = Path(path).resolve()
        relative = path.relative_to(self.root).as_posix()
        content = path.read_bytes()
        return {"path": relative, "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}

    def flush(self):
        pending = [e for e in self.entries if e["state"] != "acknowledged"]
        if pending:
            try:
                ack = self.bridge.store.import_records([e["record"] for e in pending], artifacts_root=self.root)
                for entry in pending:
                    entry.update(state="acknowledged", attempts=entry["attempts"] + 1, error=None, ack=ack)
            except Exception as error:
                for entry in pending:
                    entry.update(state="pending", attempts=entry["attempts"] + 1,
                                 error=f"{type(error).__name__}: {error}")
            atomic_json(self.path, self.entries)
        return {"pending": sum(e["state"] != "acknowledged" for e in self.entries),
                "acknowledged": sum(e["state"] == "acknowledged" for e in self.entries)}
