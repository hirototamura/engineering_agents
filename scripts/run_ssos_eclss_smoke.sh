#!/usr/bin/env bash
# Phase 1a: run SSOS ECLSS ARS smoke inside the SSOS Docker container.
#
# Host Mac (.venv) has no ros2 CLI — that failure is expected. This wrapper
# syncs src/ into the container and execs the smoke module there.
#
# Known container on this machine (2026-06): name=ssos,
# image=ghcr.io/space-station-os/space_station_os:latest
#
# Prerequisite: ECLSS stack running in the container (terminal 1):
#   docker exec -it ssos bash
#   bash /root/ssos-eclss-headless.sh
#
# Then from the repo root (terminal 2):
#   ./scripts/run_ssos_eclss_smoke.sh
#
set -euo pipefail

CONTAINER="${SSOS_CONTAINER:-ssos}"
CONTAINER_REPO="${SSOS_CONTAINER_REPO:-/tmp/engineering_agents}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

run_smoke() {
  local workdir="$1"
  shift
  cd "$workdir"
  PYTHONPATH="$workdir/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m scripts.ssos_eclss_ars_smoke "$@"
}

if command -v ros2 >/dev/null 2>&1; then
  run_smoke "$REPO_ROOT" "$@"
  exit $?
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ros2 CLI not found on host and docker is unavailable." >&2
  echo "Run this smoke inside the SSOS container — see memo/ssos_eclss_loop_connection_plan.md" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "SSOS container '$CONTAINER' is not running." >&2
  echo >&2
  echo "Start SSOS (example — adjust mounts to your setup):" >&2
  echo "  docker run -it --name ssos ghcr.io/space-station-os/space_station_os:latest" >&2
  echo >&2
  echo "Then launch headless ECLSS in terminal 1:" >&2
  echo "  docker exec -it $CONTAINER bash" >&2
  echo "  bash /root/ssos-eclss-headless.sh" >&2
  echo >&2
  echo "Re-run this script from terminal 2." >&2
  exit 1
fi

echo "==> Syncing src/ to $CONTAINER:$CONTAINER_REPO/src"
docker exec "$CONTAINER" mkdir -p "$CONTAINER_REPO"
docker cp "$REPO_ROOT/src/." "$CONTAINER:$CONTAINER_REPO/src/"

_ros_env='
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  set -u 2>/dev/null || true
'

topic_count="$(docker exec "$CONTAINER" bash -lc "${_ros_env}
  ros2 topic list 2>/dev/null | grep -c . || true
" || echo 0)"
action_count="$(docker exec "$CONTAINER" bash -lc "${_ros_env}
  ros2 action list 2>/dev/null | grep -c . || true
" || echo 0)"
if [ "${topic_count:-0}" -eq 0 ] && [ "${action_count:-0}" -eq 0 ]; then
  echo "WARNING: ros2 graph is empty — ECLSS may not be running yet." >&2
  echo "Launch ECLSS first: bash /root/ssos-eclss-headless.sh" >&2
  echo "(smoke will retry discovery for --wait-timeout seconds)" >&2
fi

quoted_args=""
for arg in "$@"; do
  quoted_args+=" $(printf '%q' "$arg")"
done

echo "==> Running smoke in container '$CONTAINER'"
if [ -t 0 ]; then
  docker exec -it "$CONTAINER" bash -lc "
  set -eo pipefail
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  set -u 2>/dev/null || true
  cd '$CONTAINER_REPO'
  PYTHONPATH='$CONTAINER_REPO/src:'"\${PYTHONPATH:-}" python3 -m scripts.ssos_eclss_ars_smoke${quoted_args}
"
else
  docker exec "$CONTAINER" bash -lc "
  set -eo pipefail
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  set -u 2>/dev/null || true
  cd '$CONTAINER_REPO'
  PYTHONPATH='$CONTAINER_REPO/src:'"\${PYTHONPATH:-}" python3 -m scripts.ssos_eclss_ars_smoke${quoted_args}
"
fi
