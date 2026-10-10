"""Import failures must fail closed before an immutable Store commit is created."""
import copy
import csv
import json
from pathlib import Path

import pytest

pytest.importorskip("onepiece")

from integrations.one_piece.balancing_cube_import import (
    ImportValidationError, _legacy_digest, build_records,
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def campaign(tmp_path):
    """Two original stages, no fabricated physical measurement or baseline."""
    source = tmp_path / "campaign"
    report = source / "report"
    plan = {stage: {"domains": [{"id": "domain"}], "conditions": [{"id": "condition"}], "seeds": [811]}
            for stage in ("exploration", "validation")}
    snapshot = {
        "model": {"physics": {"cube_side_m": .18}}, "plan": plan,
        "mission": {"revision": "mission1", "requirements": [{"id": "M-VERTEX", "name": "mission", "value": True, "unit": "1", "status": "confirmed"}]},
        "kdps": {"revision": "kdp1", "entries": [{"id": "D-SIDE", "name": "side", "value": .18, "unit": "m", "role": "design", "origin": "assumed", "standard_uncertainty": None, "model_path": "physics.cube_side_m", "requirements": ["M-VERTEX"]}]},
        "families": {}, "contract": {"revision": "contract1"},
    }
    controller = {"K": [[1]], "yaw_rate_gain_nm_s": .03}
    aggregate = {"state": "completed", "score": 1., "pass_fraction": 1., "all_pass": True,
                 "numeric_verified": True, "trials": 1, "passed_trials": 1,
                 "coverage_complete": True, "failures": {}, "metrics": {},
                 "domains": [], "gate_sources": {"native_cpu_reference": 1}}
    candidate = {"id": "candidate1", "family": "motor", "input_digest": "input1", "status": "confirmed_numerical_pass",
                 "original_status": "confirmed_numerical_pass", "validation_origin": "original_campaign",
                 "exploration": copy.deepcopy(aggregate), "validation": copy.deepcopy(aggregate),
                 "parameters": {}, "physics": {"cube_side_m": .18}, "actuation": {}, "assumptions": {"physical_fidelity": None}}
    analysis = {"candidates": [candidate], "overview": {"candidate_count": 1,
                "counts": {"confirmed_pass": 1}, "launch": {"finished_at": "2026-10-09T13:47:52+00:00"}},
                "provenance": {"campaign_directory": "/original/raw", "campaign_revision": "campaign1"},
                "prior46": {"count": 1, "ids": ["candidate1"], "status_counts": {"confirmed_numerical_pass": 1}, "original_status_counts": {"confirmed_numerical_pass": 1}},
                "best": {"original_confirmed": [{"id": "candidate1"}]},
                **{k: {} for k in ("timeline", "benchmark", "telemetry", "failure_analysis", "agreement", "null_unmeasured")},
                "criteria": [], "limitations": []}
    campaign_meta = {"revision": "campaign1", "snapshot_digest": _legacy_digest(snapshot),
                     "contract_digest": _legacy_digest(snapshot["contract"]), "controller_digest": _legacy_digest(controller)}
    supplemental = {"provenance": {"source_campaign_revision": "campaign1", "contract_digest": campaign_meta["contract_digest"],
                                    "controller_digest": campaign_meta["controller_digest"]}, "results": []}
    for path, value in [(report / "analysis.json", analysis), (report / "sources/snapshot.json", snapshot),
                        (report / "sources/controller.json", controller), (report / "sources/campaign.json", campaign_meta),
                        (report / "supplemental-confirmations.json", supplemental), (report / "replay.json", {"cases": []}),
                        (source / "gnc-report/gnc-data.json", {})]:
        write_json(path, value)
    (source / "raw").mkdir()
    (source / "raw/jobs.sqlite").write_bytes(b"original database artifact")
    rows = [{"candidate_id": "candidate1", "stage": stage, "evidence_origin": "original_campaign", "domain_id": "domain",
             "condition_id": "condition", "seed": 811, "status": "completed", "passed": "True", "failure_criteria": ""}
            for stage in ("exploration", "validation")]
    with (report / "trials.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    return source


def mutate_json(source, relative, fn):
    path = source / relative
    data = json.loads(path.read_text())
    fn(data)
    write_json(path, data)


def test_import_preserves_units_nulls_edges_and_is_idempotent(campaign, tmp_path):
    from onepiece import Store
    records, summary = build_records(campaign)
    param = next(r for r in records if r["id"] == "D-SIDE")
    assert param["data"]["unit"] == "m"
    assert param["data"]["standard_uncertainty"] is None
    assert summary["hardware_physical_validity"] is None
    assert not any(r["kind"] == "baseline" for r in records)
    original_sha = (campaign / "raw/jobs.sqlite").read_bytes()
    store = Store(tmp_path / "store")
    result = store.import_records(records, artifacts_root=campaign)
    again, _ = build_records(campaign)
    assert records == again
    assert store.import_records(again, artifacts_root=campaign)["imported"] == 0
    assert result["imported"] == len(records)
    assert store.check()["ok"]
    assert (campaign / "raw/jobs.sqlite").read_bytes() == original_sha
    context = store.context("balancing-cube", max_designs=0, max_evidence=0)
    assert any(r["id"] == "cube.simulation.snapshot" for r in context["records"])


def test_missing_condition_is_rejected(campaign):
    path = campaign / "report/trials.csv"
    rows = path.read_text(encoding="utf-8-sig").splitlines()
    path.write_text("\n".join(rows[:2]) + "\n", encoding="utf-8-sig")
    with pytest.raises(ImportValidationError, match="coverage groups"):
        build_records(campaign)


def test_duplicate_condition_is_rejected(campaign):
    path = campaign / "report/trials.csv"
    rows = path.read_text(encoding="utf-8-sig").splitlines()
    path.write_text("\n".join(rows + [rows[1]]) + "\n", encoding="utf-8-sig")
    with pytest.raises(ImportValidationError, match="Duplicate trial"):
        build_records(campaign)


def test_csv_outcome_cannot_disagree_with_summary(campaign):
    path = campaign / "report/trials.csv"
    path.write_text(path.read_text(encoding="utf-8-sig").replace("completed,True,", "lost_balance,False,status|peak_tilt_deg"), encoding="utf-8-sig")
    with pytest.raises(ImportValidationError, match="CSV/summary outcomes"):
        build_records(campaign)


@pytest.mark.parametrize("field,value", [("all_pass", False), ("all_pass", 1),
                                        ("pass_fraction", 0.0), ("pass_fraction", True)])
def test_derived_pass_fields_must_match_csv(campaign, field, value):
    mutate_json(campaign, "report/analysis.json",
                lambda a: a["candidates"][0]["exploration"].update({field: value}))
    with pytest.raises(ImportValidationError, match="CSV/summary outcomes"):
        build_records(campaign)


def test_failing_trials_cannot_claim_all_pass_or_seed_a_comparison(campaign):
    path = campaign / "report/trials.csv"
    path.write_text(path.read_text(encoding="utf-8-sig").replace("completed,True,", "lost_balance,False,status"), encoding="utf-8-sig")
    def corrupt(analysis):
        for stage in ("exploration", "validation"):
            analysis["candidates"][0][stage].update(passed_trials=0, failures={"status": 1})
            # Keep the contradictory all_pass=True/pass_fraction=1.0.
    mutate_json(campaign, "report/analysis.json", corrupt)
    with pytest.raises(ImportValidationError, match="CSV/summary outcomes"):
        build_records(campaign)


def test_frozen_input_tamper_rejected(campaign):
    mutate_json(campaign, "report/sources/controller.json", lambda c: c.update(yaw_rate_gain_nm_s=.5))
    with pytest.raises(ImportValidationError, match="digest mismatch"):
        build_records(campaign)


def test_supplemental_wrong_contract_rejected(campaign):
    mutate_json(campaign, "report/supplemental-confirmations.json", lambda s: s["provenance"].update(contract_digest="wrong"))
    with pytest.raises(ImportValidationError, match="Supplemental contract_digest"):
        build_records(campaign)


def test_prior_ids_and_outcomes_checked(campaign):
    mutate_json(campaign, "report/analysis.json", lambda a: a["prior46"].update(status_counts={"confirmed_numerical_fail": 1}))
    with pytest.raises(ImportValidationError, match="Prior-candidate outcomes"):
        build_records(campaign)


def test_corrected_trace_allocates_mission_and_verifies_numerical_cases(campaign, tmp_path):
    from onepiece import Store
    mutate_json(campaign, "report/sources/snapshot.json", lambda s: s["mission"]["requirements"][0].update(hardware_acceptance=True))
    frozen = json.loads((campaign / "report/sources/snapshot.json").read_text())
    mutate_json(campaign, "report/sources/campaign.json", lambda c: c.update(snapshot_digest=_legacy_digest(frozen)))
    records, summary = build_records(campaign)
    store = Store(tmp_path / "trace")
    store.import_records(records, artifacts_root=campaign)
    context = store.context("balancing-cube", snapshot_ref={"id": "cube.simulation.snapshot", "revision": "fixed-dt-mvp-2"})
    mission = next(r for r in context["records"] if r["id"] == "M-VERTEX")
    assert mission["product_node"] == "cube.system"
    assert next(e for e in mission["links"] if e["type"] == "allocate")["target"]["id"] == "cube.system"
    assert mission["data"]["hardware_verification_required"] is True
    assert "hardware_acceptance" not in mission["data"]
    assert "not verification" in mission["data"]["status_semantics"]
    current = [r for r in records if r["kind"] == "evaluation" and r["revision"] == "trace-20261010-2"]
    assert current and all(e["target"]["id"].startswith("cube.case.") for r in current for e in r["links"] if e["type"] == "verify")
    assert summary["trace_corrections"] > 0
