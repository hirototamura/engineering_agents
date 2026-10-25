# Validation of this skill

Run from Engineering Agents with `.[dev,analysis]` installed:

```bash
python -m pytest -q tests/engineering_skills/test_mechanical.py tests/engineering_skills/test_runner.py
```

Independent checks: Closed-form cube and annular-cylinder moments; two separated masses and parallel-axis products; rigid rotation invariance; missing mass propagation; reproducible bounded samples; invalid tensors/rotations rejected.

These tests qualify implemented equations and execution behavior, not the physical cube. CI checks SKILL.md frontmatter and referenced files in test_harness.py; the installer records a manifest of skill/tool SHA-256 hashes. Live acceptance uses the pinned Hermes/Qwen endpoint, asks the agent to load this skill and run the example with a new output path, then checks the actual receipt and numerical result independently. Save the model ID, tool-call transcript and output hashes. A fluent final answer without tool execution is a failure of harness acceptance.

After a skill, calculator, dependency, model/quantization or serving-template change, repeat the affected deterministic tests and live acceptance. Collect real measurement comparisons before declaring physical accuracy. Do not use a model's self-evaluation as the numerical oracle.
