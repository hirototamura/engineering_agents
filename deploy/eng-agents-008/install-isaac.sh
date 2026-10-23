#!/usr/bin/env bash
# Isolated, pinned installation. Never changes the MuJoCo/MJX environment.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace=${EA_WORKSPACE:-$(cd "$here/../../.." && pwd)}
export PATH="$HOME/.local/bin:$PATH"
target="$workspace/.runtime/isaac"
command -v uv >/dev/null || { echo 'Install uv 0.12.5 first.' >&2; exit 1; }
if [[ -e "$target" ]]; then
  # Existing environments are verified, never silently replaced or upgraded.
  actual=$(mktemp)
  trap 'rm -f "$actual"' EXIT
  uv pip freeze --python "$target/bin/python" > "$actual"
  diff -u "$here/isaac-linux-py312.txt" "$actual"
  echo 'Existing Isaac environment matches the pinned package set.'
  exit 0
fi
uv venv --python 3.12.14 "$target"
# --no-deps is intentional: the complete frozen set carries NVIDIA's documented
# urllib3 override for the Isaac Lab / Isaac Sim metadata conflict. See ISAAC.md.
uv pip install --python "$target/bin/python" --no-deps \
  -r "$here/isaac-linux-py312.txt" \
  --extra-index-url https://pypi.nvidia.com \
  --extra-index-url https://download.pytorch.org/whl/cu130 \
  --index-strategy unsafe-best-match
echo 'Isaac packages installed. Accept the NVIDIA EULA before launching; see ISAAC.md.'
