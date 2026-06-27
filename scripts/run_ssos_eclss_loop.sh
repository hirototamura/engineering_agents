#!/usr/bin/env bash
# Run ssos_eclss_loop inside the SSOS Docker container (sync src + exec).
#
# Host mock (no Docker / no ROS2):
#   ./scripts/run_ssos_eclss_loop.sh --mock --agents-mode labeled_rule_base
#
# Container ros2 (recommended — one command from host):
#   ./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base
#
# Enter container first, then one command inside:
#   docker exec -it ssos bash
#   ea-loop --agents-mode labeled_rule_base
#
# Prerequisite: ECLSS headless in container (terminal 1):
#   bash /root/ssos-eclss-headless.sh
#
set -euo pipefail

CONTAINER="${SSOS_CONTAINER:-ssos}"
CONTAINER_REPO="${SSOS_CONTAINER_REPO:-/opt/engineering_agents}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options] [-- scenario_run args...]

Options:
  --mock          Run on this Mac with mock backend (no Docker)
  --sync-only     Sync src/ into container; print in-container command
  --no-run        Sync only (alias for --sync-only)
  -h, --help      Show this help

Examples:
  $(basename "$0") --mock --agents-mode labeled_rule_base
  $(basename "$0") --agents-mode labeled_rule_base
  $(basename "$0") --sync-only
  # inside container after sync:
  ea-loop --agents-mode labeled_rule_base
EOF
}

sync_to_container() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found." >&2
    exit 1
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "SSOS container '$CONTAINER' is not running." >&2
    exit 1
  fi

  echo "==> Syncing src/ to $CONTAINER:$CONTAINER_REPO/src"
  docker exec "$CONTAINER" mkdir -p "$CONTAINER_REPO"
  docker cp "$REPO_ROOT/src/." "$CONTAINER:$CONTAINER_REPO/src/"

  echo "==> Installing in-container runner at $CONTAINER_REPO/run.sh and /usr/local/bin/ea-loop"
  docker cp "$REPO_ROOT/scripts/ssos_container_run.sh" "$CONTAINER:$CONTAINER_REPO/run.sh"
  docker exec "$CONTAINER" chmod +x "$CONTAINER_REPO/run.sh"
  docker exec "$CONTAINER" ln -sf "$CONTAINER_REPO/run.sh" /usr/local/bin/ea-loop
}

run_in_container() {
  local quoted_args=""
  for arg in "$@"; do
    quoted_args+=" $(printf '%q' "$arg")"
  done

  sync_to_container

  if [ $# -eq 0 ]; then
    set -- --backend ros2 --agents-mode labeled_rule_base
    quoted_args=" --backend ros2 --agents-mode labeled_rule_base"
  fi

  # Ensure ros2 when caller passes only --agents-mode (ea-loop defaults via SSOS_ECLSS_BACKEND too).
  has_backend=0
  for arg in "$@"; do
    if [ "$arg" = "--backend" ]; then
      has_backend=1
      break
    fi
  done
  if [ "$has_backend" -eq 0 ]; then
    set -- --backend ros2 "$@"
    quoted_args=" --backend ros2${quoted_args}"
  fi

  echo "==> Running ssos_eclss_loop in '$CONTAINER'"
  if [ -t 0 ]; then
    docker exec -it "$CONTAINER" bash -lc "SSOS_CONTAINER_REPO='$CONTAINER_REPO' ea-loop${quoted_args}"
  else
    docker exec "$CONTAINER" bash -lc "SSOS_CONTAINER_REPO='$CONTAINER_REPO' ea-loop${quoted_args}"
  fi
}

run_mock_on_host() {
  cd "$REPO_ROOT"
  export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
  if [ $# -eq 0 ]; then
    set -- --backend mock --agents-mode labeled_rule_base
  fi
  exec python3 -m scenario.ssos_eclss_loop.scenario_run "$@"
}

main_args=()
mode="container"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mock)
      mode="mock"
      shift
      ;;
    --sync-only | --no-run)
      mode="sync"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --)
      shift
      main_args+=("$@")
      break
      ;;
    *)
      main_args+=("$1")
      shift
      ;;
  esac
done

case "$mode" in
  mock)
    if ((${#main_args[@]})); then
      run_mock_on_host "${main_args[@]}"
    else
      run_mock_on_host
    fi
    ;;
  sync)
    sync_to_container
    echo
    echo "Inside container, run:"
    echo "  ea-loop --agents-mode labeled_rule_base   # backend defaults to ros2"
    echo "  ea-loop --agents-mode llm                 # ros2 + host Ollama"
    echo "  ea-loop --backend mock --agents-mode llm  # mock override"
    echo
    echo "Optional args: --apply-proposals /path/design_proposals.json"
    ;;
  container)
    if ((${#main_args[@]})); then
      run_in_container "${main_args[@]}"
    else
      run_in_container
    fi
    ;;
esac
