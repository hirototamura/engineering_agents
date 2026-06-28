#!/usr/bin/env bash
# Shared helpers for scripts/ssos/mac/*.sh (sourced, not executed).

ssos_resolve_paths() {
  if [[ -n "${SSOS_REPO_ROOT:-}" ]]; then
    REPO_ROOT="$SSOS_REPO_ROOT"
    SSOS_SCRIPTS_DIR="${SSOS_SCRIPTS_DIR:-$REPO_ROOT/scripts/ssos}"
    return 0
  fi
  local caller_dir
  caller_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  if [[ "$(basename "$caller_dir")" == "mac" || "$(basename "$caller_dir")" == "linux" ]]; then
    SSOS_SCRIPTS_DIR="$(cd "${caller_dir}/.." && pwd)"
  else
    SSOS_SCRIPTS_DIR="$caller_dir"
  fi
  REPO_ROOT="$(cd "${SSOS_SCRIPTS_DIR}/../.." && pwd)"
}

ssos_define_volumes() {
  ssos_resolve_paths
  SSOS_VOLUMES=(
    -v "${SSOS_SCRIPTS_DIR}/ssos-container-setup.sh:/root/ssos-container-setup.sh:ro"
    -v "${SSOS_SCRIPTS_DIR}/ssos-eclss-headless.sh:/root/ssos-eclss-headless.sh:ro"
    -v "${SSOS_SCRIPTS_DIR}/ssos-headless.launch.py:/root/ssos-headless.launch.py:ro"
    -v "${SSOS_SCRIPTS_DIR}/ssos-eps.launch.py:/root/ssos-eps.launch.py:ro"
    -v "${REPO_ROOT}/src:/ea/src"
    -v "${REPO_ROOT}/src/experiments/results:/ea/results"
  )
}

ssos_ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker CLI not found. On Mac: brew install colima docker docker-compose" >&2
    exit 1
  fi

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  echo "Docker daemon is not running. Starting Colima..." >&2
  if ! command -v colima >/dev/null 2>&1; then
    echo "Start Docker Desktop or Colima, then re-run." >&2
    exit 1
  fi

  if [[ "$(uname -m)" == "arm64" ]]; then
    echo "==> Apple Silicon: arm64 VM + Rosetta (amd64 containers via --platform)" >&2
    colima start --cpu 4 --memory 8 --disk 60 --arch aarch64 --vm-type vz --vz-rosetta
  else
    colima start --cpu 4 --memory 8 --disk 60
  fi
}
