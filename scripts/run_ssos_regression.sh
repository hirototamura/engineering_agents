#!/usr/bin/env bash
# SSOS container E2E regression — Tier 1 (pytest) + optional Tier 2 (live ROS2 smokes).
#
# Tier 1 only (default):
#   ./scripts/run_ssos_regression.sh
#
# Full regression (requires Docker + SSOS image):
#   SSOS_E2E=1 ./scripts/run_ssos_regression.sh
#
# Options:
#   --skip-pytest          Run Tier 2 only (implies SSOS_E2E=1)
#   --with-eps             Tier 2b: use ssos-headless.sh and run EPS smoke
#   --with-llm             Also run ea-loop with agents.mode=llm (needs Ollama)
#   --use-existing         Do not create/remove container; use SSOS_CONTAINER if running
#   --keep-container       Do not remove managed container on exit
#   --steps N              ea-loop simulation steps (default: 5)
#   --artifact-dir PATH    Report output directory (default: artifacts/ssos-regression/<ts>)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SSOS_REPO_ROOT="$REPO_ROOT"
SSOS_CONTAINER_EXPLICIT=0
if [[ -n "${SSOS_CONTAINER+x}" ]]; then
  SSOS_CONTAINER_EXPLICIT=1
fi
# shellcheck source=scripts/lib/ssos_docker.sh
source "$REPO_ROOT/scripts/lib/ssos_docker.sh"

RUN_PYTEST=1
RUN_TIER2=0
WITH_EPS=0
WITH_LLM=0
USE_EXISTING=0
LOOP_STEPS=5
ARTIFACT_DIR=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Tier 1 (always unless --skip-pytest):
  pytest -q

Tier 2 (when SSOS_E2E=1 or --skip-pytest):
  Start SSOS container, launch headless ECLSS, run smoke chain + ea-loop

Options:
  --skip-pytest       Skip Tier 1; run Tier 2 only
  --with-eps          Include EPS smoke (requires ssos-headless.sh)
  --with-llm          Run ea-loop in llm mode after labeled_rule_base
  --use-existing      Use running SSOS_CONTAINER; do not create/teardown
  --keep-container    Keep managed container after exit
  --steps N           ea-loop steps (default: 5)
  --artifact-dir DIR  Write JSON reports here
  -h, --help          Show this help

Environment:
  SSOS_E2E=1          Enable Tier 2
  SSOS_CONTAINER      Container name (default: ssos-regression-<pid> when managed)
  SSOS_IMAGE          Pre-built image (default: ghcr.io/space-station-os/space_station_os:latest)
  SSOS_HEADLESS_SCRIPT  ECLSS headless launcher (default: /root/ssos-eclss-headless.sh)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-pytest)
      RUN_PYTEST=0
      RUN_TIER2=1
      shift
      ;;
    --with-eps)
      WITH_EPS=1
      shift
      ;;
    --with-llm)
      WITH_LLM=1
      shift
      ;;
    --use-existing)
      USE_EXISTING=1
      shift
      ;;
    --keep-container)
      SSOS_KEEP_CONTAINER=1
      export SSOS_KEEP_CONTAINER
      shift
      ;;
    --steps)
      LOOP_STEPS="$2"
      shift 2
      ;;
    --artifact-dir)
      ARTIFACT_DIR="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${SSOS_E2E:-0}" == "1" ]]; then
  RUN_TIER2=1
fi

if [[ -z "$ARTIFACT_DIR" ]]; then
  ARTIFACT_DIR="$REPO_ROOT/artifacts/ssos-regression/$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$ARTIFACT_DIR"

run_tier1() {
  echo "==> Tier 1: pytest"
  cd "$REPO_ROOT"
  python3 -m pytest -q --ignore=tests/e2e 2>&1 | tee "$ARTIFACT_DIR/pytest.log"
}

