---
name: rigid-body-mass-properties
description: "Calculate mass, center of mass and inertia tensors of an assembly. Use for any rigid mechanical design with supplied masses, geometry and component frames."
---

# Rigid body mass properties

## Primary output

`result.json`: **rigid_body_mass_properties**, version 1. Rigid assembly mass properties: known-part and full-system mass/CoM/inertia, principal moments, missing masses and tensor sign convention. Unknown masses keep full-system properties unresolved. Supporting plots/CSV are views of this result. `summary.json` is a compact view; `receipt.json` records source, input, result and dependency hashes.

## Composition

None. This is an atomic engineering analysis skill.

## Execute

Read [input_contract.md](references/input_contract.md) for inputs. From the Engineering Agents checkout (`EA_ENGINEERING_REPO` in the Hermes wrapper), execute the trusted tool:

```bash
ea-engineering run rigid-body-mass-properties \
  --input skills/engineering/rigid-body-mass-properties/examples/input.json \
  --output /absolute/path/to/NEW_ANALYSIS_RUN
```

Use a fresh output directory. Read `summary.json` and `receipt.json` with `cat`, inspect applicable plots, and explain the assessment, assumptions, missing data and next useful analysis. The bundled input is an assumed or synthetic example. The tool does not approve requirements, adopt a baseline or actuate hardware. Numerical qualification is distinct from physical validation.

Read [validation.md](references/validation.md) before claiming this skill is qualified.
