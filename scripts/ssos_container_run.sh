#!/usr/bin/env bash
# In-container entry point for engineering_agents (ea-loop legacy).
#
# Layouts supported:
#   - Volume mount (CLI v3): /ea/src + /ea/results
#   - Sync install (main regression): /opt/engineering_agents/src
#
# Prerequisite: ECLSS headless running — bash /root/ssos-eclss-headless.sh
# Host `ea run ssos_eclss_loop` restarts headless automatically.
#
# Usage (inside SSOS container):
#   ea-loop --agents-mode labeled_rule_base
#   ea-loop --backend mock --agents-mode llm
#
set -euo pipefail

REPO="${SSOS_CONTAINER_REPO:-/ea}"
SRC="${EA_MOUNT_SRC:-$REPO/src}"
RESULTS="${EA_MOUNT_RESULTS:-/ea/results}"

if [[ ! -d "$SRC/scenario" && -d /opt/engineering_agents/src/scenario ]]; then
  REPO="/opt/engineering_agents"
  SRC="$REPO/src"
fi

if [[ ! -d "$SRC/scenario" ]]; then
  echo "engineering_agents src not found at $SRC" >&2
  echo "Mount the repo src tree, for example:" >&2
  echo "  -v \"\$REPO_ROOT/src:/ea/src\"" >&2
  echo "Or from host repo root (legacy sync):" >&2
  echo "  ./scripts/run_ssos_regression.sh --sync-only" >&2
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
  local topics actions
  topics="$(ros2 topic list 2>/dev/null || true)"
  actions="$(ros2 action list 2>/dev/null || true)"
  if ! printf '%s\n' "$topics" | grep -qE '(^|/)co2_storage([[:space:]]|$)'; then
    echo "ERROR: ECLSS headless is not running (missing /co2_storage)." >&2
    echo "From the host: ea run ssos_eclss_loop … (restarts headless automatically)" >&2
    echo "Inside the container: bash /root/ssos-eclss-headless.sh" >&2
    echo "  # legacy sync layout: /opt/engineering_agents/ssos_eclss_headless.sh" >&2
    exit 1
  fi
  if ! printf '%s\n' "$actions" | grep -qE '(^|/)air_revitalisation([[:space:]]|$)'; then
    echo "ERROR: ECLSS headless is not running (missing air_revitalisation action)." >&2
    echo "From the host: ea run ssos_eclss_loop … (restarts headless automatically)" >&2
    echo "Inside the container: bash /root/ssos-eclss-headless.sh" >&2
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
