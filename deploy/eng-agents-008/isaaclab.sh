#!/usr/bin/env bash
# Run the isolated Isaac Lab environment on the reserved GPU, without CPU fallback.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace=${EA_WORKSPACE:-$(cd "$here/../../.." && pwd)}
python="$workspace/.runtime/isaac/bin/python"
[[ -x "$python" ]] || { echo 'Run install-isaac.sh first.' >&2; exit 1; }
[[ "${OMNI_KIT_ACCEPT_EULA:-}" == YES ]] || {
  echo 'After accepting the NVIDIA Omniverse license, export OMNI_KIT_ACCEPT_EULA=YES.' >&2; exit 1;
}
case "${1:-}" in
  train|play|zero_agent|random_agent) command=$1; shift ;;
  *) echo 'Usage: isaaclab.sh {train|play|zero_agent|random_agent} [Isaac Lab arguments]' >&2; exit 2 ;;
esac
export CUDA_VISIBLE_DEVICES=GPU-8a14a4ef-ac77-553a-206d-55efbf82617b
export HEADLESS=${HEADLESS:-1}
# CUDA visibility alone does not select the Vulkan renderer. Select it by CUDA
# identity too, so Kit maps the reserved card instead of physical GPU 0.
free_mib=$(nvidia-smi -i "$CUDA_VISIBLE_DEVICES" --query-gpu=memory.free --format=csv,noheader,nounits)
[[ "$free_mib" =~ ^[0-9]+$ ]] || { echo 'Cannot determine reserved GPU memory.' >&2; exit 1; }
if (( free_mib < 16000 )); then
  echo "GPU 6 has only $free_mib MiB free; need at least 16000 MiB. Check nvidia-smi." >&2
  echo 'If Hermes is using it, stop eng-agents-hermes-model.service before simulation and restart afterward.' >&2
  exit 1
fi
"$python" -c 'import torch; assert torch.cuda.is_available() and torch.cuda.device_count() == 1; print("Isaac CUDA:", torch.cuda.get_device_name(0))'
exec "$python" -m isaaclab "$command" "$@" --device cuda:0 \
  --kit_args='--/renderer/multiGpu/enabled=false --/renderer/multiGpu/activeCudaGpus=0,'
