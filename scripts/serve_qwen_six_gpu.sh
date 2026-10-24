#!/usr/bin/env bash
# Six inference GPUs: three independent replicas, two tensor-parallel GPUs each.
# MJX uses the other two GPUs. Native MuJoCo runs on CPUs.
set -euo pipefail
ea_vllm_venv="${EA_VLLM_VENV:-/home/one-piece/.venv}"
export HF_HOME="${HF_HOME:-/home/one-piece/huggingface}"
export HF_HUB_OFFLINE=1
export CUDA_HOME="${CUDA_HOME:-$ea_vllm_venv/lib/python3.11/site-packages/nvidia/cu13}"
export PATH="$ea_vllm_venv/bin:$CUDA_HOME/bin:$PATH"
export LIBRARY_PATH="$CUDA_HOME/lib:$CUDA_HOME/lib/stubs${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="$CUDA_HOME/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_VISIBLE_DEVICES="${EA_LLM_GPU_IDS:-0,1,2,3,4,5}"
export EA_MJX_GPU_IDS="${EA_MJX_GPU_IDS:-6,7}"
export NCCL_P2P_DISABLE=1
export VLLM_MODEL_REVISION="${VLLM_MODEL_REVISION:?Pin the cached model revision before launch}"
"$ea_vllm_venv/bin/python" - <<'PY'
import os
def ids(name):
    value=os.environ[name].split(',')
    if any(not v.isdigit() for v in value) or len(set(value))!=len(value):
        raise SystemExit('Invalid physical device list: '+name)
    return set(map(int,value))
llm,simulation=ids('CUDA_VISIBLE_DEVICES'),ids('EA_MJX_GPU_IDS')
if len(llm)!=6 or len(simulation)!=2 or llm & simulation:
    raise SystemExit('Require six inference GPUs and two disjoint MJX GPUs')
PY
exec "$ea_vllm_venv/bin/vllm" serve orcarouter/Qwen3.8-27B-Uncensored-FP8 \
  --revision "$VLLM_MODEL_REVISION" \
  --host "${VLLM_HOST:-0.0.0.0}" --port "${VLLM_PORT:-8001}" \
  --served-model-name qwen3.8-27b-uncensored \
  --tensor-parallel-size 2 --data-parallel-size 3 \
  --language-model-only --kv-cache-dtype fp8 \
  --max-model-len 32768 --max-num-seqs 32 --gpu-memory-utilization 0.90 \
  --disable-custom-all-reduce --enable-prefix-caching --enable-chunked-prefill \
  --trust-remote-code --reasoning-parser qwen3 \
  --speculative-config '{"method":"mtp","num_speculative_tokens":2}' \
  --default-chat-template-kwargs '{"enable_thinking": true}'
