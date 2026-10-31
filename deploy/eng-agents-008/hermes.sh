#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace=${EA_WORKSPACE:-$(cd "$here/../../.." && pwd)}
export HERMES_HOME="$workspace/.runtime/hermes-home"
export CUDA_VISIBLE_DEVICES=${EA_GPU_UUID:-GPU-8a14a4ef-ac77-553a-206d-55efbf82617b}
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl JAX_PLATFORMS=cuda
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export MUJOCO_EGL_DEVICE_ID=${EA_EGL_DEVICE_ID:-6}
export PATH="$workspace/.runtime/node/bin:$workspace/.venv/bin:$HOME/.local/bin:$PATH"
export TERMINAL_CWD="$workspace"
repo=${EA_ENGINEERING_REPO:-$workspace/engineering_agents}
export EA_ENGINEERING_REPO="$repo"
export PATH="$repo/deploy/eng-agents-008/bin:$PATH"
if [[ -f "$repo/src/tools/engineering_skills/install.py" ]]; then
  PYTHONPATH="$repo/src" "$workspace/.venv/bin/python" -m tools.engineering_skills.install \
    --repo "$repo" --hermes-home "$HERMES_HOME" >/dev/null
fi
mkdir -p "$HERMES_HOME"
if [[ ! -f "$HERMES_HOME/config.yaml" ]]; then
  cp "$here/hermes-config.yaml" "$HERMES_HOME/config.yaml"
fi
curl --fail --silent --max-time 5 http://127.0.0.1:8016/health >/dev/null || {
  echo 'Local CUDA model server is unavailable. Start it with start-model.sh; no cloud/CPU fallback.' >&2
  exit 1
}
cd "$workspace"
exec env -u PYTHONPATH "$workspace/.runtime/hermes-agent/.venv/bin/hermes" "$@"
