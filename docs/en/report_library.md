# Bilingual report library

Engineering Agents owns the report-library implementation in
`src/tools/report_library/`. One-Piece owns the versioned engineering records.
The library is a derived presentation of files in a selected workspace. It does
not approve requirements, alter simulation results, or establish a baseline.

## Build and open the collection

Install Engineering Agents, then select the directory that contains its project
folders. No developer-specific absolute path is required.

```sh
ea reports build --workspace /path/to/workspace
ea reports serve --workspace /path/to/workspace --port 8765 --open
# Equivalent module entry point:
python -m tools.report_library --workspace /path/to/workspace build
```

The output is `/path/to/workspace/reports/`. The English and Japanese indexes are
`en/index.html` and `ja/index.html`. `index.html` opens the last selected language.
The server binds to `127.0.0.1`; it is an optional local viewer, not an engineering
record service. Source HTML files remain in their project directories.

## Latest report per title

The main collection displays one report for each matching title. Matching
normalizes Unicode, letter case and whitespace. Known English/Japanese title
aliases join the same group. Distinct numbered titles remain separate. The most
recent source-file modification time selects the displayed version. Equal times
use the source path as a deterministic tie-breaker. Copying a file can change its
modification time; this is a presentation rule, not semantic design versioning.

Older versions remain in `catalog.json` and the **All HTML files** view. The source
records and their evidence are unchanged. Current counts are 15 latest main
entries from 29 source reports, plus documentation and archived HTML.

## Reading copies and page previews

```sh
ea reports translate --workspace /path/to/workspace --endpoint http://127.0.0.1:18001
ea reports verify --workspace /path/to/workspace
ea reports capture --workspace /path/to/workspace
```

Translation explicitly calls the configured Qwen endpoint. It reuses a local
translation cache. No LLM is needed to browse, build the catalog or capture
previews. `translation_manifest.json` pins source hashes and reading-copy paths.
The language, library and source controls use native links. Relative source links
are repaired without changing toolbar destinations. Numeric JSON values, IDs,
code and long raw evidence blocks keep their recorded content. Translated prose
is a reading aid; canonical English requirements and exact source records retain
their authority.

Chrome or Chromium captures each page in an isolated temporary profile. The
1440 × 900 viewport becomes a 720 × 450 WebP thumbnail. Translated reports have
separate English/Japanese previews. `thumbnail_manifest.json` records capture
paths, times and source file versions. New or changed pages are captured in the
background while the local catalog is open. Failed captures remain missing and
are retried; they are not replaced with fabricated report images.

## Repository and artifact ownership

- Commit Python, the HTML template, tests and documentation to Engineering Agents.
- Commit compact canonical records and evidence indexes to One-Piece.
- Keep generated reading copies, thumbnails, caches, catalogs, trajectories and
  validation workspaces out of Git. Store reproducible evidence packs as Release
  assets and retain SHA-256 values in the project evidence index.
- Keep the standalone historical simulator and its launch tools in
  `hirototamura/balancing-cube-simulation`. Engineering Agents contains the current
  integrated execution path and records its original physics provenance.

The top-level `reports/*.py` files in an existing workspace are compatibility
entry points. Maintained implementations are installed with Engineering Agents.
The standalone collection can be rebuilt after restoring its report sources and
generated translation artifacts from an evidence pack.

## Published collection

The [retrieval index](../data/report_library_20261012.json) pins the collection
and campaign archives by SHA-256. Extract the collection into an empty workspace
and open `reports/index.html`. It includes the indexed source HTML, reading
copies, thumbnails and report assets. Install Engineering Agents to rescan the
workspace or capture new previews. The two separate campaign archives retain
the ten- and twenty-round execution data.
