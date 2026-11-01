# Validation

**Atomic numerical qualification**

Compare RC and second-order responses to direct complex arithmetic; reject undefined dB/phase, invalid frequency grids and malformed coefficients.

```bash
python -m pytest -q tests/engineering_skills/test_atomic_control.py
```

Use independent mathematical references and limiting/negative cases; do not use LLM self-evaluation as the oracle.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
