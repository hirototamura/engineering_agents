> Japanese: [../ja/memo/backlog.md](../ja/memo/backlog.md)

# Backlog — Research & Design Topics

Topics outside MVP scope that are worth tracking. Implementation priority follows the roadmap in [mvp_plan.md](mvp_plan.md).

---

## BL-001: Labeled Roles vs Emergent Roles (Base Role)

**Status**: Under consideration (Week-1 onward)  
**Related**: Day 4 agent team design, lunar_agents structured communication experiments

### Background

Operational-phase agent teams (Monitor / Diagnostician / Operator / DesignEngineer, etc.) may be nothing more than **human convenience labels for division of labor**. In the MVP we assign **scenario-specific roles** tailored to `scrubber_degradation` to drive anomaly response, but this is a pragmatic choice for demo viability.

### Research questions

| Condition | Hypothesis |
| --- | --- |
| **Labeled** — Explicit assignment of four scenario-specific roles | Faster anomaly response and higher reproducibility. Easier prompt/rule design. |
| **Unlabeled** — Base Role agents (no role name or role instructions) | Role division suited to the situation may **emerge** from telemetry and communication history alone. |
| **Comparison** | Quality of emergence (response speed, design-change validity, communication redundancy) can be quantitatively compared. |

### Value

- Extends lunar_agents’ “structured communication · individuality → emergence” into an **ECLSS resilience loop** context
- Provides evidence for the design choice of assigning roles vs not
- Can connect to One Piece provenance for “who proposed the design change”

### Experiment plan (not scheduled)

1. Same `scrubber_degradation` scenario, same Mock ECLSS
2. **Run A**: `agents.mode: labeled_rule_base` (four roles dedicated to scrubber_degradation)
3. **Run B**: `agents.mode: base` (N Base Role agents, no role YAML)
4. Comparison metrics (draft):
   - Steps to recovery (CO2 < 1000)
   - `messages.jsonl` message_type diversity / self-described role equivalents
   - Number of design changes and final health
   - With LLM: reasoning individuality (reuse lunar_agents metrics)

### Relation to MVP

- **Week-1**: Labeled + rule_based only (no generic role framework)
- **BL-001**: Week-2 onward or post-hackathon. Add `agents.mode: base` when Base Role is implemented
- Together with **BL-002**, forms the foundation for a three-way comparison: fixed heterogeneous / homogeneous N / emergent unlabeled

---

## BL-002: Evolutionary Persona Formation (Homogeneous vs Heterogeneous Teams)

**Status**: Under consideration (after homogeneous N-agent team introduction)  
**Related**: Homogeneous agent team redesign plan, BL-001 (emergent roles), Day 8 persona workshop, hardware development organization theory

### Background

When personas are fixed per role by hand, thinking and behavior tend to converge into rigid patterns (e.g. hold synchronization in the old `labeled_llm` / fixed four-role setup). The MVP avoids this by moving to **homogeneous N agents** (single persona · variable headcount · representative action / post-run design), but **AI-driven evolution and generation of personas** is not yet started.

As a substitute for human teams that develop hardware, the central question is **how to organize which AI (or AI team)** — i.e. **organization theory and team design**.

### Research questions

| Axis | Question |
| --- | --- |
| **Homogeneous vs heterogeneous** | Which improves emergence, recovery, and design proposal quality: all identical personas (homogeneous N) or differentiated personas (heterogeneous N)? Three-way comparison with fixed heterogeneous (current four roles). |
| **Unit of evolution** | Which acts as the “gene”: individual persona / team charter / role-division pattern? |
| **Selection pressure** | How to map simulation KPIs (CO2 recovery, power, post-run design validity) to fitness? |
| **Human-team substitute** | In closed-loop ECLSS and hardware development, which human-team functions (specialization, review, representative decision) should an AI organization reproduce? |

### Value

- Goes beyond hand-written persona rigidity; update team characteristics per run or per generation
- As a middle layer between homogeneous teams (near-term MVP) and heterogeneous/emergent (BL-001), clarifies the design space of **who decides the persona**
- Future connection to One Piece / provenance for “which generation · which individual proposed the design”

### Experiment plan (not scheduled)

1. **Baseline**: Homogeneous N + hand-written single persona (near-term implementation)
2. **Variant A**: Heterogeneous N + evolution-generated personas (random initial population, crossover · mutation)
3. **Variant B**: Homogeneous but only charter / policy evolve (persona body fixed)
4. Compare: recovery steps, design proposal adoption rate (human evaluation), discussion diversity, rigidity metrics (utterance n-gram overlap, etc.)

### Relation to MVP

- **Near term**: Homogeneous N + hand-written persona (no evolution). **Out of implementation scope** for this item
- **BL-002**: After homogeneous team stabilizes. Start from evolution loop, evaluation function, organization design docs

---

## BL-003: (Reserved)

Add future research topics here.
