"""ROS2-like topic and service names for SSOS / ECLSS integration."""

# Telemetry (simulator → agents)
TELEMETRY_CO2 = "/eclss/telemetry/co2_ppm"
TELEMETRY_SCRUBBER = "/eclss/telemetry/scrubber_efficiency"
TELEMETRY_POWER = "/eclss/telemetry/power_margin_w"
TELEMETRY_HEALTH = "/eclss/telemetry/health_summary"

# Commands (agents → simulator)
CMD_SET_FAN_SPEED = "/eclss/command/set_fan_speed"
CMD_ENABLE_BYPASS = "/eclss/command/enable_bypass"
CMD_REDUCE_LOAD = "/eclss/command/reduce_load"
CMD_REQUEST_EPS_BOOST = "/eclss/command/request_eps_boost"

# Design (agents → SSOT / simulator)
DESIGN_APPLY_CHANGE = "/eclss/design/apply_change"
DESIGN_GET_TOPOLOGY = "/eclss/design/get_topology"
DESIGN_GET_PARAMETERS = "/eclss/design/get_parameters"

# Events
EVENT_ANOMALY = "/eclss/events/anomaly"
EVENT_RECOVERY = "/eclss/events/recovery_applied"
EVENT_DESIGN_CHANGE = "/eclss/events/design_change"

ALL_TELEMETRY_TOPICS = (
    TELEMETRY_CO2,
    TELEMETRY_SCRUBBER,
    TELEMETRY_POWER,
    TELEMETRY_HEALTH,
)

ALL_COMMAND_TOPICS = (
    CMD_SET_FAN_SPEED,
    CMD_ENABLE_BYPASS,
    CMD_REDUCE_LOAD,
    CMD_REQUEST_EPS_BOOST,
)
