"""Tool-use post-run ECLSS design agent (design doc §4, §5, §10).

A single designer runs an autonomous planning loop instead of reading a
pre-digested summary: it writes its own ``task_plan``, picks one tool per turn,
observes the deterministic result, and revises. The implementation fixes the
guardrails, not the order of thought:

* one tool call per turn, from a fixed catalog
* ``max_tool_iterations`` / ``max_candidate_runs``
* an Evidence Gate that rejects a ``final_proposal`` which is not backed by
  artifacts, theory, constraints, a candidate re-simulation and a comparison.
  Candidate validation is an invariant, not a switch: the adopted fields always
  come from a record written by ``run_design_candidate``, so there is no
  configuration under which an unverified design is proposed
* a deterministic rule fallback so the run always yields a design

The Expert Context Pack in the prompt exists because a 8B–32B model, left to
self-assess, tends to jump from ``summary.json`` straight to a final answer. It
states the minimum domain facts and the minimum evidence, not a procedure.

Self-hosted vLLM / Ollama cannot be relied on for native function calling, so
the tool protocol is a plain JSON contract parsed by
:mod:`core.llm.parsing`.
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
from scenario.ssos_eclss_loop.design_tools import DesignToolContext, DesignToolkit
from scenario.ssos_eclss_loop.design_variables import CAPACITY_KEYS, read_capacity_fields

DESIGN_FAMILY = "capacity_sizing"

# Seven required tools plus up to four candidate runs fill eleven turns, so a
# budget near that leaves no room for a rejected final_proposal, a mistyped tool
# name or a second look at the data before the deterministic fallback takes over.
DEFAULT_MAX_TOOL_ITERATIONS = 24
DEFAULT_MAX_CANDIDATE_RUNS = 4

# Observation text budget per tool result kept in the prompt (characters).
_RECENT_OBSERVATION_CHARS = 2600
_OLDER_OBSERVATION_CHARS = 400
_FULL_OBSERVATIONS = 3
_RAW_RESPONSE_LOG_CHARS = 12000
_RESULT_EXCERPT_CHARS = 8000


EXPERT_CONTEXT_PACK = """\
### Expert context pack (domain minimum, not a procedure)
- Objective: every occupant must survive — a design that loses one is never adopted,
  whatever it saves. Among designs where crew_remaining == crew_initial, less CRITICAL
  dwell wins before mass, then volume, then cost. A light machine that lives in a
  dangerous band loses to a heavier calm one. So do not stop at the first design
  that works; find the calmest, then smallest, that still works.
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


TOOL_LOOP_CONTRACT = """\
Reply with ONE JSON object and nothing else.

To use a tool:
{"message": "what you learned or plan next", "reasoning": "why this tool now",
 "task_plan": ["short", "ordered", "steps"],
 "tool_call": {"name": "<tool name>", "arguments": {}}}

To finish:
{"message": "final recommendation", "reasoning": "evidence-backed rationale",
 "final_proposal": {"candidate_id": "<candidate you verified>",
                    "changes": [{"change_kind": "capacity_profile",
                                 "payload": {"backend": "plant_sim",
                                             "fields": {"<design variable>": <number>}}}],
                    "expected_outcome": {},
                    "constraint_evaluation": {}}}

Rules: exactly one tool_call per turn; never both tool_call and final_proposal;
never invent tool names or numbers; capacity fields are limited to
%s.""" % json.dumps(list(CAPACITY_KEYS))


@dataclass
class ToolUseSettings:
    enabled: bool = False
    # Optional overrides merged over design.llm for the tool loop only. A loop
    # turn emits a small JSON object, so the classic designer's large
    # completion budget only buys thinking tokens — and a turn that spends them
    # all can exceed the HTTP timeout and come back empty.
    llm_overrides: Dict[str, Any] = field(default_factory=dict)
    max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS
    max_candidate_runs: int = DEFAULT_MAX_CANDIDATE_RUNS
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
        return cls(
            enabled=bool(raw.get("enabled", False)),
            llm_overrides=dict(llm_overrides) if isinstance(llm_overrides, Mapping) else {},
            max_tool_iterations=as_int("max_tool_iterations", DEFAULT_MAX_TOOL_ITERATIONS),
            max_candidate_runs=as_int("max_candidate_runs", DEFAULT_MAX_CANDIDATE_RUNS),
            candidate_actor_mode=str(raw.get("candidate_actor_mode", "inherit")),
            candidate_steps=candidate_steps,
            plots_enabled=bool(raw.get("plots_enabled", True)),
        )


