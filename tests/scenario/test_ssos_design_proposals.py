"""Tests for ssos_eclss_loop design_proposals.json apply/build helpers."""

import json

import pytest

from scenario.ssos_eclss_loop.design_proposals import (
    DESIGN_DOMAIN,
    apply_design_proposals,
    build_design_proposals_from_run,
    validate_design_proposals,
    write_design_proposals,
)


def test_apply_action_profile_and_service_config():
    config = {
        "agents": {"policy": {"ars_goal": {"initial_co2_mass": 1000.0}}},
        "thresholds": {"o2_storage_low_kg": 400.0},
    }
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "proposed_by": "op_1",
        "decision_source": "rule",
        "changes": [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ogs",
                    "fields": {"input_water_mass": 12.0, "iodine_concentration": 1.5},
                },
            },
            {
                "change_kind": "service_config",
                "payload": {"service": "request_co2", "amount": 30.0, "before_ogs": False},
            },
            {
                "change_kind": "set_parameter",
                "payload": {"target": "thresholds.co2_storage_high_kg", "value": 1600.0},
            },
        ],
    }
    merged = apply_design_proposals(config, proposals)
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == 12.0
    assert merged["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"] == 12.0
    assert merged["agents"]["policy"]["request_co2_amount"] == 30.0
    assert merged["agents"]["actor"]["policy"]["request_co2_amount"] == 30.0
    assert merged["agents"]["policy"]["request_co2_before_ogs"] is False
    assert merged["thresholds"]["co2_storage_high_kg"] == 1600.0
    assert merged["agents"]["policy"]["ars_goal"]["initial_co2_mass"] == 1000.0


def test_apply_graph_rewire():
    config = {"agents": {"policy": {}}}
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "graph_rewire",
                "payload": {
                    "component": "rclpy_gateway",
                    "public": "/grey_water",
                    "backend": "/grey_water/wrs",
                },
            }
        ],
    }
    merged = apply_design_proposals(config, proposals)
    assert len(merged["ssos_graph"]["rewires"]) == 1
    assert merged["ssos_graph"]["rewires"][0]["public"] == "/grey_water"


def test_apply_graph_rewire_rejects_empty_payload():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [{"change_kind": "graph_rewire", "payload": {}}],
    }
    with pytest.raises(ValueError, match="non-empty"):
        apply_design_proposals({"agents": {"policy": {}}}, proposals)


def test_build_design_proposals_from_policy():
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "request_co2_before_ogs": True,
        "ars_goal": {"initial_co2_mass": 1.8},
        "ogs_goal": {"input_water_mass": 0.01},
    }
    # Without summary stress, still emit a non-no-op ARS bump (L8).
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
    )
    assert doc["design_domain"] == DESIGN_DOMAIN
    assert doc["proposed_by"] == "eclss_operator_1"
    assert doc["changes"]
    assert any(c.get("change_kind") == "action_profile" for c in doc["changes"])
    ars = next(c for c in doc["changes"] if c["change_kind"] == "action_profile")
    assert ars["payload"]["fields"]["initial_co2_mass"] == pytest.approx(1.98)
    assert validate_design_proposals(doc) == []


def test_build_design_proposals_from_policy_includes_why_what_how():
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "request_co2_before_ogs": True,
        "ars_goal": {"initial_co2_mass": 1.8},
        "ogs_goal": {"input_water_mass": 0.01},
    }
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
    )
    change = next(c for c in doc["changes"] if c["change_kind"] == "action_profile")
    assert change.get("why")
    assert change.get("what")
    assert change.get("how")


def test_build_design_proposals_from_stressed_summary_includes_why_what_how():
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "request_co2_before_ogs": True,
        "ars_goal": {"initial_co2_mass": 1.8},
        "ogs_goal": {"input_water_mass": 0.01},
    }
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
        summary={
            "final_health": {"co2_status": "warning", "o2_status": "warning"},
            "final_co2_storage_kg": 1.7,
            "min_o2_storage_kg": 0.4,
        },
    )
    kinds = {c["change_kind"] for c in doc["changes"]}
    assert "action_profile" in kinds
    assert "set_parameter" in kinds
    assert "service_config" in kinds
    for change in doc["changes"]:
        assert change.get("why")
        assert change.get("what")
        assert change.get("how")


