#!/usr/bin/env bash
# Shared SSOS Docker helpers for smoke tests and E2E regression.
#
# Volume-mount layout (same as scripts/ssos/*/ssos-run-detached.sh):
#   src     -> /ea/src
#   results -> /ea/results
#   scripts/ssos/* -> /root/
#
# Source from other scripts:
#   # shellcheck source=scripts/lib/ssos_docker.sh
#   source "$REPO_ROOT/scripts/lib/ssos_docker.sh"
#
# CI self-hosted bind mounts: the Docker daemon must see the host path passed to
# -v. Bare-metal runners (label ssos) are fine. Docker-in-Docker setups need the
# checkout under a volume shared with the dind sidecar (e.g. RUNNER_WORKSPACE).

SSOS_CONTAINER="${SSOS_CONTAINER:-ssos}"
SSOS_CONTAINER_REPO="${SSOS_CONTAINER_REPO:-/ea}"
SSOS_MOUNT_SRC="${EA_MOUNT_SRC:-/ea/src}"
SSOS_MOUNT_RESULTS="${EA_MOUNT_RESULTS:-/ea/results}"
SSOS_IMAGE="${SSOS_IMAGE:-ghcr.io/space-station-os/space_station_os:latest}"
SSOS_PLATFORM="${SSOS_PLATFORM:-linux/amd64}"
SSOS_HEADLESS_SCRIPT="${SSOS_HEADLESS_SCRIPT:-/root/ssos-eclss-headless.sh}"
SSOS_HEADLESS_FULL_SCRIPT="${SSOS_HEADLESS_FULL_SCRIPT:-/root/ssos-eclss-headless.sh}"
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