run_smoke() {
  local label="$1"
  local module="$2"
  shift 2
  local container_json="/tmp/ea_regression/${label}.json"
  local host_json="$ARTIFACT_DIR/${label}.json"

  echo "==> Tier 2 smoke: $module"
  ssos_sync_to_container
  docker exec "$SSOS_CONTAINER" mkdir -p /tmp/ea_regression
  ssos_run_python_module "$module" --json-out "$container_json" "$@"
  docker cp "$SSOS_CONTAINER:$container_json" "$host_json"
}

copy_container_dir() {
  local container_path="$1"
  local host_path="$2"
  mkdir -p "$host_path"
  docker cp "$SSOS_CONTAINER:${container_path}/." "$host_path/"
}

run_tier2() {
  if ! ssos_docker_available; then
    echo "ERROR: Tier 2 requires docker." >&2
    exit 1
  fi

  local headless_script="$SSOS_HEADLESS_SCRIPT"
  if [[ "$WITH_EPS" -eq 1 ]]; then
    headless_script="$SSOS_HEADLESS_FULL_SCRIPT"
  fi

  if [[ "$USE_EXISTING" -eq 1 ]]; then
    if ! ssos_container_running; then
      echo "ERROR: --use-existing but container '$SSOS_CONTAINER' is not running." >&2
      exit 1
    fi
    echo "==> Tier 2: using existing container '$SSOS_CONTAINER'"
  else
    if [[ "$SSOS_CONTAINER_EXPLICIT" -eq 0 ]]; then
      SSOS_CONTAINER="ssos-regression-$$"
      export SSOS_CONTAINER
    fi
    ssos_start_managed_container
  fi

  cleanup() {
    ssos_teardown_container
  }
  if [[ "$USE_EXISTING" -eq 0 ]]; then
    trap cleanup EXIT
  fi

  if ! ssos_ros_graph_ready; then
    ssos_start_headless "$headless_script"
    ssos_wait_for_ros_graph
  else
    echo "==> ECLSS already running — skipping headless launch"
  fi

  ssos_sync_to_container

  run_smoke "01_ars" scripts.ssos_eclss_ars_smoke --wait-timeout 120
  run_smoke "02_1b" scripts.ssos_eclss_1b_smoke
  run_smoke "03_wrs" scripts.ssos_eclss_2_smoke
  run_smoke "04_graph_rewire" scripts.ssos_graph_rewire_smoke

  if [[ "$WITH_EPS" -eq 1 ]]; then
    run_smoke "05_eps" scripts.ssos_eps_smoke
  fi

  local loop_container_out="/tmp/ea_regression/06_ea_loop_labeled"
  local loop_host_out="$ARTIFACT_DIR/06_ea_loop_labeled"
  mkdir -p "$loop_host_out"
  echo "==> Tier 2 ea-loop: labeled_rule_base (--steps $LOOP_STEPS)"
  docker exec "$SSOS_CONTAINER" mkdir -p /tmp/ea_regression
  ssos_run_ea_loop \
    --backend ros2 \
    --agents-mode labeled_rule_base \
    --steps "$LOOP_STEPS" \
    --output-dir "$loop_container_out"
  copy_container_dir "$loop_container_out" "$loop_host_out"

  if [[ "$WITH_LLM" -eq 1 ]]; then
    local llm_container_out="/tmp/ea_regression/07_ea_loop_llm"
    local llm_host_out="$ARTIFACT_DIR/07_ea_loop_llm"
    mkdir -p "$llm_host_out"
    echo "==> Tier 2 ea-loop: llm (--steps $LOOP_STEPS)"
    ssos_run_ea_loop \
      --backend ros2 \
      --agents-mode llm \
      --steps "$LOOP_STEPS" \
      --output-dir "$llm_container_out"
    copy_container_dir "$llm_container_out" "$llm_host_out"
  fi

  echo "==> Tier 2 complete. Artifacts: $ARTIFACT_DIR"
}

main() {
  echo "Artifacts: $ARTIFACT_DIR"

  if [[ "$RUN_PYTEST" -eq 1 ]]; then
    run_tier1
  fi

  if [[ "$RUN_TIER2" -eq 1 ]]; then
    run_tier2
  else
    echo "Tier 2 skipped (set SSOS_E2E=1 to enable SSOS container regression)"
  fi
}

main
