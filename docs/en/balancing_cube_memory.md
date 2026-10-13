# Evidence memory for cube development campaigns

The cube scenario can use persistent memory during design iteration. One-Piece remains the source of truth for requirements, KDPs, fixed model values and evidence revisions. Memory supplies a bounded projection of past experiments to the proposer. It does not approve requirements or establish a baseline.

The design adapts [Agent Memory Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques), particularly episodic memory (09), semantic memory (10), working memory (12), self-reflection (16), retrieval (20) and cross-session memory (21). It uses deterministic retrieval for this small dataset and needs no vector database or embedding service.

Each episode records its proposal, compiled configuration digest, measured feedback, source references and unverified LLM hypothesis. A hash-chained JSONL journal preserves episodes. Retrieval combines recent episodes, the highest measured score, matching configurations and relevant diverse failures. Semantic consolidation summarizes measured counts and failure frequencies; it does not convert a proposed causal mechanism into an established fact. Previous run summaries and proposal files seed cross-session memory.

The full One-Piece context is archived at each proposal. The prompt retains exact English obligations, KDPs, fixed execution conditions and the pinned historical campaign summary. Bounded memory replaces repeated candidate and simulation histories. Japanese translations and older policy repetitions remain available in the full context. The structured prompt never authorizes edits to evaluation conditions.

Defaults remain five rounds, twenty candidates, thirty minutes and three stagnant rounds. Explicit configuration permits at most twenty rounds, eighty configurations and two hours, with a stagnation ceiling of twenty. These are execution budgets, not engineering requirements. Joint mechanical and controller changes still require all four factorial cells. Saved controller matrices and control periods remain fixed within each small campaign. New experiments never perform half-step adjudication.

Enable `memory.enabled`, supply `memory.seed_runs` and set `iteration.proposal_retries` to allow bounded repair of invalid or duplicate proposals. Repairs retain their actual prompts and rejection reasons. Rejected or failed proposals do not count as completed measured iterations. Completed stage sequences remain EN, PI, R and E.

For the configured server, [the launcher](https://github.com/hirototamura/engineering_agents/blob/codex/mujoco-evidence-loop/scripts/run_cube_gpu_memory.sh) invokes the normal Engineering Agents CLI with Qwen-27B on the vLLM endpoint at port 8001. GPUs 6 and 7 serve the model; explicit `EA_MJX_GPU_IDS=0,1,2,3,4,5` distributes simulation cases across the remaining devices. Worker caches persist between candidates. CPU and GPU execute the same cases, seeds and saved controller. A missing or failed shard cannot produce GPU verification success.

Set `EA_LLM_TRACE_DIR` to capture actual fitted prompts, their hashes, generation settings, final JSON, timings, usage and finish reasons. API credentials and private reasoning text are excluded. GPU telemetry records observed utilization; allocating six simulation devices does not imply that a small twelve-case matrix saturates them.

Six-second numerical trials and CPU/GPU agreement do not demonstrate a thirty-second physical hold, calibrated sensor behavior or physical fidelity. Humans retain adoption authority.
