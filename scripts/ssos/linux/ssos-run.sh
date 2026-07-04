#!/usr/bin/env bash
# Space Station OS — interactive Docker shell (Linux).
#
# Mounts engineering_agents src/results and SSOS helper scripts into /root/.
# For host `ea run` (detached): use ssos-run-detached.sh instead.
set -euo pipefail

IMAGE="ghcr.io/space-station-os/space_station_os:latest"
PLATFORM="${SSOS_PLATFORM:-linux/amd64}"
CONTAINER_NAME="${SSOS_CONTAINER_NAME:-ssos}"

# shellcheck source=../_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../_lib.sh"
ssos_resolve_paths

stop_container() {
  if docker ps -q --filter "name=^${CONTAINER_NAME}$" | grep -q .; then
    echo
    echo "==> Stopping SSOS container (${CONTAINER_NAME})..."
    docker stop -t 5 "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi
}

trap stop_container INT TERM

echo "==> Space Station OS (engineering_agents + SSOS helpers)"
echo "    Repo:      ${REPO_ROOT}"
echo "    Scripts:   ${SSOS_SCRIPTS_DIR}"
echo

ssos_ensure_docker

echo "==> Pulling prebuilt image (platform: ${PLATFORM})..."
docker pull --platform "${PLATFORM}" "${IMAGE}"

if docker ps -aq --filter "name=^${CONTAINER_NAME}$" | grep -q .; then
  echo "==> Removing leftover container (${CONTAINER_NAME})..."
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

ssos_define_volumes

echo
echo "==> Starting SSOS container (${CONTAINER_NAME})..."
echo "    Leave shell:  type 'exit'"
echo "    ea run:       use ssos-run-detached.sh on the host instead of this script"
echo
docker run -it --rm --init --sig-proxy \
  --name "${CONTAINER_NAME}" \
  --platform "${PLATFORM}" \
  "${SSOS_VOLUMES[@]}" \
  "${IMAGE}" \
  bash /root/ssos-container-setup.sh
