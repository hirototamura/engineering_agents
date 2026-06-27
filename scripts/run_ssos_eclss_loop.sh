#!/usr/bin/env bash
# Run ssos_eclss_loop — delegates to ea run (host) or mock on host.
#
# Host ros2 (recommended — one command):
#   ea run ssos_eclss_loop --agents-mode labeled_rule_base
#   ./scripts/run_ssos_eclss_loop.sh --agents-mode labeled_rule_base   # same
#
# Host mock (no Docker):
#   ./scripts/run_ssos_eclss_loop.sh --mock --agents-mode labeled_rule_base
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options] [-- scenario args...]

Options:
  --mock          Run on this Mac with mock backend (no Docker)
  -h, --help      Show this help

Examples:
  $(basename "$0") --agents-mode labeled_rule_base
  $(basename "$0") --mock --agents-mode labeled_rule_base
  ea run ssos_eclss_loop --agents-mode labeled_rule_base
EOF
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
      echo "Deprecated: use volume mounts and 'ea run ssos_eclss_loop' instead." >&2
      exit 2
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

cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$mode" == "mock" ]]; then
  if ((${#main_args[@]})); then
    exec python3 -m tools.cli run ssos_eclss_loop --backend mock "${main_args[@]}"
  fi
  exec python3 -m tools.cli run ssos_eclss_loop --backend mock
fi

if ((${#main_args[@]})); then
  exec python3 -m tools.cli run ssos_eclss_loop "${main_args[@]}"
fi
exec python3 -m tools.cli run ssos_eclss_loop
