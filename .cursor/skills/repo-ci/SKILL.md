# repo-ci

Local and CI verification for this repository. **Policy:** [docs/ja/AGENTS.md](../../docs/ja/AGENTS.md) — do not duplicate rules here.

## Full CI mirror

```bash
./scripts/ci-local.sh
# = ci.yml (ruff + pytest + discipline) + docs.yml (mkdocs --strict)
```

## Targeted pytest

```bash
pytest tests/scenario/test_scrubber_baseline.py tests/scenario/test_scrubber_with_agents.py -q
pytest tests/scenario/test_ssos_eclss_loop.py -q
pytest tests/tools/ -q
```

## CLI quick runs

```bash
python3 -m tools.cli doctor          # local only (Docker/Ollama)
python3 -m tools.cli scenarios
python3 -m tools.cli run scrubber_degradation --agents-mode none --steps 2 --quiet
```

## Closed-loop smoke (ssos_eclss_loop, mock)

```bash
python3 -m tools.cli run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base \
  --steps 20 --run-id smoke-run1
python3 -m tools.cli run ssos_eclss_loop --backend mock --agents-mode labeled_rule_base \
  --steps 5 --run-id smoke-run2 \
  --apply-proposals src/experiments/results/smoke-run1/design_proposals.json
```

Use distinct `--run-id` values.

## SSOS Tier 2 (optional)

```bash
SSOS_E2E=1 ./scripts/run_ssos_regression.sh
```

## api-contracts checklist

- [ ] Updated docs/en/api-contracts.md and docs/ja/api-contracts.md
- [ ] CLI flag changes reflected in docs/en/cli.md and docs/ja/cli.md