def test_build_design_proposals_fallback_without_goals_uses_threshold():
    """L8/A: missing ars/ogs goals still yields a non-no-op threshold bump."""
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy={"co2_storage_high_kg": 1.5, "o2_storage_low_kg": 0.45},
    )
    assert doc["changes"]
    assert all(c["change_kind"] == "set_parameter" for c in doc["changes"])
    values = {c["payload"]["target"]: c["payload"]["value"] for c in doc["changes"]}
    assert values["agents.actor.policy.co2_storage_high_kg"] == pytest.approx(1.35)
    assert values["thresholds.co2_storage_high_kg"] == pytest.approx(1.35)


def test_build_design_proposals_defaults_before_ogs_false_when_absent():
    """Absent request_co2_before_ogs must not embed before_ogs: true in proposals."""
    policy = {
        "co2_storage_high_kg": 1.5,
        "o2_storage_low_kg": 0.45,
        "request_co2_amount": 0.025,
        "ogs_goal": {"input_water_mass": 0.01},
    }
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy=policy,
        summary={
            "final_health": {"o2_status": "warning"},
            "min_o2_storage_kg": 0.4,
        },
    )
    service = next(c for c in doc["changes"] if c["change_kind"] == "service_config")
    assert service["payload"]["before_ogs"] is False


def test_build_design_proposals_ars_zero_mass_falls_through_to_ogs():
    """ARS fallback with non-positive bump must not block OGS / later fallbacks."""
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy={
            "co2_storage_high_kg": 1.5,
            "o2_storage_low_kg": 0.45,
            "ars_goal": {"initial_co2_mass": 0.0},
            "ogs_goal": {"input_water_mass": 0.01},
        },
    )
    assert doc["changes"]
    ogs = next(c for c in doc["changes"] if c["change_kind"] == "action_profile")
    assert ogs["payload"]["subsystem"] == "ogs"
    assert ogs["payload"]["fields"]["input_water_mass"] == pytest.approx(0.011)


def test_build_design_proposals_ars_tiny_mass_falls_through():
    """Rounded-to-zero ARS bump must fall through instead of writing a no-op profile."""
    doc = build_design_proposals_from_run(
        proposed_by="eclss_operator_1",
        decision_source="rule",
        policy={
            "co2_storage_high_kg": 1.5,
            "o2_storage_low_kg": 0.45,
            "ars_goal": {"initial_co2_mass": 1e-7},
            "ogs_goal": {"input_water_mass": 0.01},
        },
    )
    assert doc["changes"]
    profiles = [c for c in doc["changes"] if c["change_kind"] == "action_profile"]
    assert profiles
    assert profiles[0]["payload"]["subsystem"] == "ogs"
    assert all(
        c["payload"]["fields"].get("initial_co2_mass", 1.0) > 0.0
        for c in profiles
        if c["payload"]["subsystem"] == "ars"
    )


def test_build_design_proposals_fallback_empty_policy_uses_default_threshold():
    """Even with empty policy, labeled builder uses default CO₂ high band."""
    doc = build_design_proposals_from_run(
        proposed_by="rep",
        decision_source="rule",
        policy={},
    )
    assert doc["changes"]
    assert any(
        c["payload"]["target"] == "thresholds.co2_storage_high_kg" for c in doc["changes"]
    )


def test_write_rejects_scrubber_change_kind(tmp_path):
    bad = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [{"change_kind": "add_edge", "payload": {}}],
    }
    with pytest.raises(ValueError, match="change_kind"):
        write_design_proposals(tmp_path / "bad.json", bad)


