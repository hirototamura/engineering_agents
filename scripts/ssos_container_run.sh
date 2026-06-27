#!/usr/bin/env bash
# In-container entry point for engineering_agents (synced to /opt/engineering_agents/run.sh).
#
# Prerequisite: ECLSS headless running — bash /root/ssos-eclss-headless.sh
#
# Usage (inside SSOS container):
#   ea-loop --agents-mode labeled_rule_base          # backend defaults to ros2
#   ea-loop --agents-mode llm                        # ros2 + host Ollama (host.docker.internal)
#   ea-loop --backend mock --agents-mode llm         # mock backend override
#   ea-loop --backend ros2 --agents-mode labeled_rule_base --apply-proposals /path/design_proposals.json
#
set -euo pipefail

REPO="${SSOS_CONTAINER_REPO:-/opt/engineering_agents}"
SRC="$REPO/src"

if [[ ! -d "$SRC/scenario" ]]; then
  echo "engineering_agents src not found at $SRC" >&2
  echo "From host repo root, run once:" >&2
  echo "  ./scripts/run_ssos_eclss_loop.sh --sync-only" >&2
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
    echo "In another terminal inside this container, run:" >&2
    echo "  /opt/engineering_agents/ssos_eclss_headless.sh" >&2
    echo "  # or: bash /root/ssos-eclss-headless.sh" >&2
    echo "Then retry ea-loop." >&2
    exit 1
  fi
  if ! printf '%s\n' "$actions" | grep -qE '(^|/)air_revitalisation([[:space:]]|$)'; then
    echo "ERROR: ECLSS headless is not running (missing air_revitalisation action)." >&2
    echo "In another terminal inside this container, run:" >&2
    echo "  /opt/engineering_agents/ssos_eclss_headless.sh" >&2
    echo "Then retry ea-loop." >&2
    exit 1
  fi
}

backend_kind="$(_resolve_backend_kind "$@")"
if [[ "$backend_kind" == "ros2" ]]; then
  _preflight_ros2_graph
fi

cd "$REPO"
export PYTHONPATH="$SRC${PYTHONPATH:+:$PYTHONPATH}"
# In-container default: talk to SSOS ECLSS via DDS (override with --backend mock).
export SSOS_ECLSS_BACKEND="${SSOS_ECLSS_BACKEND:-ros2}"
# Mac Docker: Ollama runs on the host — localhost inside the container is wrong.
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}"
exec python3 -m scenario.ssos_eclss_loop.scenario_run "$@"
