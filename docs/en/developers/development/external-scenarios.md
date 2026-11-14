# External scenario development

**Planned capability.** The current repository bundles three scenarios. Listing scans local `scenario.yaml` directories, execution merges fixed registries, the executor and CLI branch by name, results have two default tracks, and chain iteration is SSOS-specific. An arbitrary external package cannot currently be registered through a supported public interface.

The goal is to let independently maintained engineering instances own their domain while the framework supplies execution and evidence infrastructure. This page defines responsibilities, development tasks, and acceptance criteria only. It does not define a future API, plugin schema, or implementation mechanism.

## Responsibility boundaries

The framework should own discovery/admission, generic job lifecycle, execution status, output isolation, progress, and shared evidence persistence. It should expose supported capabilities without assuming ECLSS telemetry, a cube trial matrix, or one proposal format.

A scenario should own its mission and requirement authority, configuration validation, world/model construction, design and runtime operations, agent/tool composition, evaluation, and the meaning of its artifacts. A backend should own units, clock and state transitions, numerical behavior, and model evidence. Integrations should own authority/provenance translation and retry behavior. Viewers should consume declared evidence rather than become hidden evaluators.

## Development tasks and acceptance criteria

1. **Inventory current coupling.** Trace directory discovery, registries, CLI/executor branches, scenario imports in shared helpers, default output tracks, resources, and iteration. Accept when every scenario-specific assumption has an owner and regression coverage or an explicit gap.
2. **Unify discovery and executable admission.** Make available and runnable names agree, with clear duplicate, missing-dependency, and invalid-definition failures. Accept when a separate test scenario can be discovered and rejected safely without core source edits for its domain.
3. **Separate lifecycle from domain operations.** Move scenario-specific dispatch knowledge behind owned boundaries. Accept when all three bundled instances retain their existing supported modes and failure behavior, and unsupported operations fail before execution.
4. **Separate configuration, inputs, and evidence.** Retain scenario validation, resolved-input provenance, proposal application, immutable or recreatable output policy, and authoritative evaluation. Accept when an external test instance cannot overwrite another run or turn missing evidence into success.
5. **Make resources and optional dependencies installable.** Check packaged YAML/data and backend/provider preflight. Accept when tests from an installed distribution work without relying on repository-relative source files or importing unavailable optional stacks during discovery.
6. **Prove domain independence.** Add contract tests and a minimal external test instance with different domain data. Accept when listing, validation, execution, evidence inspection, and failure recovery work without importing a bundled scenario's types, and bundled regressions remain green.
7. **Publish the supported boundary.** Write user and developer documentation after behavior is implemented. Accept when current support, limitations, migration work, and extension tests are explicit in both languages.

Do not combine this objective with changing score semantics, requirements, or historical experiment results. Those changes require their own evidence and authority.