ssos_load_volume_defs() {
  local repo_root
  repo_root="$(ssos_repo_root)"
  export SSOS_REPO_ROOT="$repo_root"
  # shellcheck source=scripts/ssos/_lib.sh
  source "$repo_root/scripts/ssos/_lib.sh"
  ssos_resolve_paths
  ssos_define_volumes
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

ssos_verify_container_mounts() {
  local label="${1:-}"

  if ! ssos_docker_available; then
    echo "docker not found." >&2
    return 1
  fi
  if ! ssos_container_running; then
    echo "SSOS container '$SSOS_CONTAINER' is not running." >&2
    return 1
  fi

  if [[ "$label" != "quiet" ]]; then
    echo "==> Verifying SSOS volume mounts in '$SSOS_CONTAINER'"
  fi

  if ! docker exec "$SSOS_CONTAINER" test -d "$SSOS_MOUNT_SRC/scenario/ssos_eclss_loop"; then
    echo "ERROR: Missing mount $SSOS_MOUNT_SRC (expected repo src at /ea/src)." >&2
    echo "Recreate with: ./scripts/ssos/mac/ssos-run-detached.sh or regression managed container." >&2
    return 1
  fi
  if ! docker exec "$SSOS_CONTAINER" test -d "$SSOS_MOUNT_RESULTS"; then
    echo "ERROR: Missing mount $SSOS_MOUNT_RESULTS" >&2
    return 1
  fi
  if ! docker exec "$SSOS_CONTAINER" test -f /root/ssos-eclss-headless.sh; then
    echo "ERROR: Missing /root/ssos-eclss-headless.sh (mount scripts/ssos/*)." >&2
    return 1
  fi
  if ! docker exec "$SSOS_CONTAINER" test -f /root/ssos-headless.launch.py; then
    echo "ERROR: Missing /root/ssos-headless.launch.py (mount scripts/ssos/*)." >&2
    return 1
  fi

  if [[ "$label" != "quiet" ]]; then
    echo "    $SSOS_MOUNT_SRC OK"
    echo "    $SSOS_MOUNT_RESULTS OK"
    echo "    /root/ssos-eclss-headless.sh OK"
  fi
  return 0
}

# Back-compat name: sync is replaced by bind-mount verify (no docker cp).
ssos_sync_to_container() {
  ssos_verify_container_mounts
}

ssos_ros_graph_counts() {
  docker exec "$SSOS_CONTAINER" bash -lc "
$(ssos_ros_env_snippet)
topics=\$(ros2 topic list 2>/dev/null | grep -c . || true)
actions=\$(ros2 action list 2>/dev/null | grep -c . || true)
printf '%s %s' \"\${topics:-0}\" \"\${actions:-0}\"
"
}

ssos_eclss_graph_probe() {
  docker exec "$SSOS_CONTAINER" bash -lc "
$(ssos_ros_env_snippet)
topics=\$(ros2 topic list 2>/dev/null || true)
actions=\$(ros2 action list 2>/dev/null || true)
has_co2=0
has_ars_diag=0
has_ars_action=0
printf '%s\n' \"\$topics\" | grep -qE '(^|/)co2_storage([[:space:]]|$)' && has_co2=1 || true
printf '%s\n' \"\$topics\" | grep -qE '(^|/)ars/diagnostics([[:space:]]|$)' && has_ars_diag=1 || true
printf '%s\n' \"\$actions\" | grep -qE '(^|/)air_revitalisation([[:space:]]|$)' && has_ars_action=1 || true
printf '%s %s %s' \"\$has_co2\" \"\$has_ars_diag\" \"\$has_ars_action\"
"
}

ssos_ros_graph_ready() {
  local has_co2 has_ars_diag has_ars_action
  read -r has_co2 has_ars_diag has_ars_action <<< "$(ssos_eclss_graph_probe)"
  [[ "${has_co2:-0}" == "1" && "${has_ars_diag:-0}" == "1" && "${has_ars_action:-0}" == "1" ]]
}

ssos_wait_for_ros_graph() {
  local deadline=$((SECONDS + SSOS_GRAPH_WAIT_TIMEOUT_S))
  local has_co2 has_ars_diag has_ars_action topic_count action_count

  while (( SECONDS < deadline )); do
    if ssos_ros_graph_ready; then
      read -r topic_count action_count <<< "$(ssos_ros_graph_counts)"
      echo "==> ECLSS ROS graph ready (${topic_count} topics, ${action_count} actions)"
      return 0
    fi
    read -r has_co2 has_ars_diag has_ars_action <<< "$(ssos_eclss_graph_probe)"
    echo "==> Waiting for ECLSS (co2_storage=${has_co2} ars/diagnostics=${has_ars_diag} air_revitalisation=${has_ars_action}; ${SSOS_GRAPH_POLL_INTERVAL_S}s poll)..."
    sleep "$SSOS_GRAPH_POLL_INTERVAL_S"
  done

  echo "ERROR: ECLSS interfaces still missing after ${SSOS_GRAPH_WAIT_TIMEOUT_S}s" >&2
  echo "Headless script: ${SSOS_HEADLESS_SCRIPT:-<unset>}" >&2
  return 1
}

ssos_bootstrap_container() {
  if docker exec "$SSOS_CONTAINER" test -f /root/entry-point.sh 2>/dev/null; then
    if ! docker exec "$SSOS_CONTAINER" bash -lc 'command -v tmux >/dev/null && tmux has-session -t discovery 2>/dev/null'; then
      echo "==> Bootstrapping container (Fast DDS discovery)"
      docker exec -d "$SSOS_CONTAINER" bash /root/entry-point.sh
      sleep 2
    fi
  fi
}

ssos_resolve_headless_launcher() {
  local script="${1:-$SSOS_HEADLESS_SCRIPT}"

  if docker exec "$SSOS_CONTAINER" test -f "$script" 2>/dev/null; then
    printf '%s\n' "$script"
    return 0
  fi

  echo "ERROR: Headless script not mounted at $script" >&2
  echo "Recreate the container with scripts/ssos/*/ssos-run-detached.sh volume mounts." >&2
  return 1
}

ssos_start_managed_container() {
  if ! ssos_docker_available; then
    echo "docker not found." >&2
    return 1
  fi

  if ssos_container_running; then
    if ssos_verify_container_mounts quiet; then
      echo "==> Using existing container '$SSOS_CONTAINER' (mounts OK)"
      return 0
    fi
    echo "==> Container '$SSOS_CONTAINER' is running but mounts are incomplete — recreating" >&2
    docker rm -f "$SSOS_CONTAINER" >/dev/null 2>&1 || true
  elif docker ps -a --format '{{.Names}}' | grep -qx "$SSOS_CONTAINER"; then
    docker start "$SSOS_CONTAINER" >/dev/null
    if ssos_verify_container_mounts quiet; then
      echo "==> Started existing container '$SSOS_CONTAINER' (mounts OK)"
      SSOS_E2E_MANAGED=1
      export SSOS_E2E_MANAGED=1
      ssos_bootstrap_container
      return 0
    fi
    echo "==> Stopped container '$SSOS_CONTAINER' lacks mounts — recreating" >&2
    docker rm -f "$SSOS_CONTAINER" >/dev/null 2>&1 || true
  fi

  ssos_load_volume_defs
  echo "==> Creating container '$SSOS_CONTAINER' from $SSOS_IMAGE (platform: $SSOS_PLATFORM)"
  # shellcheck disable=SC2086
  docker run -d --init --name "$SSOS_CONTAINER" \
    --platform "$SSOS_PLATFORM" \
    -e "ROS_DOMAIN_ID=${SSOS_ROS_DOMAIN_ID}" \
    -e SSOS_CONTAINER_DETACHED=1 \
    "${SSOS_VOLUMES[@]}" \
    ${SSOS_DOCKER_RUN_EXTRA:-} \
    "$SSOS_IMAGE" sleep infinity
  SSOS_E2E_MANAGED=1
  export SSOS_E2E_MANAGED=1
  ssos_bootstrap_container
  ssos_verify_container_mounts
}

ssos_start_headless() {
  local script="${1:-$SSOS_HEADLESS_SCRIPT}"
  local launcher
  if ! launcher="$(ssos_resolve_headless_launcher "$script")"; then
    return 1
  fi
  echo "==> Starting headless stack in background: $launcher"
  docker exec -d "$SSOS_CONTAINER" bash -lc "
$(ssos_ros_env_snippet)
exec bash $(printf '%q' "$launcher")
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
export PYTHONPATH='${SSOS_MOUNT_SRC}:'\"\${PYTHONPATH:-}\"
export EA_RUN_IN_CONTAINER=1
python3 -m ${module}${quoted_args}
"
}

_ssos_write_job_spec() {
  local job_path="$1"
  shift
  local backend="ros2" agents_mode="labeled_rule_base" steps="" output_dir=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --backend)
        backend="$2"
        shift 2
        ;;
      --agents-mode)
        agents_mode="$2"
        shift 2
        ;;
      --steps)
        steps="$2"
        shift 2
        ;;
      --output-dir)
        output_dir="$2"
        shift 2
        ;;
      *)
        echo "Unknown scenario job arg: $1" >&2
        return 1
        ;;
    esac
  done

  local repo_root
  repo_root="$(ssos_repo_root)"
  PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
