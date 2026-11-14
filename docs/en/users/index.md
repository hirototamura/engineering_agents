# Use Engineering Agents

Engineering Agents runs engineering teams that propose designs, observe a simulated system, and evaluate the resulting evidence. The framework spans domains; each bundled scenario supplies its own world, permitted actions, requirements, and evidence contract.

Start with the [local quickstart](quickstart.md), then choose a [scenario](scenarios/index.md). The quickstart uses one scenario to demonstrate the workflow; its units and verification rules do not apply to every scenario.

## Plan, run, inspect

- [Configure a run](guides/configure-run.md): choose conditions, preserve inputs, and select an output directory.
- [Use an LLM](guides/llm.md): connect an existing model service and select which agents use it.
- [Iterate designs](guides/design-iterations.md): apply proposals and compare re-simulated results.
- [Inspect results](guides/inspect-results.md): separate execution success from engineering evidence.
- [Open reports](guides/reports.md) or [diagnose a problem](guides/troubleshooting.md).

Read [concepts](concepts.md) for the distinction between supervision, design, operations, and verification. Consult the [CLI](reference/cli.md), [configuration](reference/configuration.md), and [artifact reference](reference/artifacts.md) when preparing repeatable work.

These pages cover existing features. To change a simulator, add a tool, or develop a scenario, use the [developer documentation](../developers/index.md). Loading scenarios from an external package is a [development goal](../developers/development/external-scenarios.md), not a current command-line feature.

## Start from the decision you need to make

| Your question | Start here | Evidence to retain |
| --- | --- | --- |
| Can I complete a local design handoff? | [Quickstart](quickstart.md) | Separate first/applied runs and consumed proposal |
| Which system can answer my engineering question? | [Scenario selection](scenarios/index.md) | The chosen scenario's scope and prerequisites |
| What changed between two runs? | [Inspect results](guides/inspect-results.md) | Effective inputs, observations, evaluation versions |
| Can a proposed design be accepted? | [Concepts](concepts.md) and the scenario's results page | Constraints, verification evidence, approval reasons |
| Where can I read existing experiment reports? | [Report library](guides/reports.md) | Original evidence alongside derived views |
