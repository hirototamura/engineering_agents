# Validation

**Atomic numerical qualification**

Check analytical step response, cooling, long/short time limits, interval-splitting invariance and initial-temperature limit violations.

```bash
python -m pytest -q tests/engineering_skills/test_atomic_energy.py
```

Use independent mathematical references and limiting/negative cases; do not use LLM self-evaluation as the oracle.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
