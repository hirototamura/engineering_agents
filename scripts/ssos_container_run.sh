#!/usr/bin/env bash
# In-container entry point for engineering_agents (synced to /tmp/engineering_agents/run.sh).
#
# Prerequisite: ECLSS headless running — bash /root/ssos-eclss-headless.sh
#
# Usage (inside SSOS container):
#   ea-loop --agents-mode labeled_rule_base
#   ea-loop --backend ros2 --agents-mode labeled_rule_base --apply-proposals /path/design_proposals.json
#
set -euo pipefail

REPO="${SSOS_CONTAINER_REPO:-/tmp/engineering_agents}"
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

cd "$REPO"
export PYTHONPATH="$SRC${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m scenario.ssos_eclss_loop.scenario_run "$@"
