"""Unit tests for Phase 1b smoke helpers (no ROS runtime)."""

from scripts.ssos_eclss_1b_smoke import Eclss1bSmokeReport, run_1b_smoke
from environment.ssos.eclss_types import EclssTelemetrySnapshot, OgsGoal
from environment.ssos.ros2_eclss_bridge import Ros2EclssBridge


def test_1b_smoke_report_serializes():
    report = Eclss1bSmokeReport(ok=True, launch_hint="hint", sabatier_signal=True)
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["sabatier_signal"] is True


def test_run_1b_smoke_without_ros2(monkeypatch):
    monkeypatch.setattr(Ros2EclssBridge, "ros2_available", staticmethod(lambda: False))
    report = run_1b_smoke()
    assert report.ok is False
    assert any("ros2 CLI" in err for err in report.errors)


def test_run_1b_smoke_detects_sabatier_signal(monkeypatch):
    class FakeBridge:
        @staticmethod
        def ros2_available() -> bool:
            return True

        def __init__(self, **_kwargs):
            self._step = 0

        def poll_telemetry(self):
            self._step += 1
            if self._step == 1:
                return EclssTelemetrySnapshot(co2_storage_kg=100.0, o2_storage_kg=0.0)
            return EclssTelemetrySnapshot(co2_storage_kg=90.0, o2_storage_kg=5.0)

        def request_co2(self, amount: float):
            from environment.ssos.eclss_types import ServiceResult

            return ServiceResult(success=True, response_value=amount, message="ok")

        def send_oxygen_generation_goal(self, goal: OgsGoal):
            from environment.ssos.eclss_types import ActionResult

            return ActionResult(
                success=True,
                details={"total_o2_generated": 5.0, "total_ch4_vented": 1.0},
            )

    monkeypatch.setattr("scripts.ssos_eclss_1b_smoke.Ros2EclssBridge", FakeBridge)
    report = run_1b_smoke()
    assert report.ok is True
    assert report.sabatier_signal is True
    assert report.o2_storage_delta == 5.0
