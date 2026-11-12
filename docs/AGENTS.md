# Documentation rules

These rules govern documentation under `docs/` and its entry points in README,
the repository AGENTS guide, and MkDocs configuration.

## Readers and ownership

- `en/users/` and `ja/users/` serve engineers using existing features to configure,
  run, and judge design–verification work.
- `en/developers/` and `ja/developers/` serve contributors changing the repository,
  scenarios, tools, simulators, evaluation, or execution infrastructure.
- Give every page one reader and one clear task or explanatory purpose.
- Keep tutorials, task guides, concepts, and reference material distinct.
- A contract has one authoritative explanation; link to it instead of copying it.
- Keep scenario details under that scenario's parent within each reader section.
  The three bundled scenarios have equal status; none defines the project.

## Truth and writing

- Describe the current source, configuration, and tests. Verify commands against
  this checkout, not an unrelated installed package.
- Separate implemented behavior, known limitations, proposed changes, and dated
  experiment evidence. External scenario loading is a development goal, not a
  shipped capability.
- User procedures state prerequisites, inputs, commands, expected outputs, and
  how to judge completion. Reference pages state meaning, defaults, and limits.
- Developer explanations name responsible modules, contracts, extension points,
  failure behavior, and regression checks needed for the next change.
- Distinguish constraints, optimization metrics, model verification, numerical
  agreement, and physical validation. LLM explanations do not establish pass/fail.
- Use task-based navigation and plain language. Dashboards are evidence viewers.
- Reuse useful diagrams, tables, equations, and assets in their owning pages.
  Explain what each visual shows, its source/conditions, and any historical limits.
  Keep recorded assets and data unchanged; verify figures against their captions.
- Keep current English and Japanese pages aligned. Label source-only research
  material by its actual language; do not publish empty translation placeholders.

## Lifecycle and verification

- `_archive/` holds historical research, specifications, and plans. Preserve
  recorded measurements, formulas, conditions, and evidence references.
- Exclude this file and `_archive/` from the normal site and search index.
- Delete obsolete pages. Do not create relocation pages, old-heading appendices,
  compatibility anchors, or redirects to preserve previous documentation layouts.
- Update affected documentation when implementation changes. Run the strict
  MkDocs build and `python scripts/check_docs.py` for links/images/anchors,
  both reader journeys and languages; also run relevant
  CLI dry runs and regression tests. Never regenerate or rescore experiments merely
  to reorganize their documentation.
