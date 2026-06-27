#!/usr/bin/env bash
# In-container entry point for engineering_agents (mounted at /ea or synced legacy path).
#
# Usage (inside SSOS container):
#   ea-loop --agents-mode labeled_rule_base
#   ea-loop --backend mock --agents-mode llm
#
set -euo pipefail

REPO="${SSOS_CONTAINER_REPO:-/ea}"
SRC="${EA_MOUNT_SRC:-$REPO/src}"
RESULTS="${EA_MOUNT_RESULTS:-/ea/results}"

if [[ ! -d "$SRC/scenario" ]]; then
  echo "engineering_agents src not found at $SRC" >&2
  echo "Mount the repo src tree, for example:" >&2
  echo "  -v \"\$REPO_ROOT/src:/ea/src\"" >&2
  exit 1
fi

set +u
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
# shellcheck disable=SC1091
source ~/ssos_ws/install/setup.bash
set -u 2>/dev/null || true

_resolve_backend_kind() {
  local backend="${SSOS_ECLSS_BACKEND:-ros2}"
  local prev=""
  for arg in "$@"; do
    if [[ "$prev" == "--backend" ]]; then
      backend="$arg"
      break
    fi
    prev="$arg"
  done
  printf '%s' "$backend"
}

_preflight_ros2_graph() {
  local topic_count action_count
  topic_count="$(ros2 topic list 2>/dev/null | grep -c . || true)"
  action_count="$(ros2 action list 2>/dev/null | grep -c . || true)"
  if [[ "${topic_count:-0}" -eq 0 && "${action_count:-0}" -eq 0 ]]; then
    echo "ERROR: ros2 graph is empty — ECLSS headless is not running." >&2
    echo "From the host, run: ea run ssos_eclss_loop" >&2
    echo "Or start headless manually: bash /root/ssos-eclss-headless.sh" >&2
    exit 1
  fi
}

backend_kind="$(_resolve_backend_kind "$@")"
if [[ "$backend_kind" == "ros2" ]]; then
  _preflight_ros2_graph
fi

cd "$REPO"
export PYTHONPATH="$SRC${PYTHONPATH:+:$PYTHONPATH}"
export SSOS_ECLSS_BACKEND="${SSOS_ECLSS_BACKEND:-ros2}"
export EA_RESULTS_ROOT="${EA_RESULTS_ROOT:-$RESULTS}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
exec python3 -m scenario.ssos_eclss_loop.scenario_run "$@"