def test_round_trip_via_json_file(tmp_path):
    proposals = build_design_proposals_from_run(
        proposed_by="rep",
        decision_source="rule",
        policy={"ogs_goal": {"input_water_mass": 9.0}},
    )
    path = tmp_path / "design_proposals.json"
    write_design_proposals(path, proposals)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    merged = apply_design_proposals({"agents": {"policy": {}}}, loaded)
    assert merged["agents"]["policy"]["ogs_goal"]["input_water_mass"] == pytest.approx(9.9)
    assert merged["agents"]["actor"]["policy"]["ogs_goal"]["input_water_mass"] == pytest.approx(9.9)


def test_apply_action_profile_rejects_unknown_fields():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "action_profile",
                "payload": {
                    "subsystem": "ars",
                    "fields": {
                        "initial_co2_mass": 1800.0,
                        "duration_steps": 3,
                    },
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="unsupported keys"):
        apply_design_proposals({"agents": {"policy": {}}}, proposals)


def test_apply_set_parameter_rejects_arbitrary_target():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "set_parameter",
                "payload": {"target": "simulation.steps", "value": 999},
            }
        ],
    }
    with pytest.raises(ValueError, match="not allowed"):
        apply_design_proposals({"agents": {"policy": {}}}, proposals)


def test_apply_set_parameter_canonical_target_dual_writes_legacy_alias():
    proposals = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "set_parameter",
                "payload": {
                    "target": "agents.actor.policy.co2_storage_high_kg",
                    "value": 1.1,
                },
            }
        ],
    }
    merged = apply_design_proposals({"agents": {}}, proposals)
    assert merged["agents"]["actor"]["policy"]["co2_storage_high_kg"] == 1.1
    assert merged["agents"]["policy"]["co2_storage_high_kg"] == 1.1


def test_apply_without_legacy_policy_key_still_loads_actor_policy():
    from scenario.runner import load_agents_config, load_scenario_config

    config = load_scenario_config(
        "ssos_eclss_loop",
        {"agents": {"actor": {"mode": "labeled_rule_base"}}},
    )
    config.get("agents", {}).pop("policy", None)
    merged = apply_design_proposals(
        config,
        {
            "design_domain": DESIGN_DOMAIN,
            "changes": [
                {
                    "change_kind": "action_profile",
                    "payload": {
                        "subsystem": "ars",
                        "fields": {"initial_co2_mass": 2.5},
                    },
                }
            ],
        },
    )
    merged["agents"].pop("policy", None)
    agents = load_agents_config("ssos_eclss_loop", merged)
    assert agents is not None
    assert agents["actor"]["policy"]["ars_goal"]["initial_co2_mass"] == 2.5


# --------------------------------------------------------------------------- #
# supervisor approval gate (design doc §9)
# --------------------------------------------------------------------------- #
def _capacity_document(**extra) -> dict:
    document = {
        "design_domain": DESIGN_DOMAIN,
        "changes": [
            {
                "change_kind": "capacity_profile",
                "payload": {
                    "backend": "plant_sim",
                    "fields": {"plant_sim.ars.capacity_kg_day": 30.0},
                },
            }
        ],
    }
    document.update(extra)
    return document


def test_a_provisional_design_is_not_applied_without_approval():
    """The file plus --apply-proposals is the adoption path, so it is the gate."""
    config = {"plant_sim": {"ars": {"capacity_kg_day": 4.5}}}
    document = _capacity_document(
        final_status="provisional_final",
        requires_supervisor_approval=True,
        selection={"reason": "over budget by 3000 kg"},
    )
    with pytest.raises(ValueError) as excinfo:
        apply_design_proposals(config, document)
    message = str(excinfo.value)
    assert "provisional_final" in message
    assert "over budget by 3000 kg" in message
    assert "--approve-provisional" in message
    # and the config it was handed is untouched
    assert config["plant_sim"]["ars"]["capacity_kg_day"] == 4.5


