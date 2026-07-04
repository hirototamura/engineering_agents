"""ROS2-like topic names for space_station_eps mock integration."""

# SARJ
SOLAR_VOLTAGE = "/solar/voltage"

# BCDU
BCDU_OPERATION = "/bcdu/operation"
BCDU_STATUS = "/bcdu/status"

# Diagnostics
EPS_DIAGNOSTICS = "/eps/diagnostics"

# Bridge to ECLSS (EPS-3 will route request_eps_boost here)
ECLSS_LOAD_REQUEST_W = "/eps/eclss/load_request_w"

ALL_EPS_TOPICS = (
    SOLAR_VOLTAGE,
    BCDU_OPERATION,
    BCDU_STATUS,
    EPS_DIAGNOSTICS,
    ECLSS_LOAD_REQUEST_W,
)
