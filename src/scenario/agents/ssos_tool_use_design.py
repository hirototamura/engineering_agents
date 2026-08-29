"""Post-run ECLSS capacity design agent (design doc §4, §5, §10; spec §5-§10).

The designer decides what to build. It does not decide how the review is run.

Each turn it is handed one freshly assembled picture of where the design stands
and answers one of two things: try this sizing, or finish. Everything else --
reading the run, computing what the crew needs, checking constraints,
re-simulating, auditing the physics, comparing -- happens in fixed order, in
code, for every candidate.

That division is the whole point. When the model also chose which tool to call
next, an observed run spent twenty-one turns re-checking the same constraint
and finished with one candidate, because nothing in the loop obliged it to
move on. It cannot now: it is never asked.

The Expert Context Pack states the minimum domain facts, not a procedure. A
model that cannot be read is asked once more and then handed to the
deterministic fallback, which keeps every candidate already verified.

Self-hosted vLLM / Ollama cannot be relied on for native function calling, so
the protocol is a plain JSON contract parsed by :mod:`core.llm.parsing`.

Every decision is written down whole -- what the model said, what it reasoned,
and whatever thinking the provider exposed -- alongside every tool call the
code made on its behalf. A design nobody can retrace is not reviewable.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.agents.types import AgentMessage, DeliberationPhase
from core.llm.base import LLMClient, LLMGeneration, invoke_llm
from core.llm.parsing import combine_thinking, extract_thinking_text, parse_json_response
from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_eval import (
    STATUS_APPROVED,
    STATUS_PROVISIONAL,
    STATUS_REJECTED,
)
from scenario.ssos_eclss_loop.design_proposals import DESIGN_DOMAIN
from scenario.ssos_eclss_loop.design_state import (
    build_design_state,
    candidate_hash,
    find_duplicate,
    normalize_fields,
)
from scenario.ssos_eclss_loop.design_tools import DesignToolContext, DesignToolkit
from scenario.ssos_eclss_loop.design_variables import CAPACITY_KEYS, read_capacity_fields

DESIGN_FAMILY = "capacity_sizing"

# Named apart from the per-step design_state.jsonl the run already writes.
DESIGN_STATE_FILENAME = "design_decision_state.json"

DEFAULT_MAX_DECISIONS = 2
DEFAULT_MAX_PARSE_RETRIES = 1
DEFAULT_MAX_CANDIDATE_RUNS = 1

# Asking the model is the only slow thing in the loop: the nine tools together
# take about three seconds, one question takes about seventy. So the question
# is what gets budgeted, and a repair counts against it -- a reply that had to
# be asked for twice cost the run twice.
DEFAULT_MAX_LLM_CALLS = 2

# The audit record keeps what the model actually said. Clipping a rationale to
# a couple of sentences saves nothing and loses the design intent, which is the
# one thing the record exists for.
_RAW_RESPONSE_LOG_CHARS = 12000
_RESULT_EXCERPT_CHARS = 8000

EXPERT_CONTEXT_PACK = """\
### Expert context pack (domain minimum, not a procedure)
- Objective: every occupant must survive — a design that loses one is never adopted,
  whatever it saves. Among designs where everyone comes back, the scorecard decides,
  and nothing else is compared. Mass, cost, and time spent in the warning bands are
  all marked inside that score, so a heavier machine has to earn its weight back
  somewhere else on the sheet. So do not stop at the first design that works; read
  where the score was lost and aim at that.
- A low score is a statement about what to change, not a request for more capacity.
  Each candidate reports which axes lost the most marks. Growing a subsystem that is
  already covering its demand costs marks on mass and cost and buys nothing.
- Capacity is not free and not one-way. Spare throughput is mass, volume and cost the
  station carries for nothing, so sizing a subsystem *down* is a legitimate design
  move — the candidate re-simulation is what tells you whether it was too far.
- The only design variables are ARS CO2 removal capacity, OGS O2 generation capacity
  and WRS feed capacity per operation. Recovery efficiencies, Sabatier conversion,
  crew metabolism and health thresholds are NOT design variables — do not propose them.
- ARS sizes CO2 removal, OGS sizes O2 generation, WRS sizes water recycling.
- A subsystem is busy for ceil(operation_seconds / step_seconds) steps after each
  action, so actions per day are bounded: nameplate alone does not tell you throughput.
- Raising OGS capacity does nothing while ogs_goal.input_water_mass stays small;
  raising WRS capacity does nothing while wrs_goal.urine_volume stays small.
  Applying a capacity_profile re-syncs both payloads for you.
- summary.json alone is not enough evidence. Look at the time series, the dwell in
  warning / critical bands, the shortfall ledgers and the crew loss causes.
- Only a candidate that has been re-simulated may become the final proposal.
- One verified candidate is the minimum, not the goal. While candidate runs remain,
  size another one and compare: a candidate that still loses occupants has to grow,
  and one that saves everyone is worth testing smaller. The comparison tool picks the
  winner; naming a different candidate in your final_proposal will not change it."""


DECISION_CONTRACT = """Reply with ONE JSON object and nothing else. There are exactly two answers.

