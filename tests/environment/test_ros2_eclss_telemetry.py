"""Unit tests for rclpy telemetry reader helpers."""

from environment.ssos import ros2_eclss_telemetry as telemetry


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
