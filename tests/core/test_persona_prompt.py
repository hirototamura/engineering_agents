from core.agents.base import DeliberationContext, Persona
from core.agents.persona import PersonaPromptBuilder, message_contract
from core.agents.types import AgentMessage, DeliberationPhase


def test_persona_prompt_includes_memory_discourse_and_markers():
    persona = Persona(
        agent_id="monitor",
        main_role="Environmental sentinel",
        persona="Speak when CO2 drifts.",
    )
    ctx = DeliberationContext(
        step=5,
        phase=DeliberationPhase.INITIAL,
        situation="step=5, co2_ppm=950",
        step_discourse=[],
        team_discourse=[
            AgentMessage(
                step=4,
                from_role="diagnostician",
                to_role="operator",
                message="degradation suspected",
                message_type="diagnosis",
            )
        ],
        agent_memory=["step 3: noted rising CO2"],
    )
    prompt = PersonaPromptBuilder.build(
        persona,
        ctx,
        message_contract(),
        "Open forum.",
    )
    assert "agent_id: monitor" in prompt
    assert "phase: deliberation_initial" in prompt
    assert "Main role: Environmental sentinel" in prompt
    assert "Speak when CO2 drifts." in prompt
    assert "degradation suspected" in prompt
    assert "noted rising CO2" in prompt
    assert "## Your memory" in prompt
    assert "## Team discourse" in prompt
    assert "at most 60 words" in prompt
    assert "at most 80 words" in prompt
