# Validation

**Atomic numerical qualification**

Known threshold examples, stale revisions/configurations, failed/missing evidence, domain/unit/condition mismatches, canonical payload tampering and bad artifact hashes.

Check that a forged input value cannot override the hashed artifact value, that
execution metadata is bound to the same record, and that unsupported numeric
criteria do not abort other assessments. Ineligible failures remain visible as
inconclusive; an eligible failed execution remains a failure.

```bash
python -m pytest -q tests/engineering_skills/test_systems.py tests/engineering_skills/test_runner.py
```

Use independent mathematical references and limiting/negative cases; do not use LLM self-evaluation as the oracle.

CI validates packaging and the acyclic declared graph. Live Hermes acceptance checks actual skill loading, successful calculator execution and matching result/dependency hashes. Re-run affected qualification after implementation, dependency or runtime changes. These checks establish software behavior, not physical model accuracy.
