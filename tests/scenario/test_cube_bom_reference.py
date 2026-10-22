"""Guard the distinction between component references, priors and verification."""
import copy
import json
from pathlib import Path

import pytest

from scenario.balancing_cube.bom_reference import PART_NAMES, build_reference, hold_diagnostic


def inputs():
    snapshot = json.loads((Path(__file__).parents[1] / "fixtures/balancing_cube_snapshot.json").read_text())
    snapshot["context_refs"] = {"model": {"id": "cube.simulation.snapshot", "revision": "fixture"}}
    snapshot["controller_design_snapshot_ref"] = {"id": "cube.simulation.snapshot", "revision": "fixture"}
    snapshot["controller_source_ref"] = {"id": "controller.fixture", "revision": "1"}
    snapshot["model"]["physics"]["wheel_mount_side"] = "near_corner_000"
    bom = {"parts": [{"part_id": p, "quantity_reference": 3 if p == "E-001" else 1,
                       "reference_mass_g": 49 if p == "E-004" else None, "measured_mass_g": None}
                      for p in PART_NAMES], "source_sha256": "a" * 64,
           "selection_rules": [{"members": ["P-005", "P-006"], "selection": "P-005"}]}
    return snapshot, bom


def test_component_reference_preserves_k_and_does_not_add_battery_twice():
    source, bom = inputs()
    before = copy.deepcopy(source)
    result = build_reference(source, source, bom)
    assert result["controller"] == source["controller"]
    assert result["families"] == {}  # No motor-family optimization in this assessment.
    assert result["model"]["physics"]["frame_mass_kg"] == source["model"]["physics"]["frame_mass_kg"]
    assert result["model"]["component_reference"]["battery"]["reference_mass_kg"] == .049
    assert result["model"]["component_reference"]["firmware"]["executed"] is False
    assert source == before
    result["controller"]["K"][0][0] = 123
    assert source == before  # Frozen ancestry is copied, not mutated.


@pytest.mark.parametrize("change", ["duplicate", "measured", "battery", "quantity"])
def test_new_component_evidence_requires_an_explicit_recipe_review(change):
    source, bom = inputs()
    if change == "duplicate":
        bom["parts"][-1] = copy.deepcopy(bom["parts"][0])
    elif change == "measured":
        bom["parts"][0]["measured_mass_g"] = 21
    elif change == "battery":
        next(p for p in bom["parts"] if p["part_id"] == "E-004")["reference_mass_g"] = 60
    else:
        next(p for p in bom["parts"] if p["part_id"] == "E-001")["quantity_reference"] = 4
    with pytest.raises(ValueError):
        build_reference(source, source, bom)


def test_hold_diagnostic_uses_whole_interval_and_rejects_early_termination():
    result = {"rows": [{"tilt_total_deg": 4, "omega_z_deg_s": 6}] * 90 +
                       [{"tilt_total_deg": .01, "omega_z_deg_s": .1}] * 10,
              "summary": {"status": "completed", "simulated_duration_s": 30, "peak_tilt_deg": 4,
                          "peak_pivot_displacement_mm": .1, "contact_fraction": 1}}
    checked = hold_diagnostic(result)
    assert checked["whole_interval_tilt_rms_deg"] > 2
    assert not checked["checks"]["whole_interval_tilt_rms_le_2deg"]
    assert checked["yaw_5deg_s_is_target_only"]
    assert not checked["physical_verified"]
    result["rows"] = [{"tilt_total_deg": .01, "omega_z_deg_s": .1}] * 10
    result["summary"].update(status="lost_balance", simulated_duration_s=2)
    checked = hold_diagnostic(result)
    assert not checked["checks"]["duration_30s"]
    assert not checked["passed_numerical_analogues"]
