from core.agents.memory import AgentMemory, DiscourseBuffer, TeamMemoryStore
from core.agents.types import AgentMessage, StepAgentOutcome
from environment.protocol import CommandKind, RecoveryCommand


def test_agent_memory_trims_to_limit():
    mem = AgentMemory(agent_id="monitor", limit=3)
    for i in range(5):
        mem.append(f"entry {i}")
    assert mem.recent() == ["entry 2", "entry 3", "entry 4"]


def test_discourse_buffer_trims_to_window():
    buf = DiscourseBuffer(window=2)
    for i in range(3):
        buf.extend(
            [
                AgentMessage(
                    step=i,
                    from_role="monitor",
                    to_role="team",
                    message=f"m{i}",
                    message_type="alert",
                )
            ]
        )
    assert len(buf.recent()) == 2
    assert buf.recent()[0].message == "m1"


def test_team_memory_store_commit_step():
    store = TeamMemoryStore(agent_ids=["operator"], memory_limit=4, discourse_window=4)
    outcome = StepAgentOutcome(
        messages=[
            AgentMessage(
                step=1,
                from_role="operator",
                to_role="team",
                message="Boost fan",
                message_type="recovery_command",
                reasoning="CO2 high",
                metadata={"deliberation_phase": "action", "llm_memory": "watch bypass"},
            )
        ],
        commands=[
            RecoveryCommand(kind=CommandKind.SET_FAN_SPEED, value=1.0, issued_by="operator")
        ],
    )
    store.commit_step(outcome)
    assert len(store.discourse.recent()) == 1
    entries = store.agent_memories["operator"].recent()
    assert any("watch bypass" in e for e in entries)
    assert any("set_fan_speed" in e for e in entries)
