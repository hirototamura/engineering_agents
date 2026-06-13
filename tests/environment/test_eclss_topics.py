"""Contract tests for SSOS ECLSS topic/action names (Phase 1a)."""

from environment.ssos import eclss_topics as topics


def test_all_eclss_actions_are_unique():
    assert len(topics.ALL_ECLSS_ACTIONS) == len(set(topics.ALL_ECLSS_ACTIONS))


def test_all_eclss_services_are_unique():
    assert len(topics.ALL_ECLSS_SERVICES) == len(set(topics.ALL_ECLSS_SERVICES))


def test_ars_smoke_required_interfaces_present():
    assert topics.ACTION_AIR_REVITALISATION in topics.ALL_ECLSS_ACTIONS
    assert topics.TOPIC_CO2_STORAGE in topics.ALL_ECLSS_TELEMETRY_TOPICS
    assert topics.TOPIC_ARS_DIAGNOSTICS in topics.ALL_ECLSS_TELEMETRY_TOPICS


def test_headless_launch_constant():
    assert topics.LAUNCH_HEADLESS_ECLSS == "space_station/eclss.launch.py"


def test_action_type_strings_use_ssos_package():
    assert topics.ACTION_TYPE_AIR_REVITALISATION.startswith("space_station_eclss/action/")


def test_self_diagnosis_topics_are_absolute():
    for name in topics.ALL_ECLSS_SELF_DIAGNOSIS_TOPICS:
        assert name.startswith("/")


def test_parse_ros_graph_line_with_leading_slash():
    assert topics.parse_ros_graph_line("/co2_storage") == "co2_storage"


def test_parse_ros_graph_line_without_leading_slash():
    assert topics.parse_ros_graph_line("ars/diagnostics") == "ars/diagnostics"


def test_parse_ros_graph_line_strips_jazzy_type_suffix():
    line = "/air_revitalisation space_station_eclss/action/AirRevitalisation"
    assert topics.parse_ros_graph_line(line) == "air_revitalisation"


def test_parse_ros_graph_line_strips_bracketed_type_suffix():
    line = "/air_revitalisation [space_station_eclss/action/AirRevitalisation]"
    assert topics.parse_ros_graph_line(line) == "air_revitalisation"
