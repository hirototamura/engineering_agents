# Scenario implementation guides

Each bundled scenario owns an engineering world, requirement source, allowed interventions, evidence, and evaluation. They are equal instances of the project; they do not share every backend, agent mode, proposal format, or verification claim.

- [Scrubber degradation](scrubber_degradation/index.md): mock ECLSS/EPS recovery, step teams, and post-run design proposals. Proposal reapplication is not implemented.
- [SSOS ECLSS loop](ssos_eclss_loop/index.md): storage operations, distinct actor/design modes, plant/model checks, and chained proposal application.
- [Balancing cube](balancing_cube/index.md): revisioned SSOT inputs, bounded mechanical/control compilation, fixed-dt MuJoCo/MJX evaluation, and a separate design workflow.

For each instance, start with its developer overview, then choose implementation or evaluation according to your change. Public prerequisites, commands, configuration, and result interpretation live in the parallel [user scenarios](../../users/scenarios/index.md).

Shared mechanics are described in [execution](../runtime.md), [storage](../reference/storage.md), and [agents](../agents.md). Adding another bundled instance requires current registry and dispatch work; follow [add a scenario](../guides/add-scenario.md). External loading remains a [development goal](../development/external-scenarios.md).
