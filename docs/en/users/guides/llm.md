# Connect a model service

LLM modes require an existing, reachable Ollama or OpenAI-compatible vLLM service and a model available on that service. Installing Engineering Agents does not install or start either service. Labeled rules can run the local ECLSS quickstart without one.

## Select the agents that use the model

ECLSS separates runtime actors from post-run designers. This example keeps operations deterministic and uses an Ollama designer:

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --design-mode llm \
  --llm-provider ollama --llm-model gemma4:e4b \
  --set agents.design.llm.base_url=http://localhost:11434 \
  --steps 20 --run-id local-llm-01 --set iteration.enabled=false --dry-run --json
```

Check the resolved provider, model, and URL, then remove the dry-run flags. On ECLSS, `--llm-provider` and `--llm-model` affect only sides whose mode is `llm`. Set actor and designer URLs separately when they use different services. Scrubber uses `--agents-mode llm`; cube uses its own [LLM design configuration](../scenarios/balancing_cube/configuration.md).

## Resolve connection settings

`LLM_PROVIDER` overrides the YAML provider. `OLLAMA_BASE_URL` overrides the Ollama URL. `VLLM_BASE_URL`, `VLLM_MODEL`, and `VLLM_API_KEY` override vLLM connection settings. A global vLLM URL applies to both ECLSS sides, so unset it when using independent actor/designer endpoints.

The shipped ECLSS actor and designer settings point at separate lab vLLM services. Scrubber defaults to Ollama. Check the scenario configuration instead of assuming a shared model default. Use a served-model ID for vLLM: an Ollama tag containing `:` falls back to the vLLM default model. vLLM normalizes its base URL to end in `/v1`.

`api_timeout` in YAML controls Ollama; vLLM uses a 300-second client default unless `VLLM_API_TIMEOUT` is set. `max_concurrency`, memory, discourse, context length, and completion budgets can affect throughput and response completeness.

## Diagnose a failure

Run `PYTHONPATH=src python -m tools.cli doctor` and inspect the reported service URLs. This is an environment report, not a guarantee that the selected scenario's exact model is loaded. Normal ECLSS/scrubber runs perform LLM preflight after dry-run handling. Inspect messages and design records for malformed, rejected, or missing proposals; [troubleshooting](troubleshooting.md) explains how to preserve that evidence.

## Keep connection and role choices distinct

| Setting | Scope | Common comparison mistake |
| --- | --- | --- |
| `--actor-mode` / `--design-mode` | Which ECLSS role uses rules, an LLM, or no agent | Assuming the designer must use the actor's mode |
| `agents.actor.llm.*` | ECLSS actor service and generation settings | Editing designer settings while diagnosing actor latency |
| `agents.design.llm.*` | ECLSS post-run designer | Treating a generated explanation as verification |
| `VLLM_BASE_URL` / `VLLM_MODEL` | Every vLLM client in the process | Accidentally collapsing separate actor/designer services |
| `--llm-model` | All selected `llm` sides on the ECLSS CLI | Assuming it changes only one side |

A useful inspection record pairs the resolved model target with the saved messages/proposals and measured result. Changing a model while also changing the simulation horizon prevents a clean model comparison.
