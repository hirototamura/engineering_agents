"""Unit tests for SSOS ECLSS smoke helpers (no ROS runtime required)."""

from scripts.ssos_eclss_ars_smoke import (
    _filter_eclss_topics,
    _match_expected,
    discover_ros_graph,
    send_ars_goal_cli,
)
from environment.ssos.eclss_types import ArsGoal


def test_filter_eclss_topics():
    raw = ["co2_storage", "/tf", "ars/diagnostics", "/unrelated"]
    filtered = _filter_eclss_topics(raw)
    assert "co2_storage" in filtered
    assert "ars/diagnostics" in filtered
    assert "unrelated" not in filtered
    assert "tf" not in filtered


def test_match_expected_reports_missing_interfaces():
    errors = _match_expected(topics=[], actions=[])
    assert any("co2_storage" in err for err in errors)
    assert any("air_revitalisation" in err for err in errors)


def test_match_expected_passes_with_minimal_graph():
    errors = _match_expected(
        topics=["/co2_storage", "/ars/diagnostics"],
        actions=["air_revitalisation"],
    )
    assert errors == []


def test_match_expected_accepts_leading_slash_action():
    errors = _match_expected(
        topics=["/co2_storage", "/ars/diagnostics"],
        actions=["/air_revitalisation"],
    )
    assert errors == []


def test_match_expected_accepts_jazzy_action_list_line():
    errors = _match_expected(
        topics=["co2_storage", "ars/diagnostics"],
        actions=["air_revitalisation space_station_eclss/action/AirRevitalisation"],
    )
    assert errors == []


def test_discover_ros_graph_retries_until_ready(monkeypatch):
    calls = {"n": 0}

    def fake_snapshot():
        calls["n"] += 1
        if calls["n"] < 3:
            return ["co2_storage"], [], None
        return ["co2_storage", "ars/diagnostics"], ["air_revitalisation"], None

    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke._discover_ros_graph_snapshot", fake_snapshot)
    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke.time.sleep", lambda _s: None)

    topics, actions, err = discover_ros_graph(wait_timeout_s=10.0, poll_interval_s=0.01)
    assert err is None
    assert "ars/diagnostics" in topics
    assert "air_revitalisation" in actions
    assert calls["n"] == 3


def test_discover_ros_graph_timeout_reports_not_ready(monkeypatch):
    def fake_snapshot():
        return ["co2_storage"], ["oxygen_generation"], None

    clock = {"t": 0.0}

    def fake_monotonic():
        return clock["t"]

    def fake_sleep(interval: float) -> None:
        clock["t"] += interval

    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke._discover_ros_graph_snapshot", fake_snapshot)
    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke.time.monotonic", fake_monotonic)
    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke.time.sleep", fake_sleep)

    topics, actions, err = discover_ros_graph(wait_timeout_s=6.0, poll_interval_s=2.0)
    assert err is not None
    assert "ECLSS not ready" in err
    assert topics == ["co2_storage"]
    assert actions == ["oxygen_generation"]


def test_send_ars_goal_cli_uses_absolute_action_name(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = list(cmd)

        class Result:
            returncode = 0
            stdout = "Goal finished with status: SUCCEEDED\nResult:\n"
            stderr = ""

        return Result()

    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke.subprocess.run", fake_run)
    result, err = send_ars_goal_cli(ArsGoal())
    assert err is None
    assert result is not None
    assert captured["cmd"][4] == "/air_revitalisation"


def test_send_ars_goal_cli_without_ros2(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("ros2")

    monkeypatch.setattr("scripts.ssos_eclss_ars_smoke.subprocess.run", fake_run)
    result, err = send_ars_goal_cli(ArsGoal())
    assert result is None
    assert err is not None