@dataclass
class ToolTrace:
    """Append-only JSONL audit of the design loop.

    ``llm_turn`` rows are the model's message, JSON ``reasoning``, and
    captured think/reasoning_content. ``tool_call`` rows are the tool
    name, arguments, and result (``source`` is ``llm`` or ``rule_fallback``).
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

    # ------------------------------------------------------------------ #
    def propose(self, bundle: Any) -> Dict[str, Any]:
        self._turn_messages = []
        self._message_step = _post_run_step(getattr(bundle, "summary", {}) or {})
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
        trace = ToolTrace(run_dir / "tool_trace.jsonl")
        trace.append(
            {
                "event": "start",
                "agent_id": self.agent_id,
                "run_dir": str(run_dir),
                "max_tool_iterations": self.settings.max_tool_iterations,
                "max_candidate_runs": self.settings.max_candidate_runs,
                "tools": toolkit.tool_names(),
            }
        )

        if self.llm_client is None:
            result = self._rule_fallback(toolkit, trace, reason="no_llm_client")
        else:
            result = self._tool_loop(toolkit, trace)

        return self._finalize(bundle, toolkit, trace, result)

    # ------------------------------------------------------------------ #
    # LLM planning loop
    # ------------------------------------------------------------------ #
    @staticmethod
    def _thinking_from(generation: LLMGeneration, parsed: Any) -> str:
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
        iteration: int,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        metadata: Dict[str, Any] = {
            "decision_source": "llm_tool_use",
            "deliberation_phase": DeliberationPhase.POST_RUN,
            "tool_iteration": iteration,
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
                message=message or f"design turn {iteration}",
                message_type="comment",
                reasoning=reasoning or "",
                metadata=metadata,
            ).to_dict()
        )

    def _record_llm_turn(
        self,
        trace: ToolTrace,
        *,
        iteration: int,
        generation: LLMGeneration,
        parsed: Any,
        elapsed_s: float,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> str:
        data = parsed.data if isinstance(getattr(parsed, "data", None), Mapping) else {}
        thinking = self._thinking_from(generation, parsed)
        record: Dict[str, Any] = {
            "event": "llm_turn",
            "iteration": iteration,
            "elapsed_s": round(elapsed_s, 2),
            "parse_status": getattr(parsed, "status", None),
            "parse_error": getattr(parsed, "error", None),
            "message": str(data.get("message", "")),
            "reasoning": str(data.get("reasoning", "")),
            "thinking": thinking,
            "raw_excerpt": _clip(generation.text, _RAW_RESPONSE_LOG_CHARS),
        }
        if extra:
            record.update(dict(extra))
        trace.append(record)
        self._append_turn_message(
            message=str(data.get("message", "")),
            reasoning=str(data.get("reasoning", "")),
            thinking=thinking,
            iteration=iteration,
            extra=extra,
        )
        return thinking

    def _traced_tool_call(
        self,
        toolkit: DesignToolkit,
        trace: ToolTrace,
        name: str,
        arguments: Mapping[str, Any],
        *,
        iteration: int,
        source: str,
        llm_message: str = "",
        llm_reasoning: str = "",
        thinking: str = "",
        task_plan: Optional[Sequence[str]] = None,
        llm_elapsed_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        started = time.monotonic()
        result = toolkit.call(name, arguments)
        record: Dict[str, Any] = {
            "event": "tool_call",
            "source": source,
            "iteration": iteration,
            "tool": name,
            "arguments": dict(arguments),
            "result": result,
            "result_excerpt": _clip(_dumps(result), _RESULT_EXCERPT_CHARS),
            "tool_elapsed_s": round(time.monotonic() - started, 2),
            "evidence": toolkit.evidence_report(),
        }
        if llm_message:
            record["llm_message"] = llm_message
        if llm_reasoning:
            record["llm_reasoning"] = llm_reasoning
        if thinking:
            record["thinking"] = thinking
        if task_plan is not None:
            record["task_plan"] = list(task_plan)
        if llm_elapsed_s is not None:
            record["llm_elapsed_s"] = round(llm_elapsed_s, 2)
        trace.append(record)
        return result

    def _tool_loop(self, toolkit: DesignToolkit, trace: ToolTrace) -> Dict[str, Any]:
        observations: List[Dict[str, Any]] = []
        task_plan: List[str] = []
        notes: List[str] = []
        gate_feedback: Optional[str] = None
        parse_failures = 0

        for iteration in range(1, self.settings.max_tool_iterations + 1):
            prompt = self._build_prompt(
                toolkit,
                observations=observations,
                task_plan=task_plan,
                iteration=iteration,
                gate_feedback=gate_feedback,
            )
            started = time.monotonic()
            generation = invoke_llm(self.llm_client, prompt)
            elapsed = time.monotonic() - started
            parsed = parse_json_response(generation.text, required=("message",))
            thinking = self._record_llm_turn(
                trace,
                iteration=iteration,
                generation=generation,
                parsed=parsed,
                elapsed_s=elapsed,
            )
            gate_feedback = None

            if parsed.status in {"fallback", "empty_response"}:
                parse_failures += 1
                notes.append(f"iteration {iteration}: LLM response unparsable ({parsed.error})")
                trace.append(
                    {
                        "event": "parse_failure",
                        "iteration": iteration,
                        "elapsed_s": round(elapsed, 2),
                        "parse_status": parsed.status,
                        "parse_error": parsed.error,
                        "thinking": thinking,
                        "raw_excerpt": _clip(generation.text, _RAW_RESPONSE_LOG_CHARS),
                    }
                )
                if parse_failures >= 3:
                    return self._rule_fallback(
                        toolkit, trace, reason="repeated_parse_failure", notes=notes
                    )
                gate_feedback = (
                    "Your last reply was not valid JSON. Reply with exactly one JSON object "
                    "following the contract."
                )
                continue

            data = parsed.data
            plan = data.get("task_plan")
            if isinstance(plan, list) and plan:
                task_plan = [str(item) for item in plan][:8]

            final_proposal = data.get("final_proposal")
            tool_call = data.get("tool_call")
            message = str(data.get("message", ""))
            reasoning = str(data.get("reasoning", ""))

            if isinstance(final_proposal, Mapping):
                missing = toolkit.missing_evidence()
                if missing:
                    notes.append(
                        f"iteration {iteration}: final_proposal rejected by Evidence Gate "
                        f"(missing: {', '.join(missing)})"
                    )
                    trace.append(
                        {
                            "event": "evidence_gate_reject",
                            "iteration": iteration,
                            "missing_evidence": missing,
                            "message": message,
                            "reasoning": reasoning,
                            "thinking": thinking,
                        }
                    )
                    gate_feedback = (
                        "Evidence Gate rejected your final_proposal. Missing evidence: "
                        + ", ".join(missing)
                        + ". Keep using tools until every item is collected."
                    )
                    continue
                trace.append(
                    {
                        "event": "final_proposal",
                        "iteration": iteration,
                        "message": message,
                        "reasoning": reasoning,
                        "thinking": thinking,
                        "final_proposal": final_proposal,
                    }
                )
                return {
                    "decision_source": "llm_tool_use",
                    "message": message,
                    "reasoning": reasoning,
                    "final_proposal": dict(final_proposal),
                    "task_plan": task_plan,
                    "iterations_used": iteration,
                    "parse_notes": notes,
                }

            if not isinstance(tool_call, Mapping):
                notes.append(f"iteration {iteration}: reply had neither tool_call nor final_proposal")
                trace.append(
                    {
                        "event": "no_action",
                        "iteration": iteration,
                        "message": message,
                        "reasoning": reasoning,
                        "thinking": thinking,
                    }
                )
                gate_feedback = (
                    "Your reply contained no tool_call and no final_proposal. "
                    "Choose exactly one."
                )
                continue

            name = str(tool_call.get("name", "")).strip()
            arguments = tool_call.get("arguments")
            arguments = dict(arguments) if isinstance(arguments, Mapping) else {}
            if name not in toolkit.tool_names():
                notes.append(f"iteration {iteration}: unknown tool {name!r}")
                trace.append(
                    {
                        "event": "unknown_tool",
                        "iteration": iteration,
                        "requested": name,
                        "thinking": thinking,
                    }
                )
                gate_feedback = (
                    f"{name!r} is not a tool. Available tools: "
                    + ", ".join(toolkit.tool_names())
                )
                continue

            result = self._traced_tool_call(
                toolkit,
                trace,
                name,
                arguments,
                iteration=iteration,
                source="llm",
                llm_message=message,
                llm_reasoning=reasoning,
                thinking=thinking,
                task_plan=task_plan,
                llm_elapsed_s=elapsed,
            )
            observations.append(
                {
                    "iteration": iteration,
                    "tool": name,
                    "arguments": arguments,
                    "result": result,
                }
            )

        notes.append(
            f"tool loop reached max_tool_iterations={self.settings.max_tool_iterations} "
            "without an accepted final_proposal"
        )
        return self._rule_fallback(
            toolkit, trace, reason="max_iterations", notes=notes, task_plan=task_plan
        )

    # ------------------------------------------------------------------ #
    def _build_prompt(
        self,
        toolkit: DesignToolkit,
        *,
        observations: Sequence[Mapping[str, Any]],
        task_plan: Sequence[str],
        iteration: int,
        gate_feedback: Optional[str],
    ) -> str:
        evidence = toolkit.evidence_report()
        history_lines: List[str] = []
        total = len(observations)
        for index, obs in enumerate(observations):
            budget = (
                _RECENT_OBSERVATION_CHARS
                if index >= total - _FULL_OBSERVATIONS
                else _OLDER_OBSERVATION_CHARS
            )
            history_lines.append(
                f"[turn {obs['iteration']}] {obs['tool']}({_dumps(obs['arguments'])}) -> "
                f"{_clip(_dumps(obs['result']), budget)}"
            )
        history = "\n".join(history_lines) or "(no tool has been called yet)"
        plan = "\n".join(f"- {item}" for item in task_plan) or "(you have not written one yet)"

        sections = [
            f"You are {self.agent_id}, the post-run ECLSS capacity design engineer.",
            self.persona.strip(),
            "",
            "The simulation is finished. You cannot change what happened; you decide how the "
            "next build should be sized. You do not get the data up front — call tools to "
            "fetch, compute and verify it.",
            "",
            EXPERT_CONTEXT_PACK,
            "",
            "### Tool catalog (one call per turn)",
            toolkit.catalog_text(),
            "",
            f"### Turn {iteration} of at most {self.settings.max_tool_iterations}",
            f"Candidate simulations used: {evidence['candidates_run']} of "
            f"{self.settings.max_candidate_runs}.",
            "",
            "### Your task plan",
            plan,
            "",
            "### Evidence collected so far",
            f"collected: {evidence['collected'] or 'none'}",
            f"still required before any final_proposal: {evidence['missing'] or 'none'}",
            "",
            "### Tool results so far",
            history,
        ]
        if gate_feedback:
            sections += ["", "### Feedback on your last reply", gate_feedback]
        sections += ["", "### Output contract", TOOL_LOOP_CONTRACT]
        return "\n".join(sections)

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

        Used when the model is unavailable, keeps failing to parse, or burns the
        iteration budget. It performs the same evidence-collecting sequence the
        agent is asked to perform, so the run still ends with a verified design.
        """
        notes = list(notes or [])
        trace.append({"event": "rule_fallback_start", "reason": reason})
        self._append_turn_message(
            message=(
                "Deterministic fallback is collecting evidence and verifying "
                f"capacity candidates ({reason})."
            ),
            reasoning=f"Fallback reason: {reason}.",
            thinking="",
            iteration=0,
            extra={"decision_source": f"tool_use_rule_fallback:{reason}"},
        )
        fallback_turn = 0

        def call(name: str, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
            nonlocal fallback_turn
            fallback_turn += 1
            return self._traced_tool_call(
                toolkit,
                trace,
                name,
                arguments or {},
                iteration=fallback_turn,
                source="rule_fallback",
            )

        call("load_run_artifacts", {"files": ["summary", "scenario_config", "agents_config"]})
        call("summarize_timeseries", {"source": "telemetry"})
        call("summarize_timeseries", {"source": "health_metrics"})
        call("compute_eclss_features", {})
        theory = call("compute_theoretical_capacity", {})

        remaining = self.settings.max_candidate_runs - len(toolkit.candidates)
        margins = [1.15, 1.0, 1.35][: max(1, min(remaining, 3))]
        for margin in margins:
            candidate = call("propose_capacity_candidate", {"margin": margin})
            fields = candidate.get("fields")
            if not fields:
                continue
            call("evaluate_design_constraints", {"fields": fields})
            run = call(
                "run_design_candidate",
                {"fields": fields, "label": f"rule_margin_{margin}"},
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
            "iterations_used": self.settings.max_tool_iterations,
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

        thinking_turns = [
            {
                "iteration": rec.get("iteration"),
                "parse_status": rec.get("parse_status"),
                "message": rec.get("message"),
                "reasoning": rec.get("reasoning"),
                "thinking": rec.get("thinking") or "",
                "tool": rec.get("tool"),
            }
            for rec in trace.records
            if rec.get("event") == "llm_turn"
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
            "tool_trace_path": str(trace.path),
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
        for rec in reversed(trace.records):
            if rec.get("event") == "llm_turn" and rec.get("thinking"):
                final_thinking = str(rec.get("thinking") or "")
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
        proposals["deliberation_messages"] = list(self._turn_messages) + [
            AgentMessage(
                step=_post_run_step(getattr(bundle, "summary", {}) or {}),
                from_role=self.agent_id,
                to_role="team",
                message=message or "Tool-use capacity design complete.",
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
    "TOOL_LOOP_CONTRACT",
    "ToolTrace",
    "ToolUseDesignAgent",
    "ToolUseSettings",
    "STATUS_APPROVED",
    "STATUS_PROVISIONAL",
    "STATUS_REJECTED",
]
