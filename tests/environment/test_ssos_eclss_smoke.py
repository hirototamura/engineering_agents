"""Unit tests for SSOS ECLSS smoke helpers (no ROS runtime required)."""

from scripts.ssos_eclss_ars_smoke import _filter_eclss_topics, _match_expected, send_ars_goal_cli
from environment.ssos.eclss_types import ArsGoal


def test_filter_eclss_topics():
    raw = ["/co2_storage", "/tf", "/ars/diagnostics", "/unrelated"]
    filtered = _filter_eclss_topics(raw)
    assert "/co2_storage" in filtered
    assert "/ars/diagnostics" in filtered
    assert "/unrelated" not in filtered
    assert "/tf" not in filtered


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
