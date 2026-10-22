#!/usr/bin/env bash
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace=${EA_WORKSPACE:-$(cd "$here/../../.." && pwd)}
runtime="$workspace/.runtime"
model="$runtime/models/Qwen3.8-27B-Q4_K_M.gguf"
export CUDA_VISIBLE_DEVICES=${EA_GPU_UUID:-GPU-8a14a4ef-ac77-553a-206d-55efbf82617b}
export LD_LIBRARY_PATH="$HOME/.local/share/eng-agents-008/cuda-build/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
gpu_free=$(nvidia-smi -i "$CUDA_VISIBLE_DEVICES" --query-gpu=memory.free --format=csv,noheader,nounits)
[[ "$gpu_free" -ge 21000 ]] || { echo 'Selected GPU needs at least 21000 MiB free; existing jobs are preserved.' >&2; exit 1; }
printf '%s  %s\n' c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747 "$model" | sha256sum -c -
exec "$HOME/.local/share/eng-agents-008/llama-source/build/bin/llama-server" \
  --model "$model" --alias qwen3.8-27b-q4-k-m \
  --host 127.0.0.1 --port 8016 --n-gpu-layers 999 --split-mode none \
  --device CUDA0 --fit off --ctx-size 32768 --parallel 1 --flash-attn on --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0
