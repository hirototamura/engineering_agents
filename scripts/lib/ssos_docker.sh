#!/usr/bin/env bash
# Shared SSOS Docker helpers for smoke tests and E2E regression.
#
# Source from other scripts:
#   _SSOS_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/ssos_docker.sh"
#   # shellcheck source=scripts/lib/ssos_docker.sh
#   source "$_SSOS_LIB/ssos_docker.sh"

SSOS_CONTAINER="${SSOS_CONTAINER:-ssos}"
SSOS_CONTAINER_REPO="${SSOS_CONTAINER_REPO:-/tmp/engineering_agents}"
SSOS_IMAGE="${SSOS_IMAGE:-ghcr.io/space-station-os/space_station_os:latest}"
SSOS_HEADLESS_SCRIPT="${SSOS_HEADLESS_SCRIPT:-/root/ssos-eclss-headless.sh}"
SSOS_HEADLESS_FULL_SCRIPT="${SSOS_HEADLESS_FULL_SCRIPT:-/root/ssos-headless.sh}"
SSOS_ROS_DOMAIN_ID="${SSOS_ROS_DOMAIN_ID:-23}"
SSOS_GRAPH_WAIT_TIMEOUT_S="${SSOS_GRAPH_WAIT_TIMEOUT_S:-300}"
SSOS_GRAPH_POLL_INTERVAL_S="${SSOS_GRAPH_POLL_INTERVAL_S:-5}"

ssos_repo_root() {
  if [[ -n "${SSOS_REPO_ROOT:-}" ]]; then
    printf '%s\n' "$SSOS_REPO_ROOT"
    return 0
  fi
  local lib_dir
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SSOS_REPO_ROOT="$(cd "$lib_dir/../.." && pwd)"
  printf '%s\n' "$SSOS_REPO_ROOT"
}

ssos_docker_available() {
  command -v docker >/dev/null 2>&1
}

ssos_ros_env_snippet() {
  cat <<EOF
set +u
source /opt/ros/jazzy/setup.bash
source ~/ssos_ws/install/setup.bash
export ROS_DOMAIN_ID=\${ROS_DOMAIN_ID:-${SSOS_ROS_DOMAIN_ID}}
set -u 2>/dev/null || true
EOF
}

ssos_container_running() {
  ssos_docker_available || return 1
  docker ps --format '{{.Names}}' | grep -qx "$SSOS_CONTAINER"
}

ssos_sync_to_container() {
  local repo_root
  repo_root="$(ssos_repo_root)"

  if ! ssos_docker_available; then
    echo "docker not found." >&2
    return 1
  fi
  if ! ssos_container_running; then
    echo "SSOS container '$SSOS_CONTAINER' is not running." >&2
    return 1
  fi

  echo "==> Syncing src/ to $SSOS_CONTAINER:$SSOS_CONTAINER_REPO/src"
  docker exec "$SSOS_CONTAINER" mkdir -p "$SSOS_CONTAINER_REPO"
  docker cp "$repo_root/src/." "$SSOS_CONTAINER:$SSOS_CONTAINER_REPO/src/"

  local runner_src="$repo_root/scripts/ssos_container_run.sh"
  if [[ -f "$runner_src" ]]; then
    echo "==> Installing in-container runner at $SSOS_CONTAINER_REPO/run.sh and /usr/local/bin/ea-loop"
    docker cp "$runner_src" "$SSOS_CONTAINER:$SSOS_CONTAINER_REPO/run.sh"
    docker exec "$SSOS_CONTAINER" chmod +x "$SSOS_CONTAINER_REPO/run.sh"
    docker exec "$SSOS_CONTAINER" ln -sf "$SSOS_CONTAINER_REPO/run.sh" /usr/local/bin/ea-loop
  fi
}

ssos_ros_graph_counts() {
  docker exec "$SSOS_CONTAINER" bash -lc "
$(ssos_ros_env_snippet)
topics=\$(ros2 topic list 2>/dev/null | grep -c . || true)
actions=\$(ros2 action list 2>/dev/null | grep -c . || true)
printf '%s %s' \"\${topics:-0}\" \"\${actions:-0}\"
"
}

ssos_ros_graph_ready() {
  local topic_count action_count
  read -r topic_count action_count <<< "$(ssos_ros_graph_counts)"
  [[ "${topic_count:-0}" -gt 0 || "${action_count:-0}" -gt 0 ]]
}

