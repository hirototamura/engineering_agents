---
name: frequency-response-calculation
description: "Calculate a complex frequency response from a supplied SISO transfer function. Use as a reusable numerical primitive for frequency-domain analysis."
---

# Frequency response calculation

## Primary output

`result.json`: **frequency_response**, version 1. Complex response, magnitude in dB relative to one output-unit/input-unit and an explicitly defined unwrapped phase branch. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

None. This is an atomic engineering analysis skill.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run frequency-response-calculation \
  --input skills/engineering/frequency-response-calculation/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

Use a fresh output directory. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
