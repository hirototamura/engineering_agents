---
name: motor-operating-point
description: "Assess current, voltage and power at one motor/driver operating point using documented effective-DC constants. Use for actuator design across projects."
---

# Motor operating point

## Primary output

`result.json`: **motor_operating_point**, version 1. Motor operating-point assessment: electrical/mechanical/copper/driver power, braking dissipation and current/voltage feasibility. BLDC phase/line constants need an explicit effective-DC conversion. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

None. This is an atomic engineering analysis skill.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run motor-operating-point \
  --input skills/engineering/motor-operating-point/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

When asked for existing results, inspect their receipts first. Reuse evidence only when the relevant inputs/configuration and required contract/source versions match; state any differences. When new execution is requested, use a fresh output directory and preserve older runs. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
