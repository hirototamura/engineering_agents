"""ROS 2 topic, action, and service names for space_station_eclss integration.

Names align with SSOS main (space-station-os/space_station_os) as surveyed in Phase 1a.
Launch headless ECLSS (no crew GUI):

    ros2 launch space_station eclss.launch.py

Package-local launch (includes crew GUI):

    ros2 launch space_station_eclss eclss.launch.py
"""

from __future__ import annotations

from typing import Tuple


def normalize_ros_name(name: str) -> str:
    """Strip leading '/' so CLI graph names match our constants."""
    return name.lstrip("/")


def parse_ros_graph_line(line: str) -> str:
    """Extract entity name from a ``ros2 topic list`` / ``ros2 action list`` line.

    Jazzy may emit ``/air_revitalisation space_station_interfaces/action/AirRevitalisation``
    (or legacy ``space_station_eclss/...`` in ``ros2 action list -t``) — only the graph name
    (before whitespace or ``[``) is returned, without a leading slash.
    """
    stripped = line.strip()
    if not stripped:
        return ""
    name = stripped.split(None, 1)[0]
    if "[" in name:
        name = name.split("[", 1)[0]
    return normalize_ros_name(name)


def ros_cli_action_name(name: str) -> str:
    """Absolute action path for ``ros2 action send_goal``."""
    return f"/{normalize_ros_name(name)}"


# --- Actions (ActionClient) -------------------------------------------------

ACTION_AIR_REVITALISATION = "air_revitalisation"
ACTION_WATER_RECOVERY = "water_recovery_systems"
ACTION_OXYGEN_GENERATION = "oxygen_generation"

ACTION_TYPE_AIR_REVITALISATION = "space_station_interfaces/action/AirRevitalisation"
ACTION_TYPE_WATER_RECOVERY = "space_station_interfaces/action/WaterRecovery"
ACTION_TYPE_OXYGEN_GENERATION = "space_station_interfaces/action/OxygenGeneration"

# --- Services (ServiceClient) -----------------------------------------------

SERVICE_OGS_REQUEST_O2 = "/ogs/request_o2"
SERVICE_WRS_PRODUCT_WATER = "/wrs/product_water_request"
SERVICE_ARS_REQUEST_CO2 = "/ars/request_co2"
SERVICE_GREY_WATER = "/grey_water"

SERVICE_TYPE_O2_REQUEST = "space_station_interfaces/srv/O2Request"
SERVICE_TYPE_CO2_REQUEST = "space_station_interfaces/srv/Co2Request"
SERVICE_TYPE_PRODUCT_WATER = "space_station_interfaces/srv/RequestProductWater"
SERVICE_TYPE_GREY_WATER = "space_station_interfaces/srv/GreyWater"

MSG_TYPE_FLOAT64 = "std_msgs/msg/Float64"
MSG_TYPE_BOOL = "std_msgs/msg/Bool"

# --- Telemetry topics (subscribe) -------------------------------------------

TOPIC_CO2_STORAGE = "/co2_storage"
TOPIC_O2_STORAGE = "/o2_storage"
TOPIC_WRS_PRODUCT_WATER_RESERVE = "/wrs/product_water_reserve"

TOPIC_ARS_DIAGNOSTICS = "/ars/diagnostics"
TOPIC_OGS_DIAGNOSTICS = "/ogs/diagnostics"
TOPIC_WRS_DIAGNOSTICS = "/wrs/diagnostics"

# --- Failure / diagnostics control (publish Bool) -----------------------------

TOPIC_ARS_SELF_DIAGNOSIS = "/ars/self_diagnosis"
TOPIC_OGS_SELF_DIAGNOSIS = "/ogs/self_diagnosis"
TOPIC_WRS_SELF_DIAGNOSIS = "/wrs/self_diagnosis"

# --- Launch / config (Phase 1a+) --------------------------------------------

LAUNCH_HEADLESS_ECLSS = "space_station/eclss.launch.py"
LAUNCH_ECLSS_WITH_CREW = "space_station_eclss/eclss.launch.py"

CONFIG_ARS_YAML = "ARS.yaml"
CONFIG_OGS_YAML = "OGS.yaml"
CONFIG_WRS_YAML = "WRS.yaml"

ALL_ECLSS_ACTIONS: Tuple[str, ...] = (
    ACTION_AIR_REVITALISATION,
    ACTION_WATER_RECOVERY,
    ACTION_OXYGEN_GENERATION,
)

ALL_ECLSS_SERVICES: Tuple[str, ...] = (
    SERVICE_OGS_REQUEST_O2,
    SERVICE_WRS_PRODUCT_WATER,
    SERVICE_ARS_REQUEST_CO2,
    SERVICE_GREY_WATER,
)

ALL_ECLSS_TELEMETRY_TOPICS: Tuple[str, ...] = (
    TOPIC_CO2_STORAGE,
    TOPIC_O2_STORAGE,
    TOPIC_WRS_PRODUCT_WATER_RESERVE,
    TOPIC_ARS_DIAGNOSTICS,
    TOPIC_OGS_DIAGNOSTICS,
    TOPIC_WRS_DIAGNOSTICS,
)

ALL_ECLSS_SELF_DIAGNOSIS_TOPICS: Tuple[str, ...] = (
    TOPIC_ARS_SELF_DIAGNOSIS,
    TOPIC_OGS_SELF_DIAGNOSIS,
    TOPIC_WRS_SELF_DIAGNOSIS,
)