def test_an_approved_design_applies_without_a_flag():
    merged = apply_design_proposals(
        {"plant_sim": {"ars": {"capacity_kg_day": 4.5}}},
        _capacity_document(final_status="approved_final", requires_supervisor_approval=False),
    )
    assert merged["plant_sim"]["ars"]["capacity_kg_day"] == 30.0


def test_a_human_can_still_adopt_a_provisional_design_on_purpose():
    merged = apply_design_proposals(
        {"plant_sim": {"ars": {"capacity_kg_day": 4.5}}},
        _capacity_document(final_status="provisional_final", requires_supervisor_approval=True),
        approve_provisional=True,
    )
    assert merged["plant_sim"]["ars"]["capacity_kg_day"] == 30.0


def test_a_single_flagged_change_blocks_the_whole_document():
    document = _capacity_document(final_status="approved_final")
    document["changes"][0]["requires_supervisor_approval"] = True
    with pytest.raises(ValueError, match="requires_supervisor_approval"):
        apply_design_proposals({}, document)


def test_a_document_without_a_status_still_applies():
    """Hand-written and scrubber-style documents carry no design status."""
    merged = apply_design_proposals(
        {"plant_sim": {"ars": {"capacity_kg_day": 4.5}}},
        _capacity_document(),
    )
    assert merged["plant_sim"]["ars"]["capacity_kg_day"] == 30.0


# --------------------------------------------------------------------------- #
# why one design beat another (spec §15, decision C)
# --------------------------------------------------------------------------- #
def _candidate(
    cid: str,
    *,
    warn: int,
    mass: float,
    crit: int = 0,
    eligible: bool = True,
    crew: int = 50,
    score: float = 70.0,
    max_score: float = 90.0,
) -> dict:
    return {
        "candidate_id": cid,
        "final_eligible": eligible,
        "outcome": {
            "crew_remaining": crew,
            "crew_initial": 50,
            "critical_step_count": crit,
            "warning_step_count": warn,
            "evaluation_compact": {"score": score, "max_score": max_score},
        },
        "constraint_evaluation": {
            "total_mass_kg": mass,
            "total_volume_m3": mass / 280.0,
            "total_cost_musd": mass / 6.7,
        },
    }


def test_the_scorecard_is_named_as_the_deciding_criterion():
    """With everyone alive on both sides, the sheet is what is left to say."""
    from scenario.ssos_eclss_loop.design_eval import rank_rationale

    rationale = rank_rationale(
        _candidate("candidate_001", warn=65, mass=4689.9, score=72.0),
        _candidate("candidate_002", warn=69, mass=4196.2, score=64.8),
    )

    assert rationale["decided_by"] == "evaluation_score_pct"
    assert rationale["winner_value"] == 80.0  # 72 of 90
    assert rationale["runner_up_value"] == 72.0  # 64.8 of 90
    # It is the last criterion, so nothing was skipped over.
    assert rationale["not_compared"] == []


def test_dwell_and_mass_are_no_longer_criteria_at_all():
    """They are marked inside the score; they are not compared beside it."""
    from scenario.ssos_eclss_loop.design_eval import RANK_CRITERIA, rank_rationale

    assert RANK_CRITERIA == ("final_eligible", "crew_remaining", "evaluation_score_pct")

    # Wildly different dwell and mass, identical score: nothing decides.
    rationale = rank_rationale(
        _candidate("candidate_002", warn=1, mass=1900.0, score=70.0),
        _candidate("candidate_001", warn=67, mass=5800.0, score=70.0),
    )
    assert rationale["decided_by"] is None


def test_eligibility_decides_before_anything_else():
    from scenario.ssos_eclss_loop.design_eval import rank_rationale

    rationale = rank_rationale(
        _candidate("candidate_001", warn=99, mass=9999.0),
        _candidate("candidate_002", warn=1, mass=100.0, eligible=False),
    )
    assert rationale["decided_by"] == "final_eligible"


