"""SSOS ROS graph names mapped to engineering_agents EPS contract topics."""

from __future__ import annotations

from typing import Dict

from environment.ssos.eps_topics import (
    BCDU_STATUS,
    EPS_DIAGNOSTICS,
    SOLAR_VOLTAGE,
)

# Canonical SSOS topics (space-station-os main)
SSOS_TOPIC_SOLAR_VOLTAGE = "/solar_controller/ssu_voltage_v"
SSOS_TOPIC_SOLAR_POWER = "/solar_controller/ssu_power_w"
SSOS_TOPIC_SUN_BETA = "/solar_controller/sun_beta_deg"

MSG_TYPE_FLOAT64 = "std_msgs/msg/Float64"
MSG_TYPE_BCDU_STATUS = "space_station_interfaces/msg/BCDUStatus"
MSG_TYPE_DIAGNOSTIC_STATUS = "diagnostic_msgs/msg/DiagnosticStatus"

LAUNCH_HEADLESS_STATION = "space_station/space_station.launch.py"
LAUNCH_EPS_ONLY = "space_station/eps.launch.py"

CONTRACT_TO_SSOS_TOPIC: Dict[str, str] = {
    SOLAR_VOLTAGE: SSOS_TOPIC_SOLAR_VOLTAGE,
    BCDU_STATUS: BCDU_STATUS,
    EPS_DIAGNOSTICS: EPS_DIAGNOSTICS,
}
