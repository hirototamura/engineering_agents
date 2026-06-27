#!/usr/bin/env bash
# Headless ECLSS for SSOS Docker regression (no crew GUI).
#
# The public ghcr.io image does not ship /root/ssos-eclss-headless.sh (that path is
# used on self-hosted / ~/dev/ssos setups). ARS needs /ddcu/load_request at startup,
# so launch EPS + solar before ECLSS.
set -eo pipefail

set +u
source /opt/ros/jazzy/setup.bash
source ~/ssos_ws/install/setup.bash
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-23}"
set -u 2>/dev/null || true

if command -v tmux >/dev/null 2>&1 && ! tmux has-session -t discovery 2>/dev/null; then
  tmux new -s discovery -d "fastdds discovery --server-id 0"
  sleep 2
fi

ros2 launch space_station eps.launch.py &
ros2 run space_station_eps solar_power &
sleep 5
exec ros2 launch space_station eclss.launch.py
