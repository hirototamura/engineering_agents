"""Unit tests for Phase 2 smoke helpers (no ROS runtime)."""

from scripts.ssos_eclss_2_smoke import Eclss2SmokeReport, run_2_smoke
from environment.ssos.eclss.types import EclssTelemetrySnapshot, OgsGoal, WrsGoal
from environment.ssos.eclss.ros2.bridge import Ros2EclssBridge


def test_2_smoke_report_serializes():
    report = Eclss2SmokeReport(ok=True, launch_hint="hint", water_tradeoff_signal=True)
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["water_tradeoff_signal"] is True


def test_run_2_smoke_without_ros2(monkeypatch):
    monkeypatch.setattr(Ros2EclssBridge, "ros2_available", staticmethod(lambda: False))
    report = run_2_smoke()
    assert report.ok is False
    assert any("ros2 CLI" in err for err in report.errors)


def test_run_2_smoke_detects_water_tradeoff(monkeypatch):
    class FakeBridge:
        @staticmethod
        def ros2_available() -> bool:
            return True

        def __init__(self, **_kwargs):
            self._step = 0

        def poll_telemetry(self):
            self._step += 1
            if self._step == 1:
                return EclssTelemetrySnapshot(product_water_reserve_l=50.0)
            if self._step == 2:
                return EclssTelemetrySnapshot(product_water_reserve_l=52.0)
            return EclssTelemetrySnapshot(product_water_reserve_l=45.0)

        def submit_grey_water(self, liters: float):
            from environment.ssos.eclss.types import ServiceResult

            return ServiceResult(success=True, message="ok")

        def send_water_recovery_goal(self, goal: WrsGoal):
            from environment.ssos.eclss.types import ActionResult

            return ActionResult(
                success=True,
                details={"total_purified_water": 2.0, "total_cycles": 1},
            )

        def request_product_water(self, liters: float):
            from environment.ssos.eclss.types import ServiceResult

            return ServiceResult(success=True, response_value=liters, message="ok")

        def send_oxygen_generation_goal(self, goal: OgsGoal):
            from environment.ssos.eclss.types import ActionResult

            return ActionResult(success=True, details={"total_o2_generated": 10.0})

    monkeypatch.setattr("scripts.ssos_eclss_2_smoke.Ros2EclssBridge", FakeBridge)
    report = run_2_smoke()
    assert report.ok is True
    assert report.water_tradeoff_signal is True
    assert report.product_water_delta == -5.0
