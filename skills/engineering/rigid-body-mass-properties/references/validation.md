# Validation

**Atomic numerical qualification**

Closed-form box/cylinder moments, separated masses and parallel-axis cross terms, frame rotation and invalid/missing-data cases. Uncertainty sampling belongs to the composed skill.

```bash
python -m pytest -q tests/engineering_skills/test_mechanical.py
```

Use independent mathematical references and limiting/negative cases; do not use LLM self-evaluation as the oracle.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
