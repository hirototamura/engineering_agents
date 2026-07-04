## Summary

<!-- What changed and why (mission / design-verification loop). -->

## Checklist

- [ ] `./scripts/ci-local.sh` or equivalent pytest run completed
- [ ] No upward layer imports (`environment/` has no LLM/Persona; see `tests/test_layer_imports.py`)
- [ ] Virtual-world pass/fail is not decided by LLM subjectivity
- [ ] JSONL / API changes update [docs/en/api-contracts.md](docs/en/api-contracts.md) and [docs/ja/api-contracts.md](docs/ja/api-contracts.md)
- [ ] Doc changes keep en/ja pairs in sync (see `tests/test_docs_bilingual_pairs.py`)
- [ ] `src/tools/cli/` changes update [docs/en/cli.md](docs/en/cli.md) and [docs/ja/cli.md](docs/ja/cli.md)
- [ ] RunSpec or exit-code changes update `tests/tools/` and `tests/scenario/test_run_spec.py`
