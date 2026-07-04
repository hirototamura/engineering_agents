#!/usr/bin/env bash
# Headless SSOS: one ros2 launch tree (Ctrl+C stops all nodes).
set -eo pipefail

LAUNCH_FILE="${SSOS_LAUNCH_FILE:-/root/ssos-headless.launch.py}"

source_ros() {
  set +u
  # shellcheck disable=SC1090
  source "$1"
  set -u 2>/dev/null || true
}

source_ros /opt/ros/jazzy/setup.bash
source_ros /root/ssos_ws/install/setup.bash

if ! tmux has-session -t discovery 2>/dev/null; then
  /root/entry-point.sh
fi

echo "==> Launching headless SSOS (solar + EPS + ECLSS)..."
echo "    SARJ mock eclipses ~35s per 90s orbit — MBSU warnings until sunlight."
echo "    Ctrl+C stops all nodes. Type 'exit' to leave the container shell."
echo

exec ros2 launch "${LAUNCH_FILE}"
