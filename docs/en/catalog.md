# Document catalog

Full page index for the MkDocs site. Use the header language switcher for 日本語.

| Section | Page | Content |
| --- | --- | --- |
| Start | [Quick start](index.md) | Install, CLI golden path, result files |
| | [Overview](overview.md) | Project goals, dashboard, detailed setup |
| Design | [Architecture](architecture.md) | Layers, execution flow, agents |
| | [Agent design](agent-design.md) | What the world enforces, what the model decides; memory tiers; LLM contract |
| | [Extending](extending.md) | Backend, scenario, agent mode, world rules, design variable |
| Results | [Experiment record](results.md) | Three 50-round chains, measured |
| | [Roadmap](roadmap.md) | Priorities, each traced to a measurement |
| Specs | [Implementation specs](specs/index.md) | The specs each rebuild was written against, verbatim |
| | [API contracts](api-contracts.md) | JSONL schemas, protocols |
| | [Engineering guide](AGENTS.md) | Mission, coding discipline |
| Scenarios | [scrubber_degradation](scenario-scrubber-degradation.md) | Mock CO₂ scrubber scenario |
| | [ssos_eclss_loop](scenario-ssos-eclss-loop.md) | SSOS live ECLSS scenario |
| SSOS | [SSOS integration](ssos/index.md) | Docker / ROS 2 operational guides |
| | [Roadmap](ssos/roadmap.md) | Phase 0–8 status |
| More | [CLI guide](cli.md) | `ea` command reference |
| | [Development plan](development-plan.md) | Roadmap and backlog index |
| | [Maintenance guide](MAINTENANCE.md) | How to edit and preview docs |
| Memos | [Backlog](memo/backlog.md) | BL-001–BL-007 |
| | [MVP plan](memo/scrubber_degradation/mvp_plan.md) | Scrubber MVP notes |
| | [EPS implementation plan](memo/scrubber_degradation/eps_implementation_plan.md) | EPS bridge notes |
| | [Homogeneous agent team](memo/agents/homogeneous_agent_team_plan.md) | Agent team design |
| | [SSOS ECLSS connection plan](memo/ssos_eclss_loop/ssos_eclss_loop_connection_plan.md) | Phase 0–7 details |
| | [Occupant survival](memo/ssos_eclss_loop/occupant_survival.md) | plant_sim crew/actor attrition |
| | [Labeled rule-base](memo/ssos_eclss_loop/labeled_rule_base.md) | In-sim labeled ops: sized ARS/OGS/WRS, then cap |
| | [Post-run design agent](memo/ssos_eclss_loop/post_run_design_agent.md) | Actor / designer split (as shipped) |
| | [Design agent](memo/ssos_eclss_loop/tool_use_design_agent.md) | Capacity sizing: decision loop, integrity guard, physics gate, candidate re-simulation |
| | [SSOS EPS ROS2 plan](memo/ssos_eclss_loop/ssos_eps_ros2_connection_plan.md) | EPS bridge (Phase 3) |
| | [ROS2 graph investigation](memo/ssos_eclss_loop/ssos_ros2_graph_design_investigation.md) | Launch remap research |
| | [ECLSS physical phenomena](memo/ssos_eclss_loop/ssos_eclss_physical_phenomena_overview.md) | ECLSS physics memo |
| | [EPS physical phenomena](memo/ssos_eclss_loop/ssos_eps_physical_phenomena_overview.md) | EPS physics memo |
| | [Persona LLM OOP plan](memo/agents/persona_llm_core_oop_plan.md) | Persona architecture draft |
| | [Persona workshop draft](memo/agents/persona_workshop_draft.md) | Workshop notes |

GitHub entry points: root [README.md](https://github.com/hirototamura/engineering_agents/blob/main/README.md) and [AGENTS.md](https://github.com/hirototamura/engineering_agents/blob/main/AGENTS.md).

```bash
pip install -e ".[dev]"
mkdocs serve
# → http://127.0.0.1:8000/
```
