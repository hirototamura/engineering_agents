---
name: pole-placement-design
description: "Compose transfer-function derivation and state-feedback synthesis into a reviewable pole-placement design with an explicit state basis."
---

# Pole placement design

## Primary output

`result.json`: **pole_placement_design**, version 1. Pole-placement design containing K in the original state coordinates, target/achieved poles, sampled stability and pass/fail within the stated model. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

- `transfer-function-derivation`
- `state-feedback-gain-synthesis`

The executor runs these dependencies and retains their typed results and receipts under `dependencies/`. Read the relevant lower-level skill instructions when interpreting their scope. Do not independently replace their calculations.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run pole-placement-design \
  --input skills/engineering/pole-placement-design/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

Use a fresh output directory. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
