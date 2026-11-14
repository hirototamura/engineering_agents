# Development work

Use this section to scope changes that strengthen the framework across engineering domains. Current behavior is described in [architecture](../architecture.md), [runtime](../runtime.md), and [internal execution contracts](../reference/execution.md). A development objective is not a claim that the capability is available today.

## External scenario ownership

The main cross-scenario objective is to let an engineering instance be developed outside this repository while retaining its own world, tools, requirements, evaluation, and evidence. Current configuration discovery, fixed registry dispatch, CLI branches, output tracks, and SSOS-specific iteration do not yet provide that boundary.

[External scenario development](external-scenarios.md) defines responsibility boundaries, independently reviewable tasks, and acceptance criteria. It deliberately stops before specifying an external API, manifest, or plugin implementation. Those decisions require an implementation proposal and regression evidence across the three bundled scenarios.

## Documentation as maintained behavior

[Documentation maintenance](documentation.md) describes audience ownership, current-versus-historical material, bilingual updates, and checks. Documentation changes should make real capabilities easier to use and change. They must not imply that one scenario's backend, score, or proposal loop works for every other scenario.

For other work, file a concrete proposal through [contributing](../contributing.md). Name the current failure and the smallest boundary that resolves it. A change is complete when its behavior, failure handling, evidence, and documentation can be reviewed together.
