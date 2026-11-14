# Engineering Agents repository guide

Engineering Agents develops engineering teams that design and verify systems
across domains through accumulated knowledge, memory, tools, evaluation, and
evidence. The three bundled scenarios are equal-status instances of this effort.

## Sources of guidance

- [Developer guide](docs/en/developers/index.md) / [開発者ガイド](docs/ja/developers/index.md)
- [User guide](docs/en/users/index.md) / [ユーザーガイド](docs/ja/users/index.md)
- [Documentation rules](docs/AGENTS.md) apply when changing documentation.

## Engineering discipline

- Preserve the mission and physical constraints. Agents may propose requirement
  revisions; supervision retains authority until the requirements are revised.
- Separate design proposals, applied changes, simulated evidence, and physical
  validation. LLM explanations and dashboard previews do not establish pass/fail.
- Requirements come from the selected scenario's authoritative contract. One Piece
  integration is scenario-specific; provenance export does not imply SSOT input.
- Keep evidence, effective inputs, rejected candidates, and failure states auditable.
- Follow the dependency direction `tools → scenario → environment → core`.
  Scenario code calls `integrations/one_piece`; do not import upward or put LLM /
  Persona logic in environment implementations.
- Do not assume identical modes, proposal schemas, evaluation, or output handling
  across scenarios. External scenario loading is not yet implemented.

## Development and validation

Use Python 3.11 or newer. Install this checkout with `python -m pip install -e
'.[dev]'` in a virtual environment. Verify imports resolve into this checkout;
a machine-global Python can import another editable installation.

```bash
PYTHONPATH=src python -m tools.cli --help
python -m pytest --ignore=tests/e2e
mkdocs build --strict
```

Optional MuJoCo / One-Piece / GPU tests require the corresponding extras and
services. Live `tests/e2e` needs SSOS Docker / ROS2 with `SSOS_E2E=1`. Treat a local
CLI smoke as a check of its declared path; full acceptance follows the selected
scenario's regression kit.

The design→verification loop and persisted evidence are the functional smoke
boundary. See [SSOS run procedure](docs/en/users/scenarios/ssos_eclss_loop/running.md)
for a local example. Choose distinct run IDs when comparing results or applying a
previous proposal; some paths recreate recognized output directories.

[Contribution process](docs/en/developers/contributing.md) and
[documentation maintenance](docs/en/developers/development/documentation.md)
define the corresponding review checks. Historical research is isolated under
`docs/_archive/`; it does not override current implementation or guidance.