def test_a_lone_candidate_has_nothing_to_be_decided_against():
    from scenario.ssos_eclss_loop.design_eval import rank_rationale

    rationale = rank_rationale(_candidate("candidate_001", warn=65, mass=4689.9), None)
    assert rationale["decided_by"] is None
    assert "only one candidate" in rationale["detail"]


# --------------------------------------------------------------------------- #
# handing a design to the next run
# --------------------------------------------------------------------------- #
def _whole_or_partial(**fields):
    return {
        "design_domain": "ssos_graph",
        "changes": [
            {
                "change_kind": "capacity_profile",
                "payload": {"backend": "plant_sim", "fields": dict(fields)},
                "why": "test",
                "what": "test",
                "how": "test",
            }
        ],
    }


ARS_KEY = "plant_sim.ars.capacity_kg_day"
OGS_KEY = "plant_sim.ogs.max_o2_kg_day"
WRS_KEY = "plant_sim.wrs.max_feed_l_per_operation"
FLYING = {ARS_KEY: 20.8, OGS_KEY: 42.0, WRS_KEY: 2.0}


def test_a_proposal_naming_one_subsystem_hands_on_the_whole_machine():
    """A capacity proposal is merged into the scenario file, not into the run.

    So a proposal that mentions only the water recycler used to return the CO2
    scrubber and the oxygen generator to their shipped sizes -- and a chain that
    had grown them enough to keep fifty occupants alive handed the next round a
    station sized for none of them.
    """
    from scenario.ssos_eclss_loop.design_proposals import complete_capacity_profile

    completed = complete_capacity_profile(_whole_or_partial(**{WRS_KEY: 2.5}), FLYING)
    fields = completed["changes"][0]["payload"]["fields"]
    assert fields == {ARS_KEY: 20.8, OGS_KEY: 42.0, WRS_KEY: 2.5}
    # What was proposed wins; only the silence is filled in, and it is recorded.
    assert completed["changes"][0]["carried_forward"] == sorted([ARS_KEY, OGS_KEY])


def test_completing_a_proposal_never_overrides_what_it_asked_for():
    from scenario.ssos_eclss_loop.design_proposals import complete_capacity_profile

    asked = {ARS_KEY: 30.0, OGS_KEY: 60.0, WRS_KEY: 5.0}
    completed = complete_capacity_profile(_whole_or_partial(**asked), FLYING)
    assert completed["changes"][0]["payload"]["fields"] == asked
    assert "carried_forward" not in completed["changes"][0]


def test_completing_leaves_other_kinds_of_change_alone():
    from scenario.ssos_eclss_loop.design_proposals import complete_capacity_profile

    document = {
        "design_domain": "ssos_graph",
        "changes": [
            {"change_kind": "action_profile", "payload": {"subsystem": "ars"}},
            {"change_kind": "capacity_profile", "payload": {"fields": {WRS_KEY: 2.5}}},
        ],
    }
    completed = complete_capacity_profile(document, FLYING)
    assert completed["changes"][0]["payload"] == {"subsystem": "ars"}
    assert set(completed["changes"][1]["payload"]["fields"]) == set(FLYING)


def test_a_completed_proposal_applies_to_the_machine_it_names():
    """End to end: the omitted subsystems survive the trip to the next run."""
    import yaml

    from scenario.runner import scenario_config_path
    from scenario.ssos_eclss_loop.design_proposals import (
        apply_design_proposals,
        complete_capacity_profile,
    )
    from scenario.ssos_eclss_loop.design_variables import read_capacity_fields

    shipped = yaml.safe_load(scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8"))
    water_only = _whole_or_partial(**{WRS_KEY: 2.5})

    # Without completion the two gas subsystems fall back to the shipped sizes.
    reverted = read_capacity_fields(apply_design_proposals(shipped, water_only))
    assert reverted[ARS_KEY] != 20.8

    kept = read_capacity_fields(
        apply_design_proposals(shipped, complete_capacity_profile(water_only, FLYING))
    )
    assert kept == {ARS_KEY: 20.8, OGS_KEY: 42.0, WRS_KEY: 2.5}
