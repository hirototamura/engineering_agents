"""Contract and integration tests for Ros2EpsBridge (Phase 3)."""

import subprocess

import pytest

from environment.ssos.eps_backend import EpsBackend
from environment.ssos.eps_types import BcduMode
from environment.ssos.message_adapters import estimate_discharge_w, parse_bcdu_status
from environment.ssos.ros2_eps_bridge import Ros2EpsBridge
from environment.ssos.eps_topics import BCDU_STATUS
from environment.ssos.topic_map import SSOS_TOPIC_SOLAR_VOLTAGE


def test_ros2_eps_bridge_satisfies_protocol():
    assert isinstance(Ros2EpsBridge(), EpsBackend)


def test_ros2_available_false_when_cli_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("ros2")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    assert Ros2EpsBridge.ros2_available() is False


def test_parse_bcdu_status_yaml():
    text = (
        "header:\n"
        "  stamp:\n"
        "    sec: 0\n"
        "    nanosec: 0\n"
        "  frame_id: ''\n"
        "mode: discharging\n"
        "bus_voltage: 110.0\n"
        "regulation_voltage: 120.0\n"
        "current_draw: 1.5\n"
        "fault: false\n"
        "fault_message: ''\n"
    )
    status = parse_bcdu_status(text, step=3, support_w=120.0, support_steps_remaining=2)
    assert status is not None
    assert status.mode == BcduMode.DISCHARGING
    assert status.bus_voltage_v == 110.0
    assert status.current_draw_a == 1.5
    assert estimate_discharge_w(status) == 165.0


def test_parse_bcdu_status_jazzy_repr():
    text = (
        "space_station_interfaces.msg.BCDUStatus("
        "header=std_msgs.msg.Header(stamp=builtin_interfaces.msg.Time(sec=0, nanosec=0), frame_id=''), "
        "mode='charging', bus_voltage=115.0, regulation_voltage=120.0, current_draw=-0.8, "
        "fault=False, fault_message='')"
    )
    status = parse_bcdu_status(text)
    assert status is not None
    assert status.mode == BcduMode.CHARGING
    assert status.bus_voltage_v == 115.0
    assert status.current_draw_a == -0.8


def test_poll_solar_reads_ssu_voltage_and_beta(monkeypatch):
    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 else ""
        if topic == SSOS_TOPIC_SOLAR_VOLTAGE:
            return subprocess.CompletedProcess(args, 0, "data: 140.0\n", "")
        if topic == "/solar_controller/sun_beta_deg":
            return subprocess.CompletedProcess(args, 0, "data: 30.0\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    solar = Ros2EpsBridge().poll_solar()
    assert solar.solar_voltage_v == 140.0
    assert solar.beta_angle_deg == 30.0
    assert not solar.in_eclipse


def test_poll_bcdu_parses_status_topic(monkeypatch):
    bcdu_yaml = (
        "mode: idle\n"
        "bus_voltage: 108.0\n"
        "regulation_voltage: 120.0\n"
        "current_draw: 0.0\n"
        "fault: false\n"
        "fault_message: ''\n"
    )

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 else ""
        if topic == BCDU_STATUS:
            return subprocess.CompletedProcess(args, 0, bcdu_yaml, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    status = Ros2EpsBridge().poll_bcdu()
    assert status.mode == BcduMode.IDLE
    assert status.bus_voltage_v == 108.0


def test_request_discharge_arms_timer_and_consume_uses_live_watts(monkeypatch):
    bcdu_yaml = (
        "mode: discharging\n"
        "bus_voltage: 100.0\n"
        "regulation_voltage: 120.0\n"
        "current_draw: 1.2\n"
        "fault: false\n"
        "fault_message: ''\n"
    )

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 else ""
        if topic == BCDU_STATUS:
            return subprocess.CompletedProcess(args, 0, bcdu_yaml, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    bridge = Ros2EpsBridge()
    result = bridge.request_discharge(150.0, 3)
    assert result.success
    assert bridge.support_steps_remaining == 3
    assert bridge.consume_scheduled_support() == 120.0


def test_request_discharge_jazzy_repr_bcdu(monkeypatch):
    bcdu_repr = (
        "space_station_interfaces.msg.BCDUStatus("
        "header=std_msgs.msg.Header(stamp=builtin_interfaces.msg.Time(sec=0, nanosec=0), frame_id=''), "
        "mode='discharging', bus_voltage=110.0, regulation_voltage=120.0, current_draw=2.0, "
        "fault=False, fault_message='')"
    )

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 else ""
        if topic == BCDU_STATUS:
            return subprocess.CompletedProcess(args, 0, bcdu_repr, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    bridge = Ros2EpsBridge()
    bridge.request_discharge(200.0, 2)
    assert bridge.consume_scheduled_support() == 220.0


def test_request_discharge_rejects_fault(monkeypatch):
    bcdu_yaml = (
        "mode: fault\n"
        "bus_voltage: 50.0\n"
        "regulation_voltage: 120.0\n"
        "current_draw: 0.0\n"
        "fault: true\n"
        "fault_message: 'bus low'\n"
    )

    def fake_run(args, **_kwargs):
        topic = args[3] if len(args) > 3 else ""
        if topic == BCDU_STATUS:
            return subprocess.CompletedProcess(args, 0, bcdu_yaml, "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("environment.ssos.ros2_eclss_bridge.subprocess.run", fake_run)
    result = Ros2EpsBridge().request_discharge(100.0, 2)
    assert not result.success
    assert "fault" in result.message.lower()


@pytest.mark.skipif(not Ros2EpsBridge.ros2_available(), reason="ros2 CLI not available")
def test_integration_poll_topics_when_eps_running():
    """Requires SSOS EPS stack running (Docker). Skips on dev machines without ros2."""
    payload = Ros2EpsBridge(topic_timeout_s=5.0).poll_topics()
    assert "solar_voltage_v" in payload
