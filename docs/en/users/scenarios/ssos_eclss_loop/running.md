# Run and compare ECLSS designs

For local handoff behavior, use the [mock quickstart](../../quickstart.md). For plant-based evidence, the base installation is sufficient; `plant_sim` requires neither ROS2 nor a model service when both modes are labeled or disabled.

## Run one measured baseline

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --design-mode labeled_rule_base \
  --steps 50 --run-id plant-baseline-01 --set iteration.enabled=false --dry-run --json
```

Review the plan, then remove `--dry-run --json`. Keep its directory. Inspect `summary.json` and `evaluation.json` before deciding whether to apply the emitted proposal.

## Apply a reviewed proposal

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend plant_sim --actor-mode labeled_rule_base --design-mode labeled_rule_base \
  --steps 50 --run-id plant-applied-01 --set iteration.enabled=false \
  --apply-proposals experiments/eclss/results/plant-baseline-01/design_proposals.json
```

Use the same initial conditions, thresholds, horizon, fault schedule, and evaluation version. If the proposal is provisional, read its approval reasons before adding `--approve-provisional`. Applying a proposal changes the in-memory configuration and writes a consumed snapshot; it does not edit the bundled YAML. Unsupported domain/backend changes fail. By default, status-blocked proposals are refused; manual `--approve-provisional` can bypass even `rejected_final` status blocking and does not guarantee engineering bounds. Review [adoption limitations](../../guides/design-iterations.md) before using it.

Compare the applied configuration and observations, not just proposal text. Capacity changes require `plant_sim` for their capacity effect. A mock can exercise action-profile and handoff behavior but cannot establish that a larger plant works.

## Run a chain

Use [design iterations](../../guides/design-iterations.md) to run bounded automatic rounds and paired replays. Always use a new chain ID to retain earlier children and memory; `--no-recreate` is not chain resume.

## Prepare ROS2 SSOS

Use a working Docker daemon and the prebuilt SSOS image. On macOS, Docker Desktop or Colima can provide the daemon. From the repository root, the supplied helper pulls the image and creates a persistent container:

```bash
bash scripts/ssos/mac/ssos-run-detached.sh
PYTHONPATH=src python -m tools.cli doctor
```

The helper replaces an existing container named `ssos` (or `SSOS_CONTAINER_NAME`), so choose a separate name if it contains work you need. It mounts repository `src` at `/ea/src`, `experiments/eclss/results` at `/ea/results`, and the scripts in `scripts/ssos/` as `/root/ssos-container-setup.sh`, `/root/ssos-eclss-headless.sh`, `/root/ssos-headless.launch.py`, and `/root/ssos-eps.launch.py`. Other hosts need the equivalent image, mounts, and startup setup. If the container is merely stopped, use `docker start ssos` instead of recreating it.

Run from the host after the mount checks pass:

```bash
PYTHONPATH=src python -m tools.cli run ssos_eclss_loop \
  --backend ros2 --actor-mode labeled_rule_base --design-mode labeled_rule_base \
  --steps 50 --run-id ros2-review-01 --set iteration.enabled=false
```

The host runner restarts the headless simulation for each run and permits one run per container. Use `--run-id` with the mounted results root; host ROS2 rejects `--output-dir` and roots outside the repository's mounted `experiments/eclss/results`. Unset an incompatible `EA_RESULTS_ROOT`. A ROS2 run is not eligible for the plant-specific full scorecard.

Completion means you retained the baseline and applied-run evidence and can explain the [evaluation status and limitations](results.md). A command exit or a positive narrative alone is not verification.

## Select a run path for the evidence you need

| Task | Backend and execution shape | Completion evidence |
| --- | --- | --- |
| Demonstrate handoff | Mock, two distinct single runs | Consumed proposal and changed effective input |
| Compare plant sizing | Plant_sim, matched conditions | New telemetry, valid evaluation, applied capacity |
| Explore capacity choices | Plant_sim chain | Numbered runs, selected measured design, replay status |
| Exercise SSOS actions | ROS2, one host/container run | Storage telemetry and accepted/rejected operations |

A short mock is appropriate for plumbing; extending its duration does not turn it into plant verification. A ROS2 action completing does not make the plant-specific survival score applicable. Select the path before using the command's exit status as evidence.