ssos_wait_for_ros_graph() {
  local deadline=$((SECONDS + SSOS_GRAPH_WAIT_TIMEOUT_S))
  local topic_count action_count

  while (( SECONDS < deadline )); do
    read -r topic_count action_count <<< "$(ssos_ros_graph_counts)"
    if [[ "${topic_count:-0}" -gt 0 || "${action_count:-0}" -gt 0 ]]; then
      echo "==> ROS graph ready (${topic_count} topics, ${action_count} actions)"
      return 0
    fi
    echo "==> Waiting for ROS graph (${SSOS_GRAPH_POLL_INTERVAL_S}s poll)..."
    sleep "$SSOS_GRAPH_POLL_INTERVAL_S"
  done

  echo "ERROR: ROS graph still empty after ${SSOS_GRAPH_WAIT_TIMEOUT_S}s" >&2
  echo "Headless script: ${SSOS_HEADLESS_SCRIPT:-<unset>}" >&2
  return 1
}

ssos_start_managed_container() {
  if ! ssos_docker_available; then
    echo "docker not found." >&2
    return 1
  fi

  if ssos_container_running; then
    echo "==> Using existing container '$SSOS_CONTAINER'"
    return 0
  fi

  if docker ps -a --format '{{.Names}}' | grep -qx "$SSOS_CONTAINER"; then
    echo "==> Starting stopped container '$SSOS_CONTAINER'"
    docker start "$SSOS_CONTAINER" >/dev/null
    SSOS_E2E_MANAGED=1
    export SSOS_E2E_MANAGED=1
    return 0
  fi

  echo "==> Creating container '$SSOS_CONTAINER' from $SSOS_IMAGE"
  # shellcheck disable=SC2086
  docker run -d --name "$SSOS_CONTAINER" \
    -e "ROS_DOMAIN_ID=${SSOS_ROS_DOMAIN_ID}" \
    ${SSOS_DOCKER_RUN_EXTRA:-} \
    "$SSOS_IMAGE" sleep infinity
  SSOS_E2E_MANAGED=1
  export SSOS_E2E_MANAGED=1
}

ssos_start_headless() {
  local script="${1:-$SSOS_HEADLESS_SCRIPT}"
  echo "==> Starting headless stack in background: $script"
  docker exec -d "$SSOS_CONTAINER" bash -lc "
$(ssos_ros_env_snippet)
exec bash ${script}
"
}

ssos_teardown_container() {
  if [[ "${SSOS_KEEP_CONTAINER:-0}" == "1" ]]; then
    echo "==> Keeping container '$SSOS_CONTAINER' (--keep-container)"
    return 0
  fi
  if [[ "${SSOS_E2E_MANAGED:-0}" != "1" ]]; then
    return 0
  fi
  echo "==> Removing managed container '$SSOS_CONTAINER'"
  docker rm -f "$SSOS_CONTAINER" >/dev/null 2>&1 || true
}

ssos_quote_args() {
  local quoted=""
  local arg
  for arg in "$@"; do
    quoted+=" $(printf '%q' "$arg")"
  done
  printf '%s' "$quoted"
}

ssos_run_python_module() {
  local module="$1"
  shift

  if ! ssos_container_running; then
    echo "SSOS container '$SSOS_CONTAINER' is not running." >&2
    return 1
  fi

  local quoted_args
  quoted_args="$(ssos_quote_args "$@")"
  local tty_flag=""
  if [[ -t 0 ]]; then
    tty_flag="-it"
  fi

  # shellcheck disable=SC2086
  docker exec $tty_flag "$SSOS_CONTAINER" bash -lc "
set -eo pipefail
$(ssos_ros_env_snippet)
cd '${SSOS_CONTAINER_REPO}'
export PYTHONPATH='${SSOS_CONTAINER_REPO}/src:'\"\${PYTHONPATH:-}\"
python3 -m ${module}${quoted_args}
"
}

ssos_run_ea_loop() {
  ssos_sync_to_container || return 1
  local quoted_args
  quoted_args="$(ssos_quote_args "$@")"
  local tty_flag=""
  if [[ -t 0 ]]; then
    tty_flag="-it"
  fi

  # shellcheck disable=SC2086
  docker exec $tty_flag "$SSOS_CONTAINER" bash -lc "
set -eo pipefail
SSOS_CONTAINER_REPO='${SSOS_CONTAINER_REPO}' ea-loop${quoted_args}
"
}
