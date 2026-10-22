#!/usr/bin/env bash
# User-space only: no sudo, Docker, kernel changes, or service interruptions.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
workspace=${EA_WORKSPACE:-$(cd "$here/../../.." && pwd)}
runtime="$workspace/.runtime"
build_root="$HOME/.local/share/eng-agents-008"
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || { echo 'Install uv 0.12.5 from astral-sh/uv first.' >&2; exit 1; }
mkdir -p "$runtime/logs" "$runtime/models" "$build_root"
if [[ ! -d "$runtime/hermes-agent" ]]; then
  git clone --branch v0.22.4 --depth 1 https://github.com/NousResearch/hermes-agent.git "$runtime/hermes-agent"
fi
[[ "$(git -C "$runtime/hermes-agent" rev-parse HEAD)" == 4d04303818b61bf3aa09278af48356315515965b ]]
(cd "$runtime/hermes-agent"; uv sync --frozen --python 3.14.7)
uv venv --allow-existing --python 3.12.14 "$workspace/.venv"
uv pip install --python "$workspace/.venv/bin/python" -r "$here/development-linux-py312.txt"
uv pip install --python "$workspace/.venv/bin/python" --no-deps -e "$workspace/engineering_agents" -e "$workspace/one-piece"
uv venv --allow-existing --python 3.11.16 "$runtime/graphics"
uv pip install --python "$runtime/graphics/bin/python" bpy==4.5.3

# Build under a path without spaces: CUDA compiler activation flags do not
# reliably quote spaces in environment prefixes. Keep the existing host stack intact.
if [[ ! -x "$runtime/micromamba/bin/micromamba" ]]; then
  mkdir -p "$runtime/micromamba"
  curl -fLsS https://micro.mamba.pm/api/micromamba/linux-64/2.9.0 |
    tar -xj -C "$runtime/micromamba" bin/micromamba
fi
if [[ ! -d "$build_root/cuda-build/conda-meta" ]]; then
  "$runtime/micromamba/bin/micromamba" create -y -p "$build_root/cuda-build" --file "$here/cuda-build-linux64.lock"
fi
if [[ ! -d "$build_root/llama-source" ]]; then
  git clone --depth 1 --branch b11819 https://github.com/ggml-org/llama.cpp.git "$build_root/llama-source"
fi
[[ "$(git -C "$build_root/llama-source" describe --tags --exact-match)" == b11819 ]]
"$runtime/micromamba/bin/micromamba" run -p "$build_root/cuda-build" cmake \
  -S "$build_root/llama-source" -B "$build_root/llama-source/build" -G Ninja \
  -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DGGML_NATIVE=OFF \
  -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF
"$runtime/micromamba/bin/micromamba" run -p "$build_root/cuda-build" cmake \
  --build "$build_root/llama-source/build" --target llama-server -j "${EA_BUILD_JOBS:-6}"
model="$runtime/models/Qwen3.8-27B-Q4_K_M.gguf"
expected=c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747
if [[ ! -f "$model" ]]; then
  curl -fL --retry 6 -C - \
    https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/resolve/a316ea527fde32c12487be7574e2db5ac2ad2a7e/Qwen3.8-27B-Q4_K_M.gguf \
    -o "$model.partial"
  printf '%s  %s\n' "$expected" "$model.partial" | sha256sum -c -
  mv "$model.partial" "$model"
fi
printf '%s  %s\n' "$expected" "$model" | sha256sum -c -
printf '\nRuntime ready. Start the model with bash %q\n' "$here/start-model.sh"
