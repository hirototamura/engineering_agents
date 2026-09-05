#!/usr/bin/env bash
# Run one design->verify chain, the way the three archived chains were run.
#
# Each round simulates the habitat, hands the run to the design agent, and
# installs whatever the agent proposes as the next round's hardware. The chain's
# single answer lands in <output>/chain_final_answer.json.
#
#   ./scripts/run_design_chain.sh                      # 50 rounds, defaults from scenario.yaml
#   ./scripts/run_design_chain.sh --rounds 5           # a short one, to see it work
#   ./scripts/run_design_chain.sh --provider ollama --model qwen3:8b
#
# The design side needs an LLM. `ea doctor` says whether one is reachable.
# The operators are the deterministic rule base by default, so the measured
# difference between two chains is the design, not a different crew improvising.
#
# What the archived chains under experiments/runs/ were run with, and how to
# reproduce each: experiments/README.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ROUNDS=""
PROVIDER=""
MODEL=""
RUN_ID=""
EXTRA=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [options] [-- extra ea args...]

Options:
  --rounds N        Rounds in the chain (1-50). Default: scenario.yaml iteration.count
  --provider NAME   LLM provider for the design side: ollama | vllm
  --model NAME      Model id (Ollama tag or vLLM served-model id)
  --run-id NAME     Output directory name under src/experiments/results/
  -h, --help        Show this help

Examples:
  $(basename "$0") --rounds 50
  $(basename "$0") --rounds 5 --provider ollama --model qwen3:8b --run-id smoke
  $(basename "$0") -- --set plant_sim.crew.size=120
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rounds) ROUNDS="$2"; shift 2 ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; EXTRA+=("$@"); break ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if command -v ea >/dev/null 2>&1; then
  EA=(ea)
else
  # Editable install not on PATH; the package is importable from src/.
  EA=(python3 -m tools.cli)
  export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
fi

ARGS=(run ssos_eclss_loop)
[[ -n "$ROUNDS" ]]   && ARGS+=(--iterate "$ROUNDS")
[[ -n "$PROVIDER" ]] && ARGS+=(--llm-provider "$PROVIDER")
[[ -n "$MODEL" ]]    && ARGS+=(--llm-model "$MODEL")
[[ -n "$RUN_ID" ]]   && ARGS+=(--run-id "$RUN_ID")
ARGS+=("${EXTRA[@]+"${EXTRA[@]}"}")

echo "==> ${EA[*]} ${ARGS[*]}"
"${EA[@]}" "${ARGS[@]}"

echo
echo "Chain finished. What to read, in order:"
echo "  chain_final_answer.json    the one design the whole chain answers with"
echo "  chain_summary.json         survivors first vs last, and the paired replay"
echo "  compact_chain_memory.json  the note each round left for the next"
echo "  NN/design_decision_state.json  the page the model saw that round, and its answer"
echo
echo "To turn a chain into the per-round table the docs cite:"
echo "  cd experiments && python3 analysis/analyze_ssos_iter.py --root <chain dir> --prefix mychain"
