# Validation of this skill

Run from Engineering Agents with `.[dev,analysis]` installed:

```bash
python -m pytest -q tests/engineering_skills/test_electrical.py tests/engineering_skills/test_runner.py
```

Independent checks: Independent electrical/mechanical/copper energy identity; zero-load back-EMF; analytical first-order thermal step; continuous temperature between modes; regeneration/dissipative braking; current/voltage limits and invalid conventions.

These tests qualify implemented equations and execution behavior, not the physical cube. The installer also validates the SKILL.md frontmatter and packages a manifest of skill/tool SHA-256 hashes. Live acceptance uses the pinned Hermes/Qwen endpoint, asks the agent to load this skill and run the example with a new output path, then checks the actual receipt and numerical result independently. Save the model ID, tool-call transcript and output hashes. A fluent final answer without tool execution is a failure of harness acceptance.

After a skill, calculator, dependency, model/quantization or serving-template change, repeat the affected deterministic tests and live acceptance. Collect real measurement comparisons before declaring physical accuracy. Do not use a model's self-evaluation as the numerical oracle.
