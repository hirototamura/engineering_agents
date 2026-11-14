# Fixed Cube BOM assessment

This workflow compares a reference BOM with the reviewed One-Piece requirements and runs one frozen numerical configuration. It does not instantiate a design agent, call an LLM, tune the controller or select a hardware baseline.

One-Piece owns the configuration catalogue, BOM, requirement comparison, snapshot and evidence. See its `docs/en/cube_configuration_catalogue.md`. The four catalogue roles distinguish reviewed requirements, the lower-face runtime default, historical multi-agent inputs, and the new BOM reference. The ordinary scenario default is unchanged.

Use the current One-Piece source/package. Older 0.1 wheels do not support the reviewed requirement-to-function allocation links.

```sh
cd engineering_agents
PYTHONPATH=src:../one-piece/src ../.venv-integration/bin/python -m tools.run_cube_bom_reference \
  --store ../one-piece/projects/balancing-cube/store \
  --bom ../one-piece/projects/balancing-cube/references/remrc_bom_20261021.json \
  --output experiments/balancing_cube/results/remrc-bom-reference-NEW-RUN-ID

PYTHONPATH=src:../one-piece/src ../.venv-integration/bin/python -m tools.build_cube_bom_report \
  --run-dir experiments/balancing_cube/results/remrc-bom-reference-NEW-RUN-ID \
  --output ../reports/cube-configuration-catalogue/index.html
```

The runner refuses an existing output directory unless `--resume` is supplied. Resume requires the same inputs, source digests and environment. Completed cases are retained. Use a new configuration revision for changed assumptions, parts, controller or evaluation conditions. The source workbook remains unchanged; the cell-level JSON preserves its SHA-256 and source cells.

`scenario/balancing_cube/bom_reference.py` contains the fixed component mapping, assumption recipe and requirement comparison. `tools/run_cube_bom_reference.py` orchestrates record import, native MuJoCo execution and evidence storage. `tools/build_cube_bom_report.py` renders the same records/results into one portable HTML with case selection, saved-pose 3D replay, charts and JSON downloads.

The 21 October run is `remrc-bom-reference-20261021`. It contains 24 six-second cases from the inherited development matrices and ten separate nominal 30-second diagnostics. The latter use whole-interval tilt RMS and a body-origin drift proxy. They are not hardware verification. The controller is retained from the lower-face study; the reference firmware's PWM gains are not converted into SI torque or executed.

Files include `compiled.json`, `frozen-snapshot.json`, `test-plan.json`, `model.xml`, `environment.json`, `requirements-comparison.json`, `case-summaries.csv`, per-case input/XML/CSV/results, source snapshots and `evidence.zip`. The HTML embeds all 28,460 original sampled points and saved poses, so charts and replay work without a server. The source-code snapshot identifies uncommitted code as well as committed repository state.

Results: 2/12 full-gate passes in each short partition, six losses of balance, and ten successful nominal 30 s numerical hold analogues. Twenty short cases exceed the assumed torque-workload threshold. That is a numerical comparison result, not a calibrated motor thermal limit.
