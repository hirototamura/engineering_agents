#!/usr/bin/env bash
# Create a persistent SSOS container for host `ea run ssos_eclss_loop` (Linux).
#
# - Mounts engineering_agents src/results and SSOS helper scripts
# - Runs Fast DDS discovery setup once, then sleeps (detached)
# - ea run restarts headless via /root/ssos-eclss-headless.sh automatically
set -euo pipefail

IMAGE="ghcr.io/space-station-os/space_station_os:latest"
PLATFORM="${SSOS_PLATFORM:-linux/amd64}"
CONTAINER_NAME="${SSOS_CONTAINER_NAME:-ssos}"

# shellcheck source=../_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../_lib.sh"
ssos_resolve_paths

echo "==> SSOS detached container (for ea run)"
echo "    Repo:      ${REPO_ROOT}"
echo "    Container: ${CONTAINER_NAME}"
echo

ssos_ensure_docker

echo "==> Pulling prebuilt image (platform: ${PLATFORM})..."
docker pull --platform "${PLATFORM}" "${IMAGE}"

docker stop "${CONTAINER_NAME}" 2>/dev/null || true
docker rm "${CONTAINER_NAME}" 2>/dev/null || true

ssos_define_volumes

echo "==> Creating detached container..."
docker run -d --init \
  --name "${CONTAINER_NAME}" \
  --platform "${PLATFORM}" \
  "${SSOS_VOLUMES[@]}" \
  -e SSOS_CONTAINER_DETACHED=1 \
  "${IMAGE}" \
  bash -lc 'bash /root/ssos-container-setup.sh; exec sleep infinity'

echo
echo "==> Verifying mounts..."
docker exec "${CONTAINER_NAME}" test -d /ea/src/scenario/ssos_eclss_loop
docker exec "${CONTAINER_NAME}" test -f /root/ssos-eclss-headless.sh
docker exec "${CONTAINER_NAME}" test -f /root/ssos-headless.launch.py
echo "    src mount OK"
echo "    headless helpers OK"
echo
echo "Next (on the host, not inside the container):"
echo "  cd \"${REPO_ROOT}\""
echo "  source .venv/bin/activate   # if needed"
echo "  ea run ssos_eclss_loop --agents-mode labeled_rule_base --steps 50"
echo
echo "If stopped later: docker start ${CONTAINER_NAME}"
