# Configure scrubber degradation

The bundled inputs are `src/scenario/scrubber_degradation/scenario.yaml` and `agents.yaml`. Common merge and output rules are in the [configuration reference](../../reference/configuration.md).

## Initial conditions and anomaly

The simulation defaults to 50 steps, initial CO₂ of 800 ppm, and initial power margin of 150 W. At step 20 the anomaly begins: scrubber efficiency decays by 0.02 per step, power margin decays by 3 W per step, and CO₂ production is multiplied by 1.4. `anomalies` is a list; a patch replaces the whole list.

`design_parameters` sets the model's production, removal, power, bypass, and load-reduction coefficients. For example, base scrubber efficiency is 0.95, CO₂ production 32 ppm/step, and fan power 80 W. These are model coefficients; changing them changes the experiment, not an automatically verified hardware design.

## Agent modes

`agents.mode` defaults to `none`. `--agents-mode labeled_rule_base` enables four engineers with fixed recovery policy. `--agents-mode llm` enables model-driven deliberation and operations, using the supplied team personas and model settings. Labeled rules ignore the thinking-style archetypes; composition is still recorded.

The bundled team has memory limit 8 entries and discourse window 12 messages. Its LLM defaults are Ollama at `http://localhost:11434`, model `gemma4:e4b`, temperature 0.45, and a 512-token completion budget. See [LLM setup](../../guides/llm.md) for environment overrides and service requirements.

This scenario does not select among the ECLSS `mock`, `plant_sim`, and `ros2` backends. Use its station model. `--apply-proposals` does not implement scrubber reinjection; `--iterate` is not supported. The fixed health and recovery thresholds are explained once in [results](results.md).

## Understand the trade before changing a coefficient

| Runtime command | Modeled benefit | Modeled trade or limit |
| --- | --- | --- |
| `set_fan_speed` | More airflow increases modeled removal | Fan power also rises |
| `enable_bypass` | Adds a temporary flow bonus | Adds power load; does not add a topology edge |
| `reduce_load` | Reduces modeled CO₂ production | A load-reduction abstraction, not a detailed crew task model |
| `request_eps_boost` | Temporary electrical support | A finite-duration mock EPS response |

The CO₂ update is a small discrete model, not gas-flow CFD:

```text
production = configured_production × anomaly_multiplier × load_factor
removal = current_CO2 × efficiency × fan_speed × scrub_coefficient × bypass_factor
next_CO2 = max(400, current_CO2 + production − removal)
```

`load_factor` is 1 unless load reduction is active; `bypass_factor` is 1 unless bypass is enabled. These relationships explain why a “more removal” action can also worsen power margin. They do not turn the model coefficients into measured scrubber hardware properties.