To try a design:
{"decision": "propose_candidate",
 "rationale": "why this sizing, from the state above",
 "fields": {"<design variable>": <number>}}

To stop:
{"decision": "finish",
 "rationale": "why this one",
 "selected_candidate_id": "<a candidate that was simulated>"}

You do not choose what happens next. Every candidate you propose is checked,
simulated, audited and compared automatically before you are asked again, and
the winner is decided by the ranking, not by your pick. Capacity fields are
limited to %s.""" % json.dumps(list(CAPACITY_KEYS))


@dataclass
class ToolUseSettings:
    enabled: bool = False
    # Optional overrides merged over design.llm for the decision loop only.
    llm_overrides: Dict[str, Any] = field(default_factory=dict)
    # A decision emits a small JSON object, so the classic designer's large
    # completion budget only buys thinking tokens -- and a turn that spends
    # them all can exceed the HTTP timeout and come back empty.
    # One decision per candidate plus one to stop. The old budget counted
    # tool calls, which is why a model that kept re-checking the same
    # constraint could spend twenty turns without designing anything.
    max_decisions: int = DEFAULT_MAX_DECISIONS
    max_parse_retries: int = DEFAULT_MAX_PARSE_RETRIES
    max_candidate_runs: int = DEFAULT_MAX_CANDIDATE_RUNS
    # Hard ceiling on questions per review, repairs included. Reaching it is
    # not a failure: the run adopts the best design it has verified and moves
    # on, which is what the next iteration is for.
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS
    candidate_actor_mode: str = "inherit"
    candidate_steps: Optional[int] = None
    plots_enabled: bool = True

    @classmethod
    def from_design_config(cls, design_cfg: Mapping[str, Any]) -> "ToolUseSettings":
        raw = design_cfg.get("tool_use")
        raw = raw if isinstance(raw, Mapping) else {}

        def as_int(key: str, default: int) -> int:
            try:
                value = int(raw.get(key, default))
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        steps = raw.get("candidate_steps")
        try:
            candidate_steps = int(steps) if steps is not None else None
        except (TypeError, ValueError):
            candidate_steps = None
        llm_overrides = raw.get("llm")
        loop = raw.get("decision_loop")
        loop = loop if isinstance(loop, Mapping) else {}

        def loop_int(key: str, default: int) -> int:
            try:
                value = int(loop.get(key, default))
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        return cls(
            enabled=bool(raw.get("enabled", False)),
            llm_overrides=dict(llm_overrides) if isinstance(llm_overrides, Mapping) else {},
            max_decisions=loop_int("max_decisions", DEFAULT_MAX_DECISIONS),
            max_parse_retries=loop_int("max_parse_retries", DEFAULT_MAX_PARSE_RETRIES),
            max_llm_calls=loop_int("max_llm_calls", DEFAULT_MAX_LLM_CALLS),
            max_candidate_runs=as_int("max_candidate_runs", DEFAULT_MAX_CANDIDATE_RUNS),
            candidate_actor_mode=str(raw.get("candidate_actor_mode", "inherit")),
            candidate_steps=candidate_steps,
            plots_enabled=bool(raw.get("plots_enabled", True)),
        )


@dataclass
class ToolTrace:
    """Append-only JSONL audit of the design loop.

    ``llm_turn`` rows are one question to the model and its whole answer:
    message, reasoning, and whatever thinking the provider exposed.
    ``tool_call`` rows are the work the code did around it -- ``source`` says
    which fixed stage asked for it, since the model no longer picks tools.
    """

    path: Path
    records: List[Dict[str, Any]] = field(default_factory=list)

    def append(self, record: Dict[str, Any]) -> None:
        self.records.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class ToolUseDesignAgent:
    """One designer, one tool per turn, Evidence Gate before any final answer."""

    def __init__(
        self,
        *,
        agent_id: str,
        persona: str,
        settings: ToolUseSettings,
        llm_client: Optional[LLMClient] = None,
    ):
        self.agent_id = agent_id
        self.persona = persona
        self.settings = settings
        self.llm_client = llm_client
        self._turn_messages: List[Dict[str, Any]] = []
        self._message_step = 0
        self._llm_calls = 0

    # ------------------------------------------------------------------ #
    def propose(self, bundle: Any) -> Dict[str, Any]:
        self._turn_messages = []
        self._message_step = _post_run_step(getattr(bundle, "summary", {}) or {})
        self._llm_calls = 0
        run_dir = Path(getattr(bundle, "run_dir", None) or ".")
        scenario_config = dict(getattr(bundle, "scenario_config", {}) or {})
        constraints = DesignConstraints.from_scenario_config(scenario_config)
        toolkit = DesignToolkit(
            DesignToolContext(
                run_dir=run_dir,
                scenario_config=scenario_config,
                summary=dict(getattr(bundle, "summary", {}) or {}),
                agents_config=getattr(bundle, "agents_config", None),
                constraints=constraints,
                max_candidate_runs=self.settings.max_candidate_runs,
                candidate_actor_mode=self.settings.candidate_actor_mode,
                candidate_steps=self.settings.candidate_steps,
                plots_enabled=self.settings.plots_enabled,
            )
        )
        # The trace is no longer the designer's memory -- the design state is.
        # It stays as the human-readable record of what happened, which is the
        # only thing it was ever good at.
        trace = ToolTrace(run_dir / "tool_trace.jsonl")
        trace.append(
            {
                "event": "start",
                "agent_id": self.agent_id,
                "run_dir": str(run_dir),
                "max_decisions": self.settings.max_decisions,
                "max_candidate_runs": self.settings.max_candidate_runs,
            }
        )

        # Evidence is gathered the same way whether or not a model is answering.
        evidence = self._gather_evidence(toolkit, trace)
        if self.llm_client is None:
            result = self._rule_fallback(toolkit, trace, reason="no_llm_client")
        else:
            result = self._decision_loop(toolkit, trace, evidence)

        return self._finalize(bundle, toolkit, trace, result)

    # ------------------------------------------------------------------ #
    # keeping the record
    # ------------------------------------------------------------------ #
    @staticmethod
    def _thinking_from(generation: LLMGeneration, parsed: Any) -> str:
        """Whatever the provider let us see of the model working.

        Providers put it in different places -- a dedicated field, a wrapper on
        the parsed object, ``<think>`` tags in the text -- so all three are
        merged rather than picked between.
        """
        return combine_thinking(
            generation.thinking,
            getattr(parsed, "thinking", "") or "",
            extract_thinking_text(generation.text),
        )

    def _append_turn_message(
        self,
        *,
        message: str,
        reasoning: str,
        thinking: str,
        decision: int,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Add one turn to the deliberation the run's own record will carry.

        Without this the run keeps only the closing statement, and a reader
        sees the conclusion with none of the turns that reached it.
        """
        metadata: Dict[str, Any] = {
            "decision_source": "design_decision_loop",
            "deliberation_phase": DeliberationPhase.POST_RUN,
            "tool_iteration": decision,
            "decision_index": decision,
        }
        if thinking:
            metadata["thinking"] = thinking
        if extra:
            metadata.update(dict(extra))
        self._turn_messages.append(
            AgentMessage(
                step=self._message_step,
                from_role=self.agent_id,
                to_role="team",
                message=message or "design decision %d" % decision,
                message_type="comment",
                reasoning=reasoning or "",
                metadata=metadata,
            ).to_dict()
        )

    def _record_llm_turn(
        self,
        trace: ToolTrace,
        *,
        decision: int,
        generation: LLMGeneration,
        parsed: Any,
        elapsed_s: float,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Write down one exchange in full, readable or not."""
        data = parsed.data if isinstance(getattr(parsed, "data", None), Mapping) else {}
        thinking = self._thinking_from(generation, parsed)
        message = str(data.get("message") or data.get("rationale") or "")
        reasoning = str(data.get("rationale") or data.get("reasoning") or "")
        record: Dict[str, Any] = {
            "event": "llm_turn",
            # ``iteration`` is the name every existing reader looks for; this
            # loop counts decisions, so both names carry the same number.
            "iteration": decision,
            "decision": decision,
            "elapsed_s": round(elapsed_s, 2),
            "parse_status": getattr(parsed, "status", None),
            "parse_error": getattr(parsed, "error", None),
            "choice": str(data.get("decision") or ""),
            "message": message,
            "reasoning": reasoning,
            "thinking": thinking,
            "raw_excerpt": _clip(generation.text, _RAW_RESPONSE_LOG_CHARS),
        }
        if extra:
            record.update(dict(extra))
        trace.append(record)
        self._append_turn_message(
            message=message,
            reasoning=reasoning,
            thinking=thinking,
            decision=decision,
            extra=extra,
        )
        return thinking

    def _traced_tool_call(
        self,
        toolkit: DesignToolkit,
        trace: ToolTrace,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        decision: int,
        source: str,
    ) -> Dict[str, Any]:
        """Run one tool and record it.

        ``source`` names the fixed stage that asked for it. The model does not
        choose tools any more, so filing these under the model would
        misdescribe the run.
        """
        arguments = dict(arguments or {})
        started = time.monotonic()
        result = toolkit.call(name, arguments)
        trace.append(
            {
                "event": "tool_call",
                "source": source,
                "iteration": decision,
                "decision": decision,
                "tool": name,
                "arguments": arguments,
                "result": result,
                "result_excerpt": _clip(_dumps(result), _RESULT_EXCERPT_CHARS),
                "tool_elapsed_s": round(time.monotonic() - started, 2),
                "evidence": toolkit.evidence_report(),
            }
        )
        return result

    # ------------------------------------------------------------------ #
    # deterministic evidence and candidate pipeline
    # ------------------------------------------------------------------ #
    def _gather_evidence(self, toolkit: DesignToolkit, trace: ToolTrace) -> Dict[str, Any]:
        """Read the run before anyone is asked to design against it.

        The designer used to spend its first turns fetching this, and could
        reach a conclusion without ever asking for some of it. It is the same
        work every time, so the code does it every time.
        """
        started = time.monotonic()

        def call(name: str, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
            return self._traced_tool_call(
                toolkit, trace, name, arguments, decision=0, source="evidence"
            )

        call("load_run_artifacts", {})
        call("summarize_timeseries", {"source": "telemetry"})
        call("summarize_timeseries", {"source": "health_metrics"})
        features = call("compute_eclss_features", {})
        theory = call("compute_theoretical_capacity", {})
        if self.settings.plots_enabled:
            call("plot_eclss_timeseries", {})
        trace.append(
            {
                "event": "evidence_gathered",
                "elapsed_s": round(time.monotonic() - started, 2),
                "evidence": toolkit.evidence_report(),
            }
        )
        return {"features": features, "theory": theory}

    def _run_candidate_pipeline(
        self,
        toolkit: DesignToolkit,
        trace: ToolTrace,
        fields: Mapping[str, Any],
        *,
        decision: int,
        label: Optional[str] = None,
        source: str = "pipeline",
    ) -> Dict[str, Any]:
        """Check, simulate, audit and compare one proposed machine.

        Every step runs, in this order, for every candidate. The designer
        cannot skip the constraint check or forget to re-simulate, because it
        is never asked which of these to do.
        """
        normalized = normalize_fields(fields)
        if not normalized:
            record = {"error": "no recognised design variable in the proposal"}
            trace.append({"event": "candidate_rejected", "decision": decision, **record})
            return record

        duplicate = find_duplicate(toolkit.candidates, normalized)
        if duplicate is not None:
            # The same machine, proposed again. It costs a decision -- one was
            # spent -- but not a second simulation.
            trace.append(
                {
                    "event": "candidate_duplicate",
                    "decision": decision,
                    "candidate_id": duplicate.get("candidate_id"),
                    "fields": normalized,
                }
            )
            return dict(duplicate)

        started = time.monotonic()
        # Constraints before simulation, and recorded: the mass, volume and cost
        # of a machine are known without running it, and the review has to be
        # able to show that they were looked at.
        def call(name: str, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
            return self._traced_tool_call(
                toolkit, trace, name, arguments, decision=decision, source=source
            )

        call("evaluate_design_constraints", {"fields": normalized})
        result = call(
            "run_design_candidate",
            {"fields": normalized, "label": label or "decision_%d" % decision},
        )
        for record in toolkit.candidates:
            if record.get("candidate_id") == result.get("candidate_id"):
                record["candidate_hash"] = candidate_hash(normalized)
        comparison = call("compare_design_runs", {})
        trace.append(
            {
                "event": "candidate_evaluated",
                "decision": decision,
                "candidate_id": result.get("candidate_id"),
                "fields": normalized,
                "simulated": bool(result.get("simulated")),
                "outcome": result.get("outcome"),
                "constraint_evaluation": result.get("constraint_evaluation"),
                "current_best": (comparison.get("selection") or {}).get("selected_candidate_id"),
                "elapsed_s": round(time.monotonic() - started, 2),
            }
        )
        return result

    # ------------------------------------------------------------------ #
    # design decision loop
    # ------------------------------------------------------------------ #
    def _decision_loop(
        self, toolkit: DesignToolkit, trace: ToolTrace, evidence: Mapping[str, Any]
    ) -> Dict[str, Any]:
        notes: List[str] = []
        run_dir = toolkit.ctx.run_dir
        message = ""
        reasoning = ""
        self._llm_calls = 0

        for decision in range(1, self.settings.max_decisions + 1):
            # Both budgets are checked before the question, not after. Asking
            # what to build next and then discarding the answer because there
            # was no room to build it costs the whole run's slowest operation
            # and buys nothing.
            if len(toolkit.candidates) >= self.settings.max_candidate_runs:
                notes.append(
                    "decision %d: candidate budget spent; adopting the best verified design"
                    % decision
                )
                trace.append(
                    {
                        "event": "budget_reached",
                        "decision": decision,
                        "reason": "candidate_budget",
                        "candidates": len(toolkit.candidates),
                        "llm_calls": self._llm_calls,
                    }
                )
                break
            if self._llm_calls >= self.settings.max_llm_calls:
                notes.append(
                    "decision %d: question budget spent; adopting the best verified design"
                    % decision
                )
                trace.append(
                    {
                        "event": "budget_reached",
                        "decision": decision,
                        "reason": "llm_call_budget",
                        "candidates": len(toolkit.candidates),
                        "llm_calls": self._llm_calls,
                    }
                )
                break

            state = build_design_state(
                baseline_outcome=toolkit.baseline_outcome,
                theory=evidence.get("theory") or {},
                features=evidence.get("features") or {},
                candidates=toolkit.candidates,
                scenario_config=toolkit.ctx.scenario_config,
                decisions_left=self.settings.max_decisions - decision + 1,
                candidate_budget_left=self.settings.max_candidate_runs - len(toolkit.candidates),
            )
            _write_json(run_dir / DESIGN_STATE_FILENAME, state)
            trace.append({"event": "design_state", "decision": decision, "state": state})

            parsed, elapsed, generation, raw_parse = self._ask(state, repair=False)
            thinking = self._record_llm_turn(
                trace,
                decision=decision,
                generation=generation,
                parsed=raw_parse,
                elapsed_s=elapsed,
            )
            retries = 0
            while (
                parsed is None
                and retries < self.settings.max_parse_retries
                and self._llm_calls < self.settings.max_llm_calls
            ):
                retries += 1
                notes.append("decision %d: unusable reply, repaired once" % decision)
                trace.append(
                    {
                        "event": "parse_failure",
                        "decision": decision,
                        "iteration": decision,
                        "retry": retries,
                        "parse_status": getattr(raw_parse, "status", None),
                        "parse_error": getattr(raw_parse, "error", None),
                        "thinking": thinking,
                        "raw_excerpt": _clip(generation.text, _RAW_RESPONSE_LOG_CHARS),
                    }
                )
                parsed, elapsed, generation, raw_parse = self._ask(state, repair=True)
                thinking = self._record_llm_turn(
                    trace,
                    decision=decision,
                    generation=generation,
                    parsed=raw_parse,
                    elapsed_s=elapsed,
                    extra={"repair_attempt": retries},
                )
            if parsed is None:
                trace.append(
                    {
                        "event": "parse_failure",
                        "decision": decision,
                        "iteration": decision,
                        "retry": retries,
                        "parse_status": getattr(raw_parse, "status", None),
                        "parse_error": getattr(raw_parse, "error", None),
                        "thinking": thinking,
                        "raw_excerpt": _clip(generation.text, _RAW_RESPONSE_LOG_CHARS),
                    }
                )
                notes.append("decision %d: unusable reply after repair" % decision)
                return self._rule_fallback(toolkit, trace, reason="unusable_reply", notes=notes)

            message = str(parsed.get("message") or parsed.get("rationale") or "")
            reasoning = str(parsed.get("rationale") or "")
            choice = str(parsed.get("decision") or "").strip()
            trace.append(
                {
                    "event": "decision",
                    "decision": decision,
                    "iteration": decision,
                    "choice": choice,
                    # Kept whole. A rationale cut off mid-sentence cannot be
                    # reviewed, and reviewing it is the point of writing it.
                    "message": message,
                    "rationale": reasoning,
                    "thinking": thinking,
                    "llm_elapsed_s": elapsed,
                }
            )

            if choice == "finish":
                if not toolkit.candidates:
                    # Nothing was ever tried, so there is nothing to finish on.
                    notes.append(
                        "decision %d: asked to finish before proposing a candidate" % decision
                    )
                    return self._rule_fallback(
                        toolkit, trace, reason="finished_without_candidate", notes=notes
                    )
                return {
                    "final_proposal": {
                        "candidate_id": parsed.get("selected_candidate_id"),
                        "changes": [],
                    },
                    "message": message,
                    "reasoning": reasoning,
                    "parse_notes": notes,
                    "decision_source": "design_decision_loop",
                    "iterations_used": decision,
                }

            if choice != "propose_candidate":
                notes.append("decision %d: unknown decision %r" % (decision, choice))
                return self._rule_fallback(toolkit, trace, reason="unknown_decision", notes=notes)

            self._run_candidate_pipeline(
                toolkit, trace, parsed.get("fields") or {}, decision=decision
            )

        if not toolkit.candidates:
            # Nothing was ever built, so there is nothing to adopt. The
            # deterministic sizing is the only way this run ends with a design.
            notes.append("no candidate was produced within the budget")
            return self._rule_fallback(toolkit, trace, reason="no_candidate", notes=notes)
        # A spent budget is how a round is meant to end. The verified design is
        # adopted by the ranking and handed to the next iteration; the chain,
        # not this loop, is where the search continues.
        return {
            "final_proposal": None,
            "message": message,
            "reasoning": reasoning,
            "parse_notes": notes,
            "decision_source": "design_decision_loop:budget_reached",
            "iterations_used": min(self._llm_calls, self.settings.max_decisions),
            "llm_calls": self._llm_calls,
        }

    def _ask(self, state: Mapping[str, Any], *, repair: bool):
        """One question, one answer.

        Returns the usable decision (``None`` when the reply could not be
        read), how long it took, and the untouched generation and parse so the
        caller can record what was actually said either way.
        """
        prompt = self._build_prompt(state, repair=repair)
        started = time.monotonic()
        self._llm_calls += 1
        generation = invoke_llm(self.llm_client, prompt)
        elapsed = round(time.monotonic() - started, 2)
        parsed = parse_json_response(generation.text, required=("decision",))
        if parsed.status in {"fallback", "empty_response"}:
            return None, elapsed, generation, parsed
        data = parsed.data if isinstance(parsed.data, Mapping) else {}
        return (dict(data) or None), elapsed, generation, parsed

    def _build_prompt(self, state: Mapping[str, Any], *, repair: bool = False) -> str:
        """Four blocks and nothing else: who, where things stand, aim, format.

        No history is included. The state above is assembled fresh for every
        decision, so there is nothing earlier to re-read and nothing to forget.
        """
        sections = [
            "You are %s, the post-run ECLSS capacity design engineer." % self.agent_id,
            self.persona.strip(),
            "",
            EXPERT_CONTEXT_PACK,
            "",
            "### Where the design stands",
            _dumps(state),
            "",
            "### Your decision",
            "Propose one sizing to try, or finish. Everything else -- checking, "
            "simulating, auditing and comparing -- is done for you before you are "
            "asked again.",
            "",
            "### Output contract",
            DECISION_CONTRACT,
        ]
        if repair:
            sections += [
                "",
                "### Your last reply could not be read",
                "It was empty or was not valid JSON. Reply with exactly one JSON "
                "object in the format above and no other text.",
            ]
        return "\n".join(sections)

    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # deterministic fallback
    # ------------------------------------------------------------------ #
    def _rule_fallback(
        self,
        toolkit: DesignToolkit,
        trace: ToolTrace,
        *,
        reason: str,
        notes: Optional[List[str]] = None,
        task_plan: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Theory-driven sizing, run and compared without the LLM.

        Used when the model is unavailable or its replies cannot be read. It
        keeps every candidate already simulated -- losing them would throw away
        verified work because the link dropped -- and spends whatever candidate
        budget is left on theory-sized machines, so the run still ends with a
        design somebody checked.

        Evidence is already gathered before the first decision, so this does not
        collect it again.
        """
        notes = list(notes or [])
        trace.append(
            {
                "event": "rule_fallback_start",
                "reason": reason,
                "candidates_kept": len(toolkit.candidates),
            }
        )
        self._append_turn_message(
            message=(
                "Deterministic fallback is sizing and verifying capacity candidates "
                "(%s)." % reason
            ),
            reasoning="Fallback reason: %s." % reason,
            thinking="",
            decision=0,
            extra={"decision_source": "tool_use_rule_fallback:%s" % reason},
        )

        def call(name: str, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
            return self._traced_tool_call(
                toolkit, trace, name, arguments, decision=0, source="rule_fallback"
            )

        theory = call("compute_theoretical_capacity", {})

        remaining = self.settings.max_candidate_runs - len(toolkit.candidates)
        margins = [1.15, 1.0, 1.35][: max(0, min(remaining, 3))]
        for margin in margins:
            candidate = call("propose_capacity_candidate", {"margin": margin})
            fields = candidate.get("fields")
            if not fields:
                continue
            if find_duplicate(toolkit.candidates, fields) is not None:
                continue
            run = self._run_candidate_pipeline(
                toolkit,
                trace,
                fields,
                decision=0,
                label=f"rule_margin_{margin}",
                source="rule_fallback",
            )
            outcome = (run or {}).get("outcome") or {}
            if outcome.get("full_survival"):
                # Full survival reached; the smaller margins below it are the
                # interesting comparison, not larger ones.
                if margin <= 1.0:
                    break
        comparison = call("compare_design_runs", {})
        trace.append(
            {
                "event": "rule_fallback_done",
                "reason": reason,
                "theory_excerpt": _clip(_dumps(theory), 1200),
                "comparison_excerpt": _clip(_dumps(comparison), 1500),
            }
        )
        return {
            "decision_source": f"tool_use_rule_fallback:{reason}",
            "message": (
                "Capacity sized from crew demand and operation cadence, then verified by "
                "candidate re-simulation (deterministic fallback)."
            ),
            "reasoning": (
                f"Fallback reason: {reason}. Nameplate targets come from "
                "compute_theoretical_capacity; the adopted candidate is the best ranked "
                "re-simulated design."
            ),
            "final_proposal": None,
            "task_plan": list(task_plan or []),
            "iterations_used": self.settings.max_decisions,
            "parse_notes": notes,
        }

    # ------------------------------------------------------------------ #
    # report assembly
    # ------------------------------------------------------------------ #
    def _finalize(
        self,
        bundle: Any,
        toolkit: DesignToolkit,
        trace: ToolTrace,
        result: Mapping[str, Any],
    ) -> Dict[str, Any]:
        run_dir = Path(getattr(bundle, "run_dir", None) or ".")
        # Housekeeping, not designer work: re-rank whatever was simulated without
        # crediting the evidence ledger, so `evidence` still reports what the
        # designer itself collected.
        comparison = (
            toolkit.call("compare_design_runs", {}, record_evidence=False)
            if toolkit.candidates
            else {}
        )
        ranked = toolkit.ranked_candidates
        selection = toolkit.selection or {
            "final_status": STATUS_REJECTED,
            "selected_candidate_id": None,
            "reason": comparison.get("error", "no candidate was simulated"),
        }

        requested_id = None
        final_proposal = result.get("final_proposal")
        if isinstance(final_proposal, Mapping):
            requested_id = final_proposal.get("candidate_id")

        selected = self._pick_record(ranked, selection.get("selected_candidate_id"))
        requested = self._pick_record(ranked, requested_id) if requested_id else None
        notes = list(result.get("parse_notes") or [])
        if requested_id and requested is None:
            notes.append(
                f"designer referenced {requested_id!r}, which is not among the simulated "
                "candidates; kept the ranked selection"
            )
        selected_id = (selected or {}).get("candidate_id")
        if requested is not None and requested.get("candidate_id") != selected_id:
            # The ranking is the objective: every eligible candidate keeps the
            # whole crew alive, so rank 1 is the calmest then smallest design
            # that does. A different pick can only be a more CRITICAL or larger
            # one — record it, do not adopt it. The designer's judgement steers
            # which candidates get built and simulated, not which verified
            # candidate wins.
            reasons = requested.get("final_ineligible_reasons") or []
            detail = f"not final-eligible ({', '.join(reasons)})" if reasons else "ranked lower"
            notes.append(
                f"designer asked for {requested_id!r}, which is {detail}; kept the ranked "
                f"selection {selected_id!r}"
            )

        evidence = toolkit.evidence_report()
        final_status = selection.get("final_status", STATUS_REJECTED)
        if evidence["missing"] and final_status != STATUS_REJECTED:
            final_status = STATUS_PROVISIONAL
            selection = {
                **selection,
                "final_status": final_status,
                "reason": (
                    f"{selection.get('reason', '')} | evidence incomplete: "
                    f"{', '.join(evidence['missing'])}"
                ).strip(" |"),
            }

        if selected is None and ranked:
            selected = dict(ranked[0])
        changes: List[Dict[str, Any]] = []
        constraint_evaluation: Dict[str, Any] = {}
        expected_outcome: Dict[str, Any] = {}
        if selected is not None:
            constraint_evaluation = dict(selected.get("constraint_evaluation") or {})
            outcome = dict(selected.get("outcome") or {})
            expected_outcome = {
                "candidate_id": selected.get("candidate_id"),
                "crew_initial": outcome.get("crew_initial"),
                "crew_remaining": outcome.get("crew_remaining"),
                "critical_step_count": outcome.get("critical_step_count"),
                "warning_step_count": outcome.get("warning_step_count"),
                "peak_co2_storage_kg": outcome.get("peak_co2_storage_kg"),
                "min_o2_storage_kg": outcome.get("min_o2_storage_kg"),
                "final_product_water_reserve_l": outcome.get("final_product_water_reserve_l"),
                "baseline_crew_remaining": toolkit.baseline_outcome.get("crew_remaining"),
                "candidate_run_dir": selected.get("run_dir"),
            }
            changes.append(
                {
                    "change_kind": "capacity_profile",
                    "payload": {
                        "backend": "plant_sim",
                        "fields": dict(selected.get("fields") or {}),
                    },
                    "why": self._why(toolkit, selected),
                    "what": (
                        "Size ARS / OGS / WRS throughput to the verified candidate "
                        f"{selected.get('candidate_id')}."
                    ),
                    "how": self._how(toolkit, selected),
                    "requires_supervisor_approval": bool(
                        selection.get("requires_supervisor_approval", False)
                    ),
                    "candidate_id": selected.get("candidate_id"),
                }
            )

        rankings_path = run_dir / "candidate_rankings.json"
        report_path = run_dir / "design_review_report.json"
        rankings_doc = {
            "baseline": toolkit.baseline_outcome,
            "ranking": [DesignToolkit._ranking_row(record) for record in ranked],
            "selection": selection,
        }
        _write_json(rankings_path, rankings_doc)

        # One row per exchange, in order, so the report alone shows how the
        # design was reached even if the trace file is not at hand.
        thinking_turns = [
            {
                "decision": record.get("decision"),
                "iteration": record.get("iteration"),
                "parse_status": record.get("parse_status"),
                "choice": record.get("choice"),
                "message": record.get("message"),
                "reasoning": record.get("reasoning"),
                "thinking": record.get("thinking") or "",
            }
            for record in trace.records
            if record.get("event") == "llm_turn"
        ]
        report = {
            "design_family": DESIGN_FAMILY,
            "agent_id": self.agent_id,
            "decision_source": result.get("decision_source"),
            "message": result.get("message"),
            "reasoning": result.get("reasoning"),
            "task_plan": result.get("task_plan"),
            "iterations_used": result.get("iterations_used"),
            "llm_turn_count": len(thinking_turns),
            "thinking_turns": thinking_turns,
            "evidence": evidence,
            "constraints": toolkit.constraints.describe(),
            "baseline_outcome": toolkit.baseline_outcome,
            "candidates": [DesignToolkit._ranking_row(record) for record in ranked],
            "candidate_errors": [
                {
                    "candidate_id": record.get("candidate_id"),
                    "error": record.get("error"),
                    "constraint_status": (record.get("constraint_evaluation") or {}).get(
                        "constraint_status"
                    ),
                }
                for record in toolkit.candidates
                if record.get("error")
            ],
            "selection": selection,
            "final_status": final_status,
            "plots": toolkit.plot_paths,
            "notes": notes,
        }
        _write_json(report_path, report)
        trace.append({"event": "done", "final_status": final_status, "selection": selection})

        message = str(result.get("message") or "")
        proposals: Dict[str, Any] = {
            "design_domain": DESIGN_DOMAIN,
            "design_family": DESIGN_FAMILY,
            "proposed_by": self.agent_id,
            "decision_source": str(result.get("decision_source") or "tool_use"),
            "message": message,
            "reasoning": str(result.get("reasoning") or ""),
            "changes": changes,
            "parse_notes": notes,
            "baseline_graph": dict(getattr(bundle, "baseline_graph", {}) or {}),
            "final_status": final_status,
            "selected_candidate_id": selection.get("selected_candidate_id"),
            "requires_supervisor_approval": bool(
                selection.get("requires_supervisor_approval", False)
            ),
            # Carried into the document so `--apply-proposals` can tell a human
            # what it is refusing without opening the review report.
            "selection_reason": selection.get("reason"),
            "expected_outcome": expected_outcome,
            "constraint_evaluation": {
                key: constraint_evaluation.get(key)
                for key in (
                    "constraint_status",
                    "total_mass_kg",
                    "total_volume_m3",
                    "total_cost_musd",
                    "added_mass_kg",
                    "added_cost_musd",
                    "design_penalty",
                    "violations",
                )
            },
            "evidence": evidence,
            "tool_trace_path": str(trace.path),
            "candidate_rankings_path": str(rankings_path),
            "design_review_report_path": str(report_path),
            "llm_turn_count": len(thinking_turns),
            "candidate_run_dirs": [
                record.get("run_dir") for record in ranked if record.get("run_dir")
            ],
        }
        final_thinking = ""
        for record in reversed(trace.records):
            if record.get("event") == "llm_turn" and record.get("thinking"):
                final_thinking = str(record.get("thinking") or "")
                break
        final_meta: Dict[str, Any] = {
            "decision_source": proposals["decision_source"],
            "deliberation_phase": DeliberationPhase.POST_RUN,
            "final_status": final_status,
            "selected_candidate_id": selection.get("selected_candidate_id"),
            "tool_iterations": result.get("iterations_used"),
            "llm_turn_count": len(thinking_turns),
        }
        if final_thinking:
            final_meta["thinking"] = final_thinking
        # Every turn, then the closing statement: the record reads as the
        # deliberation it was, not as a verdict with no argument behind it.
        proposals["deliberation_messages"] = list(self._turn_messages) + [
            AgentMessage(
                step=self._message_step,
                from_role=self.agent_id,
                to_role="team",
                message=message or "Capacity design complete.",
                message_type="comment",
                reasoning=str(result.get("reasoning") or ""),
                metadata=final_meta,
            ).to_dict()
        ]
        return proposals

    @staticmethod
    def _pick_record(
        ranked: Sequence[Mapping[str, Any]],
        candidate_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """The named candidate, or rank 1 when no name is given.

        An unknown name returns None so the caller can say so instead of
        silently substituting the top-ranked candidate.
        """
        if not ranked:
            return None
        if candidate_id:
            for record in ranked:
                if record.get("candidate_id") == candidate_id:
                    return dict(record)
            return None
        return dict(ranked[0])

    @staticmethod
    def _how(toolkit: DesignToolkit, selected: Mapping[str, Any]) -> str:
        """``key: old → new`` for every resized design variable."""
        installed = read_capacity_fields(toolkit.ctx.scenario_config)
        parts = []
        for key, value in (selected.get("fields") or {}).items():
            before = installed.get(key)
            parts.append(f"{key}: {before} → {value}" if before is not None else f"{key}: {value}")
        return ", ".join(parts)

    @staticmethod
    def _why(toolkit: DesignToolkit, selected: Mapping[str, Any]) -> str:
        baseline = toolkit.baseline_outcome
        outcome = selected.get("outcome") or {}
        return (
            f"baseline kept {baseline.get('crew_remaining')}/{baseline.get('crew_initial')} "
            f"occupants with {baseline.get('critical_step_count')} critical steps "
            f"(peak CO2 {baseline.get('peak_co2_storage_kg')} kg, min O2 "
            f"{baseline.get('min_o2_storage_kg')} kg); the re-simulated candidate keeps "
            f"{outcome.get('crew_remaining')}/{outcome.get('crew_initial')} with "
            f"{outcome.get('critical_step_count')} critical steps"
        )


def _post_run_step(summary: Mapping[str, Any]) -> int:
    try:
        steps = int(summary.get("steps", 0) or 0)
    except (TypeError, ValueError):
        steps = 0
    return max(steps - 1, 0)


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]} …[{len(text) - limit} chars omitted]"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "DESIGN_FAMILY",
    "EXPERT_CONTEXT_PACK",
    "DECISION_CONTRACT",
    "DESIGN_STATE_FILENAME",
    "ToolTrace",
    "ToolUseDesignAgent",
    "ToolUseSettings",
    "STATUS_APPROVED",
    "STATUS_PROVISIONAL",
    "STATUS_REJECTED",
]
