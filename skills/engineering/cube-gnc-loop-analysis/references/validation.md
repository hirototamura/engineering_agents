# Validation

**Composition qualification**

Assume qualified transfer/frequency/gain skills. Check physical-model-to-state-space mapping, shared state basis/control period, dependency lineage and propagation. Separately test the project adapter/nonlinear model in the small-angle and saturation cases.

```bash
python -m pytest -q tests/engineering_skills/test_composition.py tests/engineering_skills/test_gnc.py
```

Assume qualified dependencies. Test routing, exact input/output contracts, data flow, assessment logic, error propagation and lineage. Qualify any newly introduced mathematics separately; do not duplicate dependency formula tests.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
