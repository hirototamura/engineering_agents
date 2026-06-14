"""Health and summary helpers for ssos_eclss_loop."""

from __future__ import annotations

from environment.protocol import HealthStatus
from environment.ssos.eclss_types import EclssTelemetrySnapshot
from scenario.ssos_eclss_loop.health import compute_eclss_storage_health
from scenario.ssos_eclss_loop.scenario_run import _omit_nulls, _telemetry_summary_fields


def test_health_unknown_when_telemetry_missing():
    snap = EclssTelemetrySnapshot()
    health = compute_eclss_storage_health(0, snap, {})
    assert health["co2_status"] == HealthStatus.UNKNOWN.value
    assert health["o2_status"] == HealthStatus.UNKNOWN.value
    assert health["water_status"] == HealthStatus.UNKNOWN.value
    assert health["overall"] == HealthStatus.UNKNOWN.value


def test_telemetry_snapshot_to_dict_omits_nulls():
    payload = EclssTelemetrySnapshot(co2_storage_kg=10.0).to_dict()
    assert payload == {"co2_storage_kg": 10.0}
    assert "o2_storage_kg" not in payload


def test_summary_helpers_omit_null_metrics():
    snap = EclssTelemetrySnapshot(co2_storage_kg=12.5, o2_storage_kg=480.0, raw_topics={"/co2_storage": 12.5})
    fields = _telemetry_summary_fields(snap, peak_co2=12.5, min_o2=480.0)
    assert fields["final_co2_storage_kg"] == 12.5
    assert "final_product_water_reserve_l" not in fields
    assert fields["telemetry_topics_read"] == ["/co2_storage"]

    omitted = _omit_nulls({"ars_invoked_step": None, "message_count": 0})
    assert omitted == {"message_count": 0}
