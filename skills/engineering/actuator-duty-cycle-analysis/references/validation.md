# Validation

**Composition qualification**

Assume qualified motor/thermal primitives. Check heat and temperature handoffs, chronology, motor-count scaling, energy accumulation and preservation of lower-level violations.

```bash
python -m pytest -q tests/engineering_skills/test_composition.py tests/engineering_skills/test_electrical.py
```

Assume qualified dependencies. Test routing, exact input/output contracts, data flow, assessment logic, error propagation and lineage. Qualify any newly introduced mathematics separately; do not duplicate dependency formula tests.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
