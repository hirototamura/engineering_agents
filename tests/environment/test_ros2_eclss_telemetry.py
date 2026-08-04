"""Unit tests for rclpy telemetry reader helpers."""

import time

from environment.ssos.eclss.ros2 import telemetry


def test_rclpy_telemetry_available_false_without_rclpy(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rclpy":
            raise ImportError("no rclpy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    telemetry.reset_rclpy_telemetry_reader()
    assert telemetry.rclpy_telemetry_available() is False
    assert telemetry.get_rclpy_telemetry_reader() is None


def test_read_fresh_rejects_stale_cached_values(monkeypatch):
    class FakeReader:
        def __init__(self) -> None:
            self._values = {
                "/co2_storage": 1500.0,
                "/o2_storage": 480.0,
                "/wrs/product_water_reserve": 100.0,
            }
            self._updated_at = dict.fromkeys(self._values, time.monotonic() - 60.0)

        def read_fresh(self, wait_timeout_s: float, *, max_age_s: float):
            del wait_timeout_s
            now = time.monotonic()
            fresh = all((now - ts) <= max_age_s for ts in self._updated_at.values())
            if not fresh:
                return None, None, None
            return (
                self._values["/co2_storage"],
                self._values["/o2_storage"],
                self._values["/wrs/product_water_reserve"],
            )

    monkeypatch.setattr(telemetry, "get_rclpy_telemetry_reader", lambda: FakeReader())
    reader = telemetry.get_rclpy_telemetry_reader()
    assert reader is not None
    assert reader.read_fresh(0.0, max_age_s=5.0) == (None, None, None)