from pathlib import Path
from scenario.jobs.spec import RunSpec

overrides = {
    'backend': {'kind': '$backend'},
    'agents': {'mode': '$agents_mode'},
}
steps = '$steps'
if steps:
    overrides['simulation'] = {'steps': int(steps)}
output_dir = '$output_dir'
RunSpec(
    scenario='ssos_eclss_loop',
    overrides=overrides,
    output_dir=Path(output_dir) if output_dir else None,
    recreate_output=True,
).write_json(Path('$job_path'))
"
}

ssos_run_scenario_job() {
  ssos_sync_to_container || return 1

  local job_host job_container="/tmp/ea-regression-job-$$.json"
  job_host="$(mktemp "${TMPDIR:-/tmp}/ea-job.XXXXXX.json")"
  _ssos_write_job_spec "$job_host" "$@" || return 1

  docker cp "$job_host" "$SSOS_CONTAINER:$job_container"
  rm -f "$job_host"

  local tty_flag=""
  if [[ -t 0 ]]; then
    tty_flag="-it"
  fi

  # shellcheck disable=SC2086
  docker exec $tty_flag "$SSOS_CONTAINER" bash -lc "
set -eo pipefail
$(ssos_ros_env_snippet)
cd '${SSOS_CONTAINER_REPO}'
export PYTHONPATH='${SSOS_MOUNT_SRC}:'\"\${PYTHONPATH:-}\"
export SSOS_ECLSS_BACKEND=ros2
export EA_RESULTS_ROOT='${SSOS_MOUNT_RESULTS}'
export EA_RUN_IN_CONTAINER=1
export OLLAMA_BASE_URL=\${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
python3 -m scenario.jobs '$job_container'
rc=\$?
rm -f '$job_container'
exit \$rc
"
}

# Deprecated alias — use ssos_run_scenario_job.
ssos_run_ea_loop() {
  ssos_run_scenario_job "$@"
}
