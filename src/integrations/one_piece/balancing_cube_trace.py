"""Append trace corrections without rewriting historical record revisions."""
from __future__ import annotations

import copy

TRACE_REVISION = "trace-20261010-2"
ACTIVE_SNAPSHOT_REVISION = "fixed-dt-mvp-2"


def trace_corrections(records):
    from onepiece import make_record, ref
    corrections = []
    by_id = {r["id"]: r for r in records if r["kind"] != "simulation_snapshot"}
    fixed = next((r for r in records if r["kind"] == "simulation_snapshot" and r["revision"] == "fixed-dt-mvp-1"), None)
    if fixed is None:
        return []
    project = fixed["project_id"]
    def revised(original, *, data=None, links=None, revision=TRACE_REVISION):
        record = make_record(project_id=project, id=original["id"], kind=original["kind"], revision=revision,
            product_node=original["product_node"], created_at="2026-10-10T00:00:00+00:00",
            actor={"type": "automation", "id": "balancing-cube-trace-correction"},
            data={**copy.deepcopy(original["data"] if data is None else data), "supersedes": ref(original)},
            links=copy.deepcopy(original["links"] if links is None else links), artifacts=original["artifacts"])
        corrections.append(record)
        return record
    requirements = []
    for original in records:
        if original["kind"] != "requirement":
            continue
        data = copy.deepcopy(original["data"])
        data["status_semantics"] = "source_requirement_statement_status; not verification or acceptance outcome"
        data["physical_verified"] = None
        if "hardware_acceptance" in data:
            data["hardware_verification_required"] = data.pop("hardware_acceptance")
            data["hardware_verification_note"] = "An item to demonstrate with hardware; not an acceptance/pass flag. Original field retained in superseded source revision."
        links = copy.deepcopy(original["links"])
        for edge in links:
            if edge["target"]["id"] in by_id and by_id[edge["target"]["id"]]["kind"] == "requirement":
                edge["target"]["revision"] = TRACE_REVISION
            if original["id"] == "M-VERTEX" and edge["type"] == "allocate":
                edge["target"] = ref(by_id["cube.system"])
        requirement = revised(original, data=data, links=links)
        if original["id"] == "M-VERTEX":
            requirement["product_node"] = "cube.system"
        requirements.append(requirement)
    for original in records:
        if original["kind"] == "test_case":
            revised(original, data={**original["data"], "verification_domain": "numerical_development",
                "required_duration_s": fixed["data"]["contract"].get("screening", {}).get("required_duration_s", 6.0),
                "physical_verified": False,
                "scope_note": "Numerical development case; does not demonstrate hardware hold duration."})
        elif original["kind"] == "evaluation":
            links = [copy.deepcopy(e) for e in original["links"] if e["type"] != "verify" or e["target"]["id"] != "M-VERTEX"]
            for edge in links:
                if edge["type"] == "verify" and edge["target"]["id"].startswith("cube.case."):
                    edge["target"]["revision"] = TRACE_REVISION
            revised(original, links=links)
    data = copy.deepcopy(fixed["data"])
    data["context_refs"]["requirements"] = [ref(r) for r in requirements]
    data["context_refs"]["campaign_summary"] = ref(by_id["cube.campaign.summary"])
    data["mission"] = {**data["mission"], "source_revision": data["mission"]["revision"],
                       "revision": TRACE_REVISION,
                       "requirements": [r["data"] for r in requirements if r["data"].get("original_record")]}
    data["trace_correction_note"] = "Allocation, statement-status semantics and numerical test-case trace corrected; physics, controller, criteria and numerical outcomes unchanged. No human baseline established."
    active = revised(fixed, data=data, revision=ACTIVE_SNAPSHOT_REVISION,
                     links=[{"type": "derive", "target": ref(fixed)}])
    corrections.append(make_record(project_id=project, id="cube.system-model.active", kind="system_model",
        revision=TRACE_REVISION, created_at="2026-10-10T00:00:00+00:00",
        actor={"type": "automation", "id": "balancing-cube-trace-correction"},
        data={"simulation_snapshot_ref": ref(active), "scope": "current context projection; not human-adopted baseline"}))
    return corrections
