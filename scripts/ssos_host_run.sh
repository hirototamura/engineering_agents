#!/usr/bin/env bash
# Internal host orchestrator for: ea run ssos_eclss_loop (ros2 backend).
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
  echo "Start SSOS with mounts (example — adjust to your ssos-run.sh):" >&2
  echo "  docker run -it --name ssos \\" >&2
  echo "    -v \"$REPO_ROOT/src:$MOUNT_SRC\" \\" >&2
  echo "    -v \"$REPO_ROOT/src/experiments/results:$MOUNT_RESULTS\" \\" >&2
  echo "    ghcr.io/space-station-os/space_station_os:latest" >&2
  exit 3
fi

_check_mounts() {
  if ! docker exec "$CONTAINER" test -d "$MOUNT_SRC/scenario/ssos_eclss_loop"; then
    echo "Volume mount missing: $MOUNT_SRC/scenario not found in container." >&2
    echo "Add to ssos-run.sh:" >&2
    echo "  -v \"$REPO_ROOT/src:$MOUNT_SRC\"" >&2
    echo "  -v \"$REPO_ROOT/src/experiments/results:$MOUNT_RESULTS\"" >&2
    exit 3
  fi
  if ! docker exec "$CONTAINER" test -d "$MOUNT_RESULTS"; then
    echo "Volume mount missing: $MOUNT_RESULTS not found in container." >&2
    exit 3
  fi
}

_stop_headless() {
  echo "==> Stopping ECLSS headless (clean plant state)"
  docker exec "$CONTAINER" bash -lc '
    pkill -f "ssos-eclss-headless" 2>/dev/null || true
    pkill -f "eclss.launch" 2>/dev/null || true
    pkill -f "space_station.*eclss" 2>/dev/null || true
    sleep 2
  ' || true
}

_start_headless() {
  echo "==> Starting ECLSS headless"
  docker exec -d "$CONTAINER" bash -lc 'bash /root/ssos-eclss-headless.sh'
}

_poll_ros2_graph() {
  local deadline=$((SECONDS + HEADLESS_POLL_TIMEOUT_S))
  echo "==> Waiting for ros2 graph (timeout ${HEADLESS_POLL_TIMEOUT_S}s)"
  while ((SECONDS < deadline)); do
    local counts
    counts="$(docker exec "$CONTAINER" bash -lc '
      set +u
      source /opt/ros/jazzy/setup.bash 2>/dev/null
      source ~/ssos_ws/install/setup.bash 2>/dev/null
      set -u 2>/dev/null || true
      t=$(ros2 topic list 2>/dev/null | grep -c . || true)
      a=$(ros2 action list 2>/dev/null | grep -c . || true)
      echo "${t:-0} ${a:-0}"
    ')"
    local topic_count action_count
    read -r topic_count action_count <<<"$counts"
    if [[ "${topic_count:-0}" -gt 0 || "${action_count:-0}" -gt 0 ]]; then
      echo "==> ros2 graph ready (topics=$topic_count actions=$action_count)"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ros2 graph still empty after ${HEADLESS_POLL_TIMEOUT_S}s." >&2
  echo "Check headless logs inside the container." >&2
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
    python3 -m tools.cli job run '$job_in_container'
    rm -f '$job_in_container'
  "
}

_check_mounts
_stop_headless
_start_headless
_poll_ros2_graph
_run_job
