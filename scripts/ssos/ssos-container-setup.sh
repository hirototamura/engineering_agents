#!/usr/bin/env bash
# Runs inside the SSOS container on startup.

set -eo pipefail

source_ros() {
  set +u
  # shellcheck disable=SC1090
  source "$1"
  set -u 2>/dev/null || true
}

echo "==> Running SSOS container setup..."

# Fast DDS discovery server (from entry-point.sh)
if ! tmux has-session -t discovery 2>/dev/null; then
  /root/entry-point.sh
  echo "    Fast DDS discovery server started (tmux session: discovery)"
else
  echo "    Fast DDS discovery server already running"
fi

# Persist ROS environment for interactive shells
if ! grep -q 'ssos_ws/install/setup.bash' ~/.bashrc 2>/dev/null; then
  cat >> ~/.bashrc <<'EOF'

# Space Station OS
source /opt/ros/jazzy/setup.bash
source /root/ssos_ws/install/setup.bash
EOF
  echo "    ROS 2 workspace added to ~/.bashrc"
fi

source_ros /opt/ros/jazzy/setup.bash
source_ros /root/ssos_ws/install/setup.bash

echo "==> SSOS ready"
echo "    Workspace: /root/ssos_ws"
echo "    Launch:    ros2 launch space_station space_station.launch.py"
echo "    ECLSS:     bash /root/ssos-eclss-headless.sh   # solar + EPS + ECLSS"
echo "    EPS only:  ros2 launch /root/ssos-eps.launch.py"
echo "    Stop sim:  Ctrl+C (during ros2 launch) / exit (leave container)"
echo "    OpenMCT:   /root/ssos_ws/src/space_station_os/open_mct-bridge.sh /root/ssos_ws"
echo

if [[ "${SSOS_CONTAINER_DETACHED:-}" == "1" ]]; then
  echo "==> Detached mode — container stays up for host 'ea run'"
  exit 0
fi

exec bash -l
