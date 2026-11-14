# Open and maintain a report library

The report library discovers existing workspace HTML reports and builds a searchable catalog. It is an inspection aid; it does not run simulations or replace their source evidence.

## Build or serve the catalog

Choose the workspace containing your project folders explicitly:

```bash
PYTHONPATH=src python -m tools.cli reports build --workspace /path/to/workspace
PYTHONPATH=src python -m tools.cli reports serve --workspace /path/to/workspace --port 8765 --open
```

`build` writes `reports/index.html`, language-specific catalog pages, and `reports/catalog.json` under that workspace. `serve` rescans on refresh and opens the catalog at `http://127.0.0.1:8765/reports/index.html`. Stop the server with Ctrl-C. Source HTML reports are not edited by catalog building.

`EA_REPORT_WORKSPACE` sets the workspace when `--workspace` is omitted. Otherwise the current directory is used, except that running in `engineering_agents` beside a `one-piece` directory selects their parent. An explicit workspace makes repeatable use clearer.

## Optional translations and thumbnails

```bash
PYTHONPATH=src python -m tools.cli reports translate --workspace /path/to/workspace --prepare-only
PYTHONPATH=src python -m tools.cli reports verify --workspace /path/to/workspace
PYTHONPATH=src python -m tools.cli reports capture --workspace /path/to/workspace
```

Translation preparation counts text without contacting a model. Actual translation uses the configured translation endpoint (`--endpoint`, default `http://127.0.0.1:18001`) and a fixed model in the report translator; it does not inherit the simulation's LLM settings. It creates derived language views and a translation manifest. Thumbnails require a working browser-capture environment. Use module-specific help for action details, for example `PYTHONPATH=src python -m tools.report_library.translate_reports --help`.

Check translated labels against the original evidence and run `verify` before sharing. A translated report does not create new measurements or change the validity of the underlying experiment. For the meaning of a report's metrics, return to its owning [scenario](../scenarios/index.md).

## Know which layer you are reading

| Layer | Typical artifact | Meaning |
| --- | --- | --- |
| Measured source | Run JSON/JSONL and frozen inputs | Conditions and observations to audit |
| Scenario report | `evaluation.html`, cube campaign report | A view of one declared evaluation |
| Reading copy | Translated report and manifest | Different language, same underlying measurements |
| Catalog | `reports/catalog.json`, catalog HTML | Discovery and navigation across reports |
| Thumbnail | Captured report image | Preview, not a substitute for the complete record |

If a catalog result looks promising, follow it into the report and then into the source evidence. A thumbnail cannot show a missing case or changed denominator, and a translation cannot resolve an inconclusive result.
