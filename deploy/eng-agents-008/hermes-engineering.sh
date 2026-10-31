#!/usr/bin/env bash
# Hermes owns task planning/tool use; versioned EA tools own numerical results.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=${EA_ENGINEERING_REPO:-$(cd "$here/../.." && pwd)}
workspace=${EA_WORKSPACE:-$(cd "$repo/.." && pwd)}
export EA_ENGINEERING_REPO="$repo" EA_WORKSPACE="$workspace"
# Preserve the existing CUDA model, profile, approval prompts and endpoint.
exec bash "$here/hermes.sh" "$@"
