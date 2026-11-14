# Maintain the documentation

Documentation is part of the change contract. A reader should be able to configure and judge an existing feature, or find the implementation boundary for changing it, without reconstructing a research notebook.

## Assign the reader and purpose

`users/` serves engineers configuring, running, and interpreting existing design–verification work. `developers/` serves contributors changing code, scenarios, tools, backends, evaluation, and execution infrastructure. Give each page one purpose: a tutorial to complete a first task, a guide to perform a specific change, a concept to explain a boundary, or a reference to define exact behavior.

Task-oriented entry points and separation of guides from reference take structural inspiration from the [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart) and [Claude documentation](https://platform.claude.com/docs/ja/home). The project retains its own terminology, content, and navigation.

Scenario-specific content belongs under that scenario within each reader section. Treat scrubber, SSOS, and balancing cube equally. Public CLI, configuration, and artifact definitions have one owner in user reference; developer pages explain internal contracts and link to it.

## Write from current evidence

Read the source and tests in this checkout. Distinguish implemented behavior, limitations, planned work, and dated measurements. For a user procedure, specify prerequisites, inputs, command, expected evidence, and completion judgment. For a developer guide, identify modules, contracts, failure behavior, extension points, and regression checks.

Keep English and Japanese page structures and claims aligned. Source-only research material keeps its real language label rather than an empty translation page. Historical plans, specifications, and reports belong under `_archive/`, excluded from normal publishing and search; extract current useful knowledge into maintained pages with its source/test basis. Preserve original experiment measurements and conditions.

## Verify the reader journeys

Follow the source [documentation rules](https://github.com/hirototamura/engineering_agents/blob/main/docs/AGENTS.md) and [contributor guide](https://github.com/hirototamura/engineering_agents/blob/main/AGENTS.md). Check mirrored paths, navigation, relative links, images, anchors, source references, and both user/developer journeys. Run `python -m mkdocs build --strict`, then `python scripts/check_docs.py`. The checker verifies audience/language parity, generated links and anchors, reader journeys, language switching, and exclusion of internal rules and archives from publication/search. Use CLI help and dry runs to check documented options without regenerating experiments. Run relevant regression tests for any behavioral claims changed by the code.

Delete obsolete published pages. Do not retain relocation stubs, old-heading appendices, compatibility anchors, or redirects. Never regenerate or rescore recorded experiments merely to reorganize their documentation.
