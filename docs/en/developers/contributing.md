# Contribute a reviewable change

A useful change names a concrete failure or missing capability, the responsible boundary, and observable behavior after the fix. Start from [architecture](architecture.md) and the relevant [scenario](scenarios/index.md), rather than treating one instance as the whole framework.

## Define the work

For feature, design, and integration proposals, use the repository's [first-principles issue template](https://github.com/hirototamura/engineering_agents/blob/main/.github/ISSUE_TEMPLATE/first_principles.md): current problem, why it matters, scope, and expected outcome with acceptance criteria. The template concerns the justification for work. The `first_principles` persona archetype concerns how a simulated agent reasons; these are different mechanisms.

State the requirement source and who can revise it. Separate changes to design variables, runtime policy, evaluator behavior, and evidence presentation. Preserve the mission, physical constraints, and independent deterministic verification. For planned external scenarios, use the [bounded development tasks](development/external-scenarios.md), not an invented plugin API.

## Implement and check

Read the repository [AGENTS guide](https://github.com/hirototamura/engineering_agents/blob/main/AGENTS.md) and [documentation rules](https://github.com/hirototamura/engineering_agents/blob/main/docs/AGENTS.md). Make the change in its owning layer, update both documentation languages, and use temporary directories for test artifacts. Do not reuse recorded experiment directories for tests.

Run targeted tests while developing, then run:

```bash
python -m pytest --ignore=tests/e2e
python -m mkdocs build --strict
```

Provider tests should use controlled responses and cover transport/parse failures. Backend changes need unit, state-transition, and evidence checks; live ROS2, GPU, or physical validation requires the matching environment and a stated scope. Inspect relevant optional-test skips. A viewer opening successfully is not proof of a design–verification loop.

## Explain the result

Describe the trigger, prior failure, new behavior, affected contracts, and verification performed. Include limitations that matter to the claim: mock versus physics backend, numerical versus physical verification, unexecuted final proposals, or incomplete delivery. Preserve old experiment evidence and its recorded conditions. Update current documentation without relocation stubs or compatibility headings; see [documentation maintenance](development/documentation.md).
