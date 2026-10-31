# Validation

**Composition qualification**

Assume qualified synthesis. Check that the exact supplied state realization reaches the gain skill, sampling settings propagate and unstable sampled results remain failed.

```bash
python -m pytest -q tests/engineering_skills/test_composition.py
```

Assume qualified dependencies. Test routing, exact input/output contracts, data flow, assessment logic, error propagation and lineage. Qualify any newly introduced mathematics separately; do not duplicate dependency formula tests.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
