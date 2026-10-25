---
name: state-feedback-gain-synthesis
description: "Synthesize full-state SISO feedback gains for explicit target poles and assess sampled stability. Use as a reusable pole-placement calculation."
---

# State feedback gain synthesis

## Primary output

`result.json`: **state_feedback_gain**, version 1. K for u=-Kx, gain units, desired/achieved poles and zero-order-held closed-loop stability. No production controller is edited. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

None. This is an atomic engineering analysis skill.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run state-feedback-gain-synthesis \
  --input skills/engineering/state-feedback-gain-synthesis/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

When asked for existing results, inspect their receipts first. Reuse evidence only when the relevant inputs/configuration and required contract/source versions match; state any differences. When new execution is requested, use a fresh output directory and preserve older runs. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
