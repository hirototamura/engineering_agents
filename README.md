# Engineering Agents

Develop teams of engineering agents that design and verify systems across domains. Accumulated knowledge, memory, tools, evaluation, and evidence inform the next engineering decision.

[日本語](README.ja.md) · [Documentation](docs/en/index.md)

## Run design and verification

The [user guide](docs/en/users/index.md) serves engineers configuring existing capabilities, running experiments, and interpreting outcomes.

- [Quickstart](docs/en/users/quickstart.md)
- [Configure a run](docs/en/users/guides/configure-run.md)
- [Inspect results and evidence](docs/en/users/guides/inspect-results.md)
- [CLI reference](docs/en/users/reference/cli.md)

## Add or change capabilities

The [developer guide](docs/en/developers/index.md) serves contributors modifying the repository and scenarios.

- [Development environment](docs/en/developers/setup.md)
- [Architecture](docs/en/developers/architecture.md)
- [Extend and verify](docs/en/developers/guides/add-scenario.md)
- [External scenario development](docs/en/developers/development/external-scenarios.md)

## Bundled scenarios

- [scrubber_degradation](docs/en/users/scenarios/scrubber_degradation/index.md): scrubber degradation and power-assisted recovery
- [ssos_eclss_loop](docs/en/users/scenarios/ssos_eclss_loop/index.md): life-support operations and capacity design
- [balancing_cube](docs/en/users/scenarios/balancing_cube/index.md): cube mechanics and control design

Each scenario is an equal-status instance. The current implementation requires bundled registration; external scenario loading is a development goal. Dashboards are tools for reviewing evidence.

Python 3.11+ is required. Each scenario documents its simulator, LLM, SSOT, and Docker prerequisites. Coding agents read [AGENTS.md](AGENTS.md); documentation changes follow [docs/AGENTS.md](docs/AGENTS.md).

[Apache License 2.0](LICENSE.txt) — Copyright 2026 One Piece Engineering
