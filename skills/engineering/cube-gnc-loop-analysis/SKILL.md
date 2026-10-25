---
name: cube-gnc-loop-analysis
description: "Compose reusable engineering analysis skills for one balancing-cube tilt-axis control study, with a project-specific nonlinear comparison."
---

# Cube gnc loop analysis

## Primary output

`result.json`: **cube_local_control_assessment**, version 1. Cube local-control assessment: linked transfer-function, Bode and pole-placement outputs plus a torque-limited nonlinear diagnostic. No production K, requirement or baseline is changed. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

- `transfer-function-derivation`
- `bode-diagram-analysis`
- `pole-placement-design`

The executor runs these dependencies and retains their typed results and receipts under `dependencies/`. Read the relevant lower-level skill instructions when interpreting their scope. Do not independently replace their calculations.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run cube-gnc-loop-analysis \
  --input skills/engineering/cube-gnc-loop-analysis/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

When asked for existing results, inspect their receipts first. Reuse evidence only when the relevant inputs/configuration and required contract/source versions match; state any differences. When new execution is requested, use a fresh output directory and preserve older runs. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
