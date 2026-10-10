# MuJoCo and One-Piece design loop

One-Piece owns versioned requirements, KDPs, detailed parameters, evidence and decisions. Engineering Agents proposes changes and executes simulation. Existing ECLSS scenarios remain independent.

## Bounded MVP

Automatic hardware changes are restricted to six mechanical variables and registered motor selection. Automatic software changes are restricted to three LQR Q-weight groups (attitude, angular rate, momentum; 0.25–4 times nominal) and yaw gain (0–0.12). R, sensing, timing, timestep, actuator constraints and evaluation code are fixed.

Each small campaign shares a saved controller K. Simultaneous mechanics/control changes receive the four old/new combinations under identical conditions. New CPU/GPU checks use a fixed timestep without half-step adjudication. Historical half-step evidence retains its original provenance.

CPU and MJX use the same authoritative stop fields: `contact_loss_stop_s`, `slip_stop_speed_m_s`, `slip_stop_duration_s`, and `pivot_drift_stop_mm`. The legacy source manifest identifies the original code; EN records the current implementation hashes, including corrections to the imported evaluator. Historical results are preserved rather than rewritten by those corrections.

## ENPIRE mapping

1. **EN** pins the One-Piece model, requirements, reset, constraints, verification and code identity. Every rollout starts from its declared initial state.
2. **PI** reads requirements, KDPs and recorded feedback, then proposes a falsifiable hypothesis with the smallest allowed change.
3. **R** executes native MuJoCo and, when requested, MJX on a real GPU. Deterministic code evaluates the results.
4. **E** uses failures and keep/reject decisions to revise a bounded design-search policy: hypothesis, KDP priority and search step. The next PI reads the new revision and persisted feedback.

This applies ENPIRE's frozen-environment feedback structure to configuration search. It does not implement real-robot autoresearch, arbitrary algorithm/code evolution or learned-weight updates. Search-policy evolution cannot edit the evaluator. Humans establish requirements, evaluation conditions and adopted baselines; automatic keep/reject decisions concern development experiments.

Missing GPU execution remains not-run; CPU results never claim GPU agreement. Published confirmation feedback becomes development data when exposed to the next improver.

## Persistence and acceptance

Record configuration identity, parent, hypothesis, diff, controller, trial conditions/seeds, telemetry, failures, decisions and search-policy ancestry. A durable outbox retries recording idempotently. The next iteration re-reads recorded feedback. Defaults are five iterations, twenty new proposals, thirty minutes and a three-iteration stagnation limit. Child rollouts do not recursively spawn designers.

Offline acceptance imports the 2,048 historical designs and reproduces the prior-46 split (31 pass, 9 fail, 6 inconclusive), replays saved controllers on CPU, and runs two Fake LLM iterations with real CPU simulation. Real LLM improvement, new GPU execution and physical fidelity remain separate checks. See the repository README for commands and the One-Piece project for evidence.

## Run locally

Clone the repositories next to each other and restore the One-Piece [evidence pack](https://github.com/hirototamura/one-piece/tree/main/projects/balancing-cube). The contract is JSON Schema 1.0 / package 0.1.0. Install the local One-Piece checkout; a PyPI publication is not assumed.

```sh
python -m pip install -e ../one-piece -e '.[mujoco]'
ea run balancing_cube --backend mujoco_cpu --design-mode none \
  --set ssot.path=../one-piece/projects/balancing-cube/store
python scripts/verify_cube_loop.py \
  --store ../one-piece/projects/balancing-cube/store --output results/cube-offline-check
```

The default snapshot `cube.simulation.snapshot@fixed-dt-mvp-1` pins the existing paired numerical best `D-000544-52890` as comparison reference. The nominal LQR linearization plant and historical saved K remain fixed. This reference selection does not adopt a human baseline.

`none` evaluates the reference on CPU. The offline script runs two Fake LLM rounds with actual CPU physics and checks persisted feedback. Real proposals use `--design-mode llm --iterate 2 --llm-provider ollama`. GPU execution needs the optional `.[gpu]` dependencies and CUDA, using `--backend mjx_gpu`. Neither real LLM improvement nor the new GPU path has been executed in this acceptance.

Retry pending evidence with `MechanicalBridge(store_path).outbox(run_dir).flush()`. Pending synchronization stops PI. Time budgets cap HTTP timeouts and are checked between CPU cases and before/after GPU batches; an active native solver/JIT call finishes before interruption at the next boundary.

References: [ENPIRE paper](https://arxiv.org/html/2606.19980v2), [autoresearch contract](https://github.com/NVlabs/ENPIRE/blob/main/enpire/policy/autoresearch_instruction.md), [One-Piece system model](https://github.com/hirototamura/one-piece/blob/main/docs/en/SYSTEM_MODEL.md).
