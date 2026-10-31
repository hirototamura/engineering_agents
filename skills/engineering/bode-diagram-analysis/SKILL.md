---
name: bode-diagram-analysis
description: "Evaluate a linear design in the frequency domain by composing transfer-function derivation and frequency-response calculation. Produce a Bode assessment with explicit design criteria."
---

# Bode diagram analysis

## Primary output

`result.json`: **frequency_response_assessment**, version 1. Frequency-response assessment: Bode data/plot, criterion results, plant internal stability and scope. No supplied criteria means unassessed, not pass. Point criteria do not certify a whole band. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

- `transfer-function-derivation`
- `frequency-response-calculation`

The executor runs these dependencies and retains their typed results and receipts under `dependencies/`. Read the relevant lower-level skill instructions when interpreting their scope. Do not independently replace their calculations.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run bode-diagram-analysis \
  --input skills/engineering/bode-diagram-analysis/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

When asked for existing results, inspect their receipts first. Reuse evidence only when the relevant inputs/configuration and required contract/source versions match; state any differences. When new execution is requested, use a fresh output directory and preserve older runs. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
