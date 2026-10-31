# MuJoCo and One-Piece design loop

One-Piece owns versioned requirements, KDPs, detailed parameters, evidence and decisions. Engineering Agents proposes changes and executes simulation. Existing ECLSS scenarios remain independent.

## Bounded MVP

Automatic hardware changes are restricted to six mechanical variables and registered motor selection. Automatic software changes are restricted to three LQR Q-weight groups (attitude, angular rate, momentum; 0.25–4 times nominal) and yaw gain (0–0.12). R, sensing, timing, timestep, actuator constraints and evaluation code are fixed.

Each small campaign shares a saved controller K. Simultaneous mechanics/control changes receive the four old/new combinations under identical conditions. Native MuJoCo–MJX agreement checks use a fixed timestep without half-step adjudication. Historical half-step evidence retains its original provenance.

Use implementation names for agreement, and hardware names for execution resources. The agreed [future execution policy](simulation_backend_policy.md) qualifies MJX, uses it for broad exploration, and reserves paired checks for finalists, sensitive cases and regression tests. The current runner still pairs every requested MJX candidate; selective execution is not implemented yet. Existing evidence is unchanged.

Native MuJoCo and MJX use the same authoritative stop fields: `contact_loss_stop_s`, `slip_stop_speed_m_s`, `slip_stop_duration_s`, and `pivot_drift_stop_mm`. The legacy source manifest identifies the original code; EN records the current implementation hashes, including corrections to the imported evaluator. Historical results are preserved rather than rewritten by those corrections.

## ENPIRE mapping

1. **EN** pins the One-Piece model, requirements, reset, constraints, verification and code identity. Every rollout starts from its declared initial state.
2. **PI** reads requirements, KDPs and recorded feedback, then proposes a falsifiable hypothesis with the smallest allowed change.
3. **R** executes native MuJoCo and, when requested, MJX on a real GPU. Deterministic code evaluates the results.
4. **E** uses failures and keep/reject decisions to revise a bounded design-search policy: hypothesis, KDP priority and search step. The next PI reads the new revision and persisted feedback.

This applies ENPIRE's frozen-environment feedback structure to configuration search. It does not implement real-robot autoresearch, arbitrary algorithm/code evolution or learned-weight updates. Search-policy evolution cannot edit the evaluator. Humans establish requirements, evaluation conditions and adopted baselines; automatic keep/reject decisions concern development experiments.

Missing MJX execution remains not-run; native MuJoCo results alone never claim implementation agreement. Published confirmation feedback becomes development data when exposed to the next improver.

## Persistence and acceptance

Record configuration identity, parent, hypothesis, diff, controller, trial conditions/seeds, telemetry, failures, decisions and search-policy ancestry. A durable outbox retries recording idempotently. The next iteration re-reads recorded feedback. Defaults are five iterations, twenty new proposals, thirty minutes and a three-iteration stagnation limit. Child rollouts do not recursively spawn designers.

Offline acceptance imports the 2,048 historical designs and reproduces the prior-46 split (31 pass, 9 fail, 6 inconclusive), replays saved controllers on CPU, and runs two Fake LLM iterations with real CPU simulation. Real LLM improvement, new GPU execution and physical fidelity remain separate checks. See the repository README for commands and the One-Piece project for evidence.

## Run locally

Clone the repositories next to each other and restore the One-Piece [evidence pack](https://github.com/hirototamura/one-piece/tree/main/projects/balancing-cube). The contract is JSON Schema 1.0 / package 0.1.1. Install the local One-Piece checkout; a PyPI publication is not assumed.

```sh
python -m pip install -e ../one-piece -e '.[mujoco]'
ea run balancing_cube --backend mujoco_cpu --design-mode none \
  --set ssot.path=../one-piece/projects/balancing-cube/store
python scripts/verify_cube_loop.py \
  --store ../one-piece/projects/balancing-cube/store --output results/cube-offline-check
```

CLI constraints (enforced in `run_mechanical` / `BalancingCubeScenario`): `ssot.path` is required; backends are `mujoco_cpu`/`mjx_gpu` (`cpu`/`gpu` aliases); agent mode is `llm` or `none` only; `--seed` is rejected; `--set` may only change `ssot`, `backend`, `agents`, `iteration`, `output`, `memory`. `--iterate` without a scenario name still selects `ssos_eclss_loop`. List outputs with `ea results --track balancing_cube`.

The default snapshot `cube.simulation.snapshot@bottom-corner-000-20261017-3` uses the three faces incident to supporting corner 000. It retains the tested MASS controller and its exact historical design-plant reference. The comparison design is a lower-face descendant of `D-000544-52890`; historical upper-face results do not apply automatically. The mission remains balancing on all eight corners. See [first-trial evidence and controller choice](bottom_corner_trial.md). `fixed-dt-mvp-2` remains available for explicit historical reproduction. No human baseline is adopted.

`none` evaluates the reference on CPU. The offline script runs two Fake LLM rounds with actual CPU physics and checks persisted feedback. Real proposals use `--design-mode llm --iterate 2 --llm-provider ollama`. GPU execution needs the optional `.[gpu]` dependencies and CUDA, using `--backend mjx_gpu`. Neither real LLM improvement nor the new GPU path has been executed in this acceptance.

Retry pending evidence with `MechanicalBridge(store_path).outbox(run_dir).flush()`. Pending synchronization stops PI. Time budgets cap HTTP timeouts and are checked between CPU cases and before/after GPU batches; an active native solver/JIT call finishes before interruption at the next boundary.

References: [ENPIRE paper](https://arxiv.org/html/2606.19980v2), [autoresearch contract](https://github.com/NVlabs/ENPIRE/blob/main/enpire/policy/autoresearch_instruction.md), [One-Piece system model](https://github.com/hirototamura/one-piece/blob/main/docs/en/SYSTEM_MODEL.md).

## Review corrections

`fixed-dt-mvp-2` corrects ownership and evidence trace metadata from `fixed-dt-mvp-1`; model, saved K, evaluation criteria and the D-000544-52890 reference are unchanged. The reference design and campaign summary (including prior-46 counts) are mandatory context records outside the five-design/eight-evidence limits. Existing acceptance history is retained; new acceptance runs use a temporary copy of the store.

`suggested_search_step` is advisory policy data, not a maximum parent-to-child delta. The compiler enforces absolute mechanical/control ranges. Reference execution failure stops before PI. Requested GPU execution that is unavailable produces an inconclusive run and a nonzero CLI exit; CPU-only operation remains available explicitly. Aggregation errors preserve partial evidence and roll back the best design for an incomplete 2×2 comparison.

CI installs `.[dev,mujoco,onepiece]`, including the SHA-256-pinned 0.1.1 wheel from the One-Piece Release, and requires all Cube tests to execute with zero skips on Python 3.11/3.12. General ECLSS tests remain independent of these optional dependencies.
