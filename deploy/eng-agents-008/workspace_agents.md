# Eng Agents 008 — development handover

Read the repository's own AGENTS.md before changing its files. Read
`engineering_agents/deploy/eng-agents-008/README.md` for environment commands,
locked source revisions, test evidence, and known limits.

The workspace contains three independent repositories:
- `engineering_agents`: design proposals, bounded experiment loops, model adapters, reports and website.
- `one-piece`: requirements, system model, versioned evidence and human decisions.
- `balancing-cube-simulation`: standalone simulator, launch tools and reference CAD source.

Use GitHub branches and reviewable commits for handovers. Keep large results in
checksummed private Release assets. Never commit tokens, model weights, virtual
environments or mutable agent memory. Do not overwrite another environment's work.

GPU 6 (UUID `GPU-8a14a4ef-ac77-553a-206d-55efbf82617b`) is reserved for this profile.
GPUs 0–5 serve an existing model; GPU 7 remains available for other work.
Use CUDA for local model inference and MJX, NVIDIA EGL/OpenGL for rendering,
and Blender OptiX for RTX ray tracing. Fail visibly when the requested accelerated
backend is unavailable; do not silently replace it with software rendering.
Native MuJoCo dynamics, CAD kernels, orchestration, and I/O still use CPU code.
Report those distinctions honestly. GPU visibility variables are configuration,
not a security boundary or a scheduling lock; recheck availability before new work.

OpenShell is intentionally disabled at the user's request. Do not install Docker,
upgrade the kernel, or reboot this server to enable it. Hermes uses the local
terminal backend with host user privileges. Keep approval prompts enabled.
Do not let the agent alter its own approval settings or expand permissions.

The mission is a cube that can eventually balance on any of eight corners.
The first physical trial uses three lower-face reaction wheels. The reference
STLs/BOM contain assumptions and unverified interfaces; numerical simulations
are not physical acceptance. Humans set requirements and adopted baselines.
Never edit One-Piece CORE.md without specific human approval. Deterministic
measurements and requirement checks decide simulation outcomes, not LLM opinions.

Historical reports and experiments are preserved. New development writes new run
directories. Do not silently rewrite previous measurements, IDs, or provenance.

ECLSS experiments live under `engineering_agents/experiments/eclss/`; cube
experiments live under `engineering_agents/experiments/balancing_cube/`. Classify
compatibility runs by their recorded scenario, not a folder-name guess.
One-Piece owns the requirements explorer and the dataset retrieval catalog.
Use `onepiece datasets list/fetch/verify` for historical validation evidence;
never copy the entire `integration-validation` scratch workspace as a new source
repository. Browser review proposals do not change canonical requirements.
