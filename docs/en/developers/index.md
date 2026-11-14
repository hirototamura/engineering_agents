# Develop Engineering Agents

Engineering Agents develops engineering teams that design and verify systems across domains. Contributors change the execution framework, agent workflows, simulators, tools, and evidence checks that make those teams reviewable. The bundled [scenarios](scenarios/index.md) are three separate engineering instances with equal status.

Start with [development setup](setup.md), then read the [architecture](architecture.md) and [execution lifecycle](runtime.md). For a concrete change, use one of these guides:

- [Add a bundled scenario](guides/add-scenario.md).
- [Change a simulator backend](guides/change-backend.md).
- [Add an agent tool](guides/add-tool.md).
- [Change evaluation](guides/change-evaluation.md).

[Agents](agents.md), [tools and memory](tools-memory.md), and [records and integrations](records-integrations.md) explain the boundaries behind those tasks. [Execution contracts](reference/execution.md) and [storage contracts](reference/storage.md) describe current internal behavior. Commands, configuration fields, and artifact interpretation belong to the [user reference](../users/reference/cli.md).

Preserve the mission while proposing changes to design or verification requirements through supervision. Keep design creativity separate from deterministic evidence checks. A simulation result establishes only the verification scope of its model; it does not establish physical validation.

The current system discovers bundled configuration directories and dispatches through a fixed registry with scenario-specific branches. Loading an arbitrary external scenario is a [development objective](development/external-scenarios.md), not a shipped capability. Read [contributing](contributing.md) for the review and verification process.
