#!/usr/bin/env bash
# Phase 3: run SSOS EPS bridge smoke inside the SSOS Docker container.
#
# Prerequisite: SSOS headless stack running (solar + EPS + ECLSS)
#
#   ./scripts/run_ssos_eps_smoke.sh
#   ./scripts/run_ssos_eps_smoke.sh --json-out /tmp/eps_smoke.json
#
set -euo pipefail

CONTAINER="${SSOS_CONTAINER:-ssos}"
CONTAINER_REPO="${SSOS_CONTAINER_REPO:-/tmp/engineering_agents}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

run_smoke() {
  local workdir="$1"
  shift
  cd "$workdir"
  PYTHONPATH="$workdir/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m scripts.ssos_eps_smoke "$@"
}

if command -v ros2 >/dev/null 2>&1; then
  run_smoke "$REPO_ROOT" "$@"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ros2 CLI not found on host and docker is unavailable." >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "SSOS container '$CONTAINER' is not running." >&2
  exit 1
fi

echo "==> Syncing src/ to $CONTAINER:$CONTAINER_REPO/src"
docker exec "$CONTAINER" mkdir -p "$CONTAINER_REPO"
docker cp "$REPO_ROOT/src/." "$CONTAINER:$CONTAINER_REPO/src/"

quoted_args=""
for arg in "$@"; do
  quoted_args+=" $(printf '%q' "$arg")"
done

echo "==> Running Phase 3 EPS smoke in container '$CONTAINER'"
if [ -t 0 ]; then
  docker exec -it "$CONTAINER" bash -lc "
  set -eo pipefail
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  export ROS_DOMAIN_ID=\${ROS_DOMAIN_ID:-23}
  set -u 2>/dev/null || true
  cd '$CONTAINER_REPO'
  PYTHONPATH='$CONTAINER_REPO/src:'\"\${PYTHONPATH:-}\" python3 -m scripts.ssos_eps_smoke${quoted_args}
"
else
  docker exec "$CONTAINER" bash -lc "
  set -eo pipefail
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  export ROS_DOMAIN_ID=\${ROS_DOMAIN_ID:-23}
  set -u 2>/dev/null || true
  cd '$CONTAINER_REPO'
  PYTHONPATH='$CONTAINER_REPO/src:'\"\${PYTHONPATH:-}\" python3 -m scripts.ssos_eps_smoke${quoted_args}
"
fi
