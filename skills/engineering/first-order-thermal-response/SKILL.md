---
name: first-order-thermal-response
description: "Calculate one exact constant-load interval of a lumped first-order thermal network. Use for electronic, actuator or mechanical thermal assessments."
---

# First order thermal response

## Primary output

`result.json`: **thermal_interval_response**, version 1. Thermal interval response: end/peak/equilibrium temperatures, time constant and optional limit assessment. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

None. This is an atomic engineering analysis skill.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run first-order-thermal-response \
  --input skills/engineering/first-order-thermal-response/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

Use a fresh output directory. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
