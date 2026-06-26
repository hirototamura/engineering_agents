"""Unit tests for Phase 3 EPS smoke helpers (no ROS runtime)."""

from scripts.ssos_eps_smoke import EpsSmokeReport, run_eps_smoke
from environment.ssos.ros2_eps_bridge import Ros2EpsBridge


def test_eps_smoke_report_serializes():
    report = EpsSmokeReport(ok=True, launch_hint="hint", topics={"solar_voltage_v": 120.0})
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["topics"]["solar_voltage_v"] == 120.0


def test_run_eps_smoke_without_ros2(monkeypatch):
    monkeypatch.setattr(Ros2EpsBridge, "ros2_available", staticmethod(lambda: False))
    report = run_eps_smoke()
    assert report.ok is False
    assert any("ros2 CLI" in err for err in report.errors)


def test_run_eps_smoke_with_fake_bridge(monkeypatch):
    class FakeBridge:
        @staticmethod
        def ros2_available() -> bool:
            return True

        def __init__(self, **_kwargs):
            pass

        def poll_topics(self):
            return {
                "solar_voltage_v": 130.0,
                "bcdu_mode": "idle",
                "bus_voltage_v": 110.0,
            }

        def request_discharge(self, support_w: float, duration_steps: int):
            from environment.ssos.eps_types import DischargeResult

            return DischargeResult(success=True, message="armed")

    monkeypatch.setattr("scripts.ssos_eps_smoke.Ros2EpsBridge", FakeBridge)
    report = run_eps_smoke(arm_discharge_w=100.0, arm_duration_steps=2)
    assert report.ok is True
    assert report.topics["solar_voltage_v"] == 130.0
    assert report.discharge_armed is not None


def test_run_eps_smoke_reports_missing_topics(monkeypatch):
    class FakeBridge:
        @staticmethod
        def ros2_available() -> bool:
            return True

        def __init__(self, **_kwargs):
            pass

        def poll_topics(self):
            return {
                "solar_voltage_v": None,
                "bcdu_mode": None,
            }

    monkeypatch.setattr("scripts.ssos_eps_smoke.Ros2EpsBridge", FakeBridge)
    report = run_eps_smoke()
    assert report.ok is False
    assert any("solar voltage" in err for err in report.errors)
    assert any("BCDU" in err for err in report.errors)
