# Add a bundled scenario

Use this guide to add an engineering instance to this repository. External scenario loading is not implemented; its [development tasks](../development/external-scenarios.md) are separate.

## Define the instance

State its mission, requirement authority, world/model assumptions, design variables, runtime actions, verification conditions, optimization metrics, evidence, and failure states. Identify which parts are simulated and which claims need physical validation. Use [all three bundled instances](../scenarios/index.md) as examples of different boundaries, not as one mandatory domain schema.

## Connect the current implementation

1. Add `src/scenario/<name>/scenario.yaml` and a runner that owns configuration, backend/team construction, evidence, and completion. Use the current `Scenario` ABC only where its contract fits; actual runners receive additional job arguments.
2. Publish a scenario registry entry and merge it in `scenario/runner.py::_scenario_registry()`. Directory discovery alone only changes listings. Ensure `list_scenarios()`, descriptions, and executable names agree.
3. Extend `scenario/jobs/executor.py` if the runner needs arguments beyond the generic path. Decide explicitly whether proposal adoption, progress callbacks, seed overrides, history, and recreation apply. Do not inherit SSOS's iteration semantics by accident.
4. Update `tools/cli` validation and dispatch for supported modes, backends, and required inputs. Keep domain configuration validation in its owner. Check installed-package data declarations if adding YAML or other resources.
5. Implement deterministic evaluation and write a non-empty `summary.json`. Preserve effective inputs, applied design, telemetry, and provenance needed to reproduce the verdict. Define incomplete and non-applicable evidence before reporting success.

## Integration checklist for the current seam

The old directory-only extension recipe is insufficient for this checkout. Review these concrete integration points together:

| Integration point | What to add or verify | First regression |
| --- | --- | --- |
| `scenario/<name>/scenario.yaml` | Package resource, description, owned validation | Discovery and installed-resource availability |
| `scenario_run.py` registry entry | Runnable object and non-empty summary | Valid short execution in temporary output |
| `runner.py::_scenario_registry()` | Explicit registry merge | Listed names agree with dispatch |
| `jobs/executor.py` | Supported extra arguments and failure handling | Unsupported argument/adoption path rejected |
| `tools/cli` | Modes, backend admission, preflight, defaults | CLI and job request resolve equivalent intent |
| Evaluation and artifacts | Declared scope and missing-evidence behavior | Damaged evidence cannot pass |
| Reader documentation | Existing user/developer scenario parents | Both language journeys reach the new contract |

A declaration of `run()` is only part of the seam. For example, a runner that accepts `apply_proposals_path` but ignores it must not advertise proposal adoption. Define a test around the changed behavior, not merely around the method's existence.

## Prove the boundary

Add tests for registry/listing alignment, configuration rejection, valid short execution in temporary storage, malformed or missing summary, invalid proposal handling, output isolation, and deterministic evaluation. Test backend and provider failure without relying on a live service. Include domain invariants and a check that requirement edits cannot improve a supposedly fixed comparison.

Create mirrored user pages for configuration, running, and results, plus developer pages for implementation and evaluation. Link public fields to the [user reference](../../users/reference/configuration.md). The acceptance result is a runnable, reviewable instance with its own evidence contract; broad externalization is not a prerequisite for adding a bundled instance.
