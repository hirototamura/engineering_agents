#!/usr/bin/env bash
# Internal host orchestrator for: ea run ssos_eclss_loop (ros2 backend).
#
# Each ea run: stop headless → start fresh headless → poll graph → run job.
# This resets SSOS plant state (CO2/O2 tanks, EPS, etc.) between runs.
#
# Prerequisite: SSOS container with volume mounts:
#   -v "$REPO/src:/ea/src"
#   -v "$REPO/src/experiments/results:/ea/results"
#
# Usage (from ea run — not end-user facing):
#   ./scripts/ssos_host_run.sh /path/to/job.json
#
set -euo pipefail

CONTAINER="${SSOS_CONTAINER:-ssos}"
MOUNT_SRC="${EA_MOUNT_SRC:-/ea/src}"
MOUNT_RESULTS="${EA_MOUNT_RESULTS:-/ea/results}"
HEADLESS_POLL_TIMEOUT_S="${EA_HEADLESS_POLL_TIMEOUT_S:-120}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") JOB.json

Runs a RunSpec inside the SSOS Docker container (ros2).
Requires volume mounts on $MOUNT_SRC and $MOUNT_RESULTS.
EOF
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

JOB_JSON_HOST="$1"
if [[ ! -f "$JOB_JSON_HOST" ]]; then
  echo "RunSpec not found: $JOB_JSON_HOST" >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install Docker Desktop and start the SSOS container." >&2
  exit 3
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "SSOS container '$CONTAINER' is not running." >&2
  echo >&2
  if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "Container exists but is stopped. Start it in the background:" >&2
    echo "  docker start $CONTAINER" >&2
    echo >&2
    echo "Then run from the Mac host (not inside the container):" >&2
    echo "  ea run ssos_eclss_loop --agents-mode labeled_rule_base" >&2
  else
    echo "Create the SSOS container with helper scripts mounted:" >&2
    echo "  ./scripts/ssos/mac/ssos-run-detached.sh" >&2
    echo >&2
    echo "See scripts/ssos/README.md (Windows/Linux: manual mounts for now)." >&2
  fi
  exit 3
fi

_check_mounts() {
  if ! docker exec "$CONTAINER" test -d "$MOUNT_SRC/scenario/ssos_eclss_loop"; then
    echo "Volume mount missing: $MOUNT_SRC/scenario not found in container." >&2
    echo "Recreate the container: ./scripts/ssos/mac/ssos-run-detached.sh" >&2
    exit 3
  fi
  if ! docker exec "$CONTAINER" test -f /root/ssos-eclss-headless.sh; then
    echo "SSOS headless helper missing: /root/ssos-eclss-headless.sh" >&2
    echo "Recreate the container so scripts/ssos/* is mounted: ./scripts/ssos/mac/ssos-run-detached.sh" >&2
    exit 3
  fi
  if ! docker exec "$CONTAINER" test -d "$MOUNT_RESULTS"; then
    echo "Volume mount missing: $MOUNT_RESULTS not found in container." >&2
    exit 3
  fi
}

_stop_headless() {
  echo "==> Stopping headless SSOS (reset plant state before this run)"
  docker exec "$CONTAINER" bash -lc '
    pkill -f "ssos-headless.launch" 2>/dev/null || true
    pkill -f "ssos-eclss-headless" 2>/dev/null || true
    pkill -f "eclss.launch" 2>/dev/null || true
    pkill -f "eps.launch" 2>/dev/null || true
    pkill -f "solar_power" 2>/dev/null || true
    pkill -f "space_station_eps" 2>/dev/null || true
    pkill -f "space_station.*eclss" 2>/dev/null || true
    sleep 2
  ' || true
}

_start_headless() {
  echo "==> Starting ECLSS headless (solar + EPS + ECLSS)"
  docker exec -d "$CONTAINER" bash -lc '
    set +u
    source /opt/ros/jazzy/setup.bash
    source ~/ssos_ws/install/setup.bash
    set -u 2>/dev/null || true
    if [[ -f /root/ssos-eclss-headless.sh ]]; then
      exec bash /root/ssos-eclss-headless.sh
    fi
    if [[ -f /root/ssos-headless.launch.py ]]; then
      exec ros2 launch /root/ssos-headless.launch.py
    fi
    echo "ERROR: /root/ssos-eclss-headless.sh not mounted — recreate container with scripts/ssos/mac/ssos-run-detached.sh" >&2
    exit 1
  '
}

_poll_ros2_graph() {
  local deadline=$((SECONDS + HEADLESS_POLL_TIMEOUT_S))
  echo "==> Waiting for ECLSS ros2 graph (timeout ${HEADLESS_POLL_TIMEOUT_S}s)"
  while ((SECONDS < deadline)); do
    local status
    status="$(docker exec "$CONTAINER" bash -lc '
      set +u
      source /opt/ros/jazzy/setup.bash 2>/dev/null
      source ~/ssos_ws/install/setup.bash 2>/dev/null
      set -u 2>/dev/null || true
      topics=$(ros2 topic list 2>/dev/null || true)
      eclss=0
      for t in /co2_storage /o2_storage /wrs/product_water_reserve; do
        if echo "$topics" | grep -qx "$t"; then
          eclss=$((eclss + 1))
        fi
      done
      actions=$(ros2 action list 2>/dev/null | grep -c . || true)
      echo "${eclss:-0} ${actions:-0}"
    ')"
    local eclss_topic_count action_count
    read -r eclss_topic_count action_count <<<"$status"
    if [[ "${eclss_topic_count:-0}" -ge 2 && "${action_count:-0}" -gt 0 ]]; then
      echo "==> ECLSS ros2 graph ready (storage_topics=$eclss_topic_count actions=$action_count)"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ECLSS ros2 graph not ready after ${HEADLESS_POLL_TIMEOUT_S}s." >&2
  echo "Expected /co2_storage, /o2_storage, or /wrs/product_water_reserve plus ECLSS actions." >&2
  echo "Inside container: ros2 topic list && ros2 action list" >&2
  exit 3
}

_run_job() {
  local job_in_container="/tmp/ea-job-$$.json"
  echo "==> Running job in '$CONTAINER'"
  docker cp "$JOB_JSON_HOST" "$CONTAINER:$job_in_container"
  docker exec "$CONTAINER" bash -lc "
    set -euo pipefail
    set +u
    source /opt/ros/jazzy/setup.bash
    source ~/ssos_ws/install/setup.bash
    set -u 2>/dev/null || true
    export SSOS_CONTAINER_REPO=/ea
    export EA_RESULTS_ROOT='$MOUNT_RESULTS'
    export PYTHONPATH='$MOUNT_SRC'\${PYTHONPATH:+:\$PYTHONPATH}
    export SSOS_ECLSS_BACKEND=ros2
    export OLLAMA_BASE_URL=\${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
    export EA_RUN_IN_CONTAINER=1
    cd /ea
    python3 -m scenario.jobs '$job_in_container'
    rm -f '$job_in_container'
  "
}

_check_mounts
_stop_headless
_start_headless
_poll_ros2_graph
_run_job
