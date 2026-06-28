#!/usr/bin/env bash
# graph_rewire runtime E2E — SSOS container with headless ECLSS.
#
# Terminal 1 (host):
#   ~/dev/ssos/ssos-run.sh
#
# Terminal 2 (inside container):
#   bash /root/ssos-eclss-headless.sh
#
# Terminal 3 (host):
#   ./scripts/run_graph_rewire_e2e.sh
#
set -euo pipefail

CONTAINER="${SSOS_CONTAINER:-ssos}"
CONTAINER_REPO="${SSOS_CONTAINER_REPO:-/opt/engineering_agents}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

run_smoke() {
  local workdir="$1"
  shift
  cd "$workdir"
  PYTHONPATH="$workdir/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m scripts.ssos_graph_rewire_smoke "$@"
}

if command -v ros2 >/dev/null 2>&1; then
  run_smoke "$REPO_ROOT" "$@"
  exit $?
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ros2 CLI not found on host and docker is unavailable." >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "SSOS container '$CONTAINER' is not running." >&2
  echo "Start: ~/dev/ssos/ssos-run.sh" >&2
  echo "Then inside container: bash /root/ssos-eclss-headless.sh" >&2
  exit 1
fi

echo "==> Syncing src/ to $CONTAINER:$CONTAINER_REPO/src"
docker exec "$CONTAINER" mkdir -p "$CONTAINER_REPO"
docker cp "$REPO_ROOT/src/." "$CONTAINER:$CONTAINER_REPO/src/"

quoted_args=""
for arg in "$@"; do
  quoted_args+=" $(printf '%q' "$arg")"
done

echo "==> Running graph_rewire E2E smoke in container '$CONTAINER'"
if [ -t 0 ]; then
  docker exec -it "$CONTAINER" bash -lc "
  set -eo pipefail
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  set -u 2>/dev/null || true
  cd '$CONTAINER_REPO'
  PYTHONPATH='$CONTAINER_REPO/src:'\"\${PYTHONPATH:-}\" python3 -m scripts.ssos_graph_rewire_smoke${quoted_args}
"
else
  docker exec "$CONTAINER" bash -lc "
  set -eo pipefail
  set +u
  source /opt/ros/jazzy/setup.bash
  source ~/ssos_ws/install/setup.bash
  set -u 2>/dev/null || true
  cd '$CONTAINER_REPO'
  PYTHONPATH='$CONTAINER_REPO/src:'\"\${PYTHONPATH:-}\" python3 -m scripts.ssos_graph_rewire_smoke${quoted_args}
"
fi
