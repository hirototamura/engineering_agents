#!/usr/bin/env bash
# Explicit bounded design campaign; never edits an adopted baseline.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
store_path="${1:?Usage: run_cube_gpu_memory.sh PROJECT_STORE OUTPUT [SEED_RUN ...]}"
output_dir="${2:?An empty output directory is required}"
shift 2
seed_runs=("$@")
iterations="${EA_ITERATIONS:-10}"
candidate_budget="${EA_MAX_CANDIDATES:-$((iterations * 4))}"
stagnation_budget="${EA_STAGNATION_ROUNDS:-$iterations}"
ea_python="${EA_PYTHON:-python3}"
ea_site_packages="${EA_SHARED_SITE_PACKAGES:-}"
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export EA_MJX_GPU_IDS="${EA_MJX_GPU_IDS:-0,1,2,3,4,5}"
export EA_LLM_TRACE_DIR="$output_dir/llm-trace"
export VLLM_MAX_MODEL_LEN=32768 VLLM_API_TIMEOUT=600
export VLLM_TOKENIZE_PREFLIGHT=true
onepiece_source="$store_path/src"
if [[ ! -d "$onepiece_source/onepiece" ]]; then
  onepiece_source="$(cd "$store_path/../../.." && pwd)/src"
fi
export PYTHONPATH="$repo_root/src:$onepiece_source${PYTHONPATH:+:$PYTHONPATH}"
if [[ -n "$ea_site_packages" ]]; then export EA_SHARED_SITE_PACKAGES="$ea_site_packages"; fi
execution_dir="${output_dir}.execution"
mkdir -p "$execution_dir"
if [[ -e "$output_dir" ]]; then
  echo "Use a new output directory; existing evidence is preserved." >&2
  exit 2
fi
override_file="$execution_dir/overrides.json"
"$ea_python" -c 'import json,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"iteration":{"proposal_retries":3},"memory":{"enabled":True,"seed_runs":[p for p in sys.argv[2:] if p]}},ensure_ascii=False,indent=2))' "$override_file" "${seed_runs[@]}"
command=("$ea_python" "$repo_root/scripts/run_with_site_packages.py" -m tools.cli run balancing_cube
  --backend mjx_gpu --design-mode llm --iterate "$iterations"
  --llm-provider vllm --llm-model qwen3.8-27b-uncensored
  --set agents.llm.base_url=http://127.0.0.1:8001/v1
  --set agents.llm.temperature=0.3 --set agents.llm.max_tokens=3072
  --set agents.llm.think=true --set agents.llm.thinking_token_budget=2048
  --set "ssot.path=$store_path" --set ssot.snapshot_revision=fixed-dt-mvp-2
  --set "iteration.max_candidates=$candidate_budget" --set iteration.max_wall_s=7200
  --set "iteration.stagnation_rounds=$stagnation_budget" --override-file "$override_file" --json
  --output-dir "$output_dir")
"$ea_python" -c 'import json,sys,datetime; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"started_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"command":sys.argv[2:],"shared_site_packages":sys.argv[2] or None,"llm":{"provider":"vllm","model":"qwen3.8-27b-uncensored","endpoint":"http://127.0.0.1:8001/v1","temperature":0.3,"max_tokens":3072,"thinking_token_budget":2048,"think":True,"prompt_fit_method":"server_tokenizer_no_truncation"},"gpu_assignment":{"simulation":[0,1,2,3,4,5],"llm":[6,7]},"requested_rounds":int(sys.argv[sys.argv.index("--iterate") + 1]),"requirements_and_verifier_edits":False},ensure_ascii=False,indent=2))' "$execution_dir/execution-manifest.json" "$ea_site_packages" "${command[@]}"
"$ea_python" -m tools.gpu_telemetry --output "$execution_dir/gpu-telemetry.jsonl" &
sampler_pid=$!
trap 'kill "$sampler_pid" 2>/dev/null || true' EXIT
cd "$repo_root"
set +e
"${command[@]}" > "$execution_dir/run.log" 2>&1
run_exit=$?
set -e
kill "$sampler_pid" 2>/dev/null || true
wait "$sampler_pid" 2>/dev/null || true
"$ea_python" -c 'import json,sys,datetime; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({"exit_code":int(sys.argv[2]),"finished_at":datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))' "$execution_dir/runner-status.json" "$run_exit"
if [[ -d "$output_dir" ]]; then
  cp "$execution_dir"/* "$output_dir/"
fi
exit "$run_exit"
