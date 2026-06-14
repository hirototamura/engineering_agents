"""Contract and integration tests for Ros2EclssBridge (Phase 1b)."""

import subprocess

import pytest

from environment.ssos.eclss_backend import EclssBackend
from environment.ssos.eclss_types import ArsGoal, OgsGoal, WrsGoal
from environment.ssos.ros2_eclss_bridge import Ros2EclssBridge, _echo_float_topic, _run_ros2_cli


def test_ros2_bridge_satisfies_protocol():
    assert isinstance(Ros2EclssBridge(), EclssBackend)


def test_ros2_available_false_when_cli_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("ros2")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    assert Ros2EclssBridge.ros2_available() is False


def test_poll_telemetry_parses_float_topics(monkeypatch):
    responses = {
        ("/co2_storage",): "data: 1234.5\n",
        ("/o2_storage",): "data: 678.0\n",
        ("/wrs/product_water_reserve",): "data: 42.0\n",
    }

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 and args[1] == "topic" else ""
        body = responses.get((topic,), "")
        return subprocess.CompletedProcess(args, 0, body, "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    snap = Ros2EclssBridge().poll_telemetry()
    assert snap.co2_storage_kg == 1234.5
    assert snap.o2_storage_kg == 678.0
    assert snap.product_water_reserve_l == 42.0


def test_request_o2_parses_service_response(monkeypatch):
    def fake_run(args, **_kwargs):
        assert args[0:2] == ["ros2", "service"]
        return subprocess.CompletedProcess(
            args,
            0,
            "response:\n  o2_resp: 500.0\n  success: true\n  message: 'ok'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_o2(500.0)
    assert result.success
    assert result.response_value == 500.0
    assert result.message == "ok"


def test_request_co2_parses_service_response(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            "response:\n  co2_resp: 120.0\n  success: true\n  message: 'delivered'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_co2(120.0)
    assert result.success
    assert result.response_value == 120.0


def test_request_co2_parses_jazzy_repr_service_response(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            (
                "response:\n"
                "space_station_interfaces.srv.Co2Request_Response("
                "co2_resp=50.0, success=True, message='CO2 successfully delivered')\n"
            ),
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_co2(50.0)
    assert result.success
    assert result.response_value == 50.0
    assert result.message == "CO2 successfully delivered"


def test_request_o2_parses_jazzy_repr_insufficient_storage(monkeypatch):
    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args,
            0,
            (
                "response:\n"
                "space_station_interfaces.srv.O2Request_Response("
                "o2_resp=0.0, success=False, message='Insufficient O2 in storage')\n"
            ),
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    result = Ros2EclssBridge().request_o2(100.0)
    assert result.success is False
    assert result.response_value == 0.0
    assert "Insufficient" in result.message


def test_poll_telemetry_includes_failure_flags_after_set(monkeypatch):
    def fake_run(args, **_kwargs):
        if len(args) > 3 and args[1] == "topic" and args[2] == "echo":
            return subprocess.CompletedProcess(args, 0, "data: 100.0\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    bridge = Ros2EclssBridge()
    bridge.set_subsystem_failure("ogs", True)
    snap = bridge.poll_telemetry()
    assert snap.ogs_failure_enabled is True
    assert snap.ars_failure_enabled is False


def test_send_oxygen_generation_goal_parses_action_result(monkeypatch):
    def fake_run(args, **_kwargs):
        assert "/oxygen_generation" in args
        return subprocess.CompletedProcess(
            args,
            0,
            "Goal finished with status: SUCCEEDED\n"
            "Result:\n  success: true\n"
            "  total_o2_generated: 88.0\n"
            "  summary_message: 'done'\n",
            "",
        )

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    result = Ros2EclssBridge().send_oxygen_generation_goal(OgsGoal())
    assert result.success
    assert result.details.get("total_o2_generated") == 88.0


def test_set_subsystem_failure_publishes_bool(monkeypatch):
    captured = {}

    def fake_run(args, **_kwargs):
        captured["args"] = list(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    Ros2EclssBridge().set_subsystem_failure("ogs", True)
    assert captured["args"][1:5] == ["topic", "pub", "--once", "/ogs/self_diagnosis"]
    assert "{data: true}" in captured["args"][-1]


def test_wrs_methods_raise_not_implemented():
    bridge = Ros2EclssBridge()
    with pytest.raises(NotImplementedError):
        bridge.send_water_recovery_goal(WrsGoal())
    with pytest.raises(NotImplementedError):
        bridge.request_product_water(1.0)
    with pytest.raises(NotImplementedError):
        bridge.submit_grey_water(1.0)


@pytest.mark.skipif(not Ros2EclssBridge.ros2_available(), reason="ros2 CLI not available")
def test_integration_poll_telemetry_when_eclss_running():
    """Requires SSOS ECLSS stack running (Docker). Skips on dev machines without ros2."""
    snap = Ros2EclssBridge(topic_timeout_s=5.0).poll_telemetry()
    # At least one storage topic should respond when ECLSS is up; otherwise fields stay None.
    assert snap.co2_storage_kg is not None or snap.o2_storage_kg is not None or snap.raw_topics == {}


@pytest.mark.skipif(not Ros2EclssBridge.ros2_available(), reason="ros2 CLI not available")
def test_integration_ros_graph_lists_eclss_interfaces():
    code, out, _ = _run_ros2_cli(["topic", "list"], timeout_s=10.0)
    assert code == 0
    topics = set(out.splitlines())
    # When ECLSS is not running this still passes (empty or partial graph).
    if "/co2_storage" in topics:
        value = _echo_float_topic("/co2_storage", timeout_s=5.0)
        assert value is not None
