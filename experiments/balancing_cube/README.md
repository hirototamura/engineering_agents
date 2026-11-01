# Balancing-cube experiments

This folder contains the reports and evidence from balancing-cube simulation
campaigns. The scenario implementation remains under `src/scenario/`.

New runs are written to `experiments/balancing_cube/results/<run_id>/` by
default. List them with `ea results --track balancing_cube`. Use
`EA_RESULTS_ROOT` or the CLI's `--results-root` option when a run needs a
different storage location.

Run artifacts are ignored by Git because they can include large telemetry,
trajectories, and replay data. Publish curated, hash-identified evidence packs
separately when they need to be shared.
