"""One designer, then an independent audit panel, then a deterministic merge."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.agents.persona import ARCHETYPE_LENSES
from core.llm.base import invoke_llm
from core.llm.parsing import parse_json_response
from core.storage import DesignStorage
from core.storage.claims import ClaimsRegistry, rewrite_body_from_selected
from core.storage.session import SessionStore
from scenario.ssos_eclss_loop.chain_memory import load_chain_memory
from scenario.ssos_eclss_loop.design_eval import STATUS_APPROVED, STATUS_PROVISIONAL
from scenario.ssos_eclss_loop.design_state import _scorecard
from scenario.ssos_eclss_loop.design_tools import DesignToolkit
from scenario.ssos_eclss_loop.design_variables import CAPACITY_KEYS, read_capacity_fields

DESIGN_FAMILY = "capacity_sizing"

DEFAULT_BIAS_DIRECTION = (
    "This run's declared bias: after full survival, the ranking rewards less "
    "CRITICAL dwell then a smaller/cheaper machine, so there is incentive to "
    "stop at the first surviving design or to undersize. Do not treat that "
    "incentive as a reason to skip re-deriving numbers or trying to break the "
    "emerging conclusion."
)

INTERNAL_PROPOSAL_KEYS = ("ranked_candidates", "baseline_outcome")

DEFAULT_AUDITOR_PREFIX = "eclss_auditor"
DEFAULT_AUDIT_LENSES = ("rederive_numbers", "avoid_local_optima", "design_validity")
DEFAULT_AUDIT_MAX_TOKENS = 2048
AUDIT_SPEECH_CHARS = 400
AUDIT_BRIEF_CHAR_BUDGET = 12000

AUDIT_CONTRACT = """\
Reply with one JSON object.

Approve: {"decision":"approve","message":"...","reasoning":"..."}
Reject items: {"decision":"reject","rejected_fields":["plant_sim.wrs.max_feed_l_per_operation"],"message":"...","reasoning":"..."}

rejected_fields must already be in the proposal. Do not invent a machine,
field, or value. Unnamed items stay. You do not see the other auditors.
"""


@dataclass
class AuditAgent:
    """One independent auditor on the adoption panel."""

    agent_id: str
    lens: str
    persona: str


@dataclass
class AuditVerdict:
    """What one panel auditor decided, or why it abstained."""

    decision: str
    agent_id: str
    lens: str = ""
    message: str = ""
    reasoning: str = ""
    rejected_fields: List[str] = field(default_factory=list)
    fallback_reason: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def resolve_bias_direction(design_cfg: Mapping[str, Any]) -> str:
    team = design_cfg.get("team") if isinstance(design_cfg.get("team"), Mapping) else {}
    explicit = str((team or {}).get("bias_direction") or "").strip()
    if explicit:
        return explicit
    return DEFAULT_BIAS_DIRECTION


def resolve_audit_config(design_cfg: Mapping[str, Any]) -> Dict[str, Any]:
    raw = design_cfg.get("audit")
    if not isinstance(raw, Mapping):
        return {"enabled": False, "agents": []}
    enabled = True if raw.get("enabled") is None else bool(raw.get("enabled"))
    if "count" in raw and raw.get("count") is not None:
        count = max(0, int(raw["count"]))
    else:
        count = len(DEFAULT_AUDIT_LENSES)
    id_prefix = str(raw.get("id_prefix") or DEFAULT_AUDITOR_PREFIX)
    if raw.get("id") and not raw.get("id_prefix") and raw.get("count") is None:
        agent_ids = [str(raw["id"])]
        count = 1
    else:
        agent_ids = [f"{id_prefix}_{index}" for index in range(1, count + 1)]
    lens_names = [str(name).strip() for name in (raw.get("archetypes") or DEFAULT_AUDIT_LENSES)]
    lens_names = [name for name in lens_names if name]
    if not lens_names:
        lens_names = list(DEFAULT_AUDIT_LENSES)
    unknown = [name for name in lens_names if name not in ARCHETYPE_LENSES]
    if unknown:
        raise ValueError(
            f"Unknown audit lens(es): {unknown}. "
            f"Known lenses: {sorted(ARCHETYPE_LENSES)}"
        )
    shared = str(raw.get("persona") or "").strip()
    agents: List[AuditAgent] = []
    for index, agent_id in enumerate(agent_ids):
        lens = lens_names[index % len(lens_names)]
        persona = ARCHETYPE_LENSES[lens]
        if shared:
            persona = f"{persona}\n\n{shared}"
        agents.append(AuditAgent(agent_id=agent_id, lens=lens, persona=persona))
    return {"enabled": enabled, "agents": agents}


def merge_audit_llm_cfg(
    design_cfg: Mapping[str, Any],
    tool_use_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Designer llm + tool_use overrides, then audit.llm. Default a short budget."""
    audit = design_cfg.get("audit") if isinstance(design_cfg.get("audit"), Mapping) else {}
    audit_llm = audit.get("llm") if isinstance(audit.get("llm"), Mapping) else {}
    merged = {
        **dict(design_cfg.get("llm") or {}),
        **dict(tool_use_overrides or {}),
        **dict(audit_llm),
    }
    if "max_tokens" not in audit_llm:
        merged["max_tokens"] = DEFAULT_AUDIT_MAX_TOKENS
    return merged


def collect_audit_evidence(
    *,
    designer: Mapping[str, Any],
    ranked: Sequence[Mapping[str, Any]],
    scenario_config: Optional[Mapping[str, Any]] = None,
    run_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """The two views an auditor needs: nameplates, and the chain note.

    Python builds this once. Auditors do not choose or call tools.
    """
    selected_id = designer.get("selected_candidate_id")
    selected = next(
        (row for row in ranked if row.get("candidate_id") == selected_id),
        None,
    )
    proposed = dict((selected or {}).get("fields") or _fields_from_changes(designer))
    installed = read_capacity_fields(scenario_config or {})
    delta: Dict[str, Any] = {}
    for key in CAPACITY_KEYS:
        before = installed.get(key)
        after = proposed.get(key)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta[key] = after - before
    evidence: Dict[str, Any] = {
        "installed": {key: installed[key] for key in CAPACITY_KEYS if key in installed},
        "proposed": {key: proposed[key] for key in CAPACITY_KEYS if key in proposed},
        "delta": delta,
    }
    if run_dir is not None:
        memory = _audit_chain_view(load_chain_memory(Path(run_dir)))
        if memory:
            evidence["chain"] = memory
    return evidence


def build_audit_brief(
    *,
    designer: Mapping[str, Any],
    ranked: Sequence[Mapping[str, Any]],
    bias_direction: str,
    auditor: AuditAgent,
    evidence: Optional[Mapping[str, Any]] = None,
) -> str:
    """Show one slim designer proposal to one auditor. Other auditors are absent."""
    selected_id = designer.get("selected_candidate_id")
    selected = next(
        (row for row in ranked if row.get("candidate_id") == selected_id),
        None,
    )
    proposal = {
        "proposed_by": designer.get("proposed_by"),
        "selected_candidate_id": selected_id,
        "fields": (selected or {}).get("fields") or _fields_from_changes(designer),
        "message": _clip_speech(designer.get("message")),
        "reasoning": _clip_speech(designer.get("reasoning")),
        "outcome": _audit_outcome(
            (selected or {}).get("outcome")
            if selected
            else designer.get("expected_outcome")
        ),
    }
    catalog = [_audit_candidate_row(record) for record in ranked if record is not selected]
    sections = [
        f"You are {auditor.agent_id}. Check this machine from your lens.",
        auditor.persona,
        "Approve or reject named items. Do not invent a machine. You do not see the other auditors.",
    ]
    if bias_direction:
        sections += ["", "### Declared bias of this run", _clip_speech(bias_direction)]
    if evidence:
        sections += [
            "",
            "### Installed vs proposed (and chain note)",
            json.dumps(evidence, ensure_ascii=False, default=str, separators=(",", ":")),
        ]
    sections += [
        "",
        "### Proposed machine",
        json.dumps(proposal, ensure_ascii=False, default=str, separators=(",", ":")),
    ]
    if catalog:
        sections += [
            "",
            "### Other verified candidates",
            json.dumps(catalog, ensure_ascii=False, default=str, separators=(",", ":")),
        ]
    sections += ["", "### Output contract", AUDIT_CONTRACT]
    brief = "\n".join(sections)
    if len(brief) <= AUDIT_BRIEF_CHAR_BUDGET:
        return brief
    return brief[:AUDIT_BRIEF_CHAR_BUDGET] + "\n…[audit brief clipped]"


def run_lens_audit(
    *,
    llm_client: Any,
    brief: str,
    auditor: AuditAgent,
    session: Optional[SessionStore] = None,
) -> AuditVerdict:
    """One auditor turn. An unusable reply abstains and does not invent a machine."""
    if llm_client is None:
        return AuditVerdict(
            decision="fallback",
            agent_id=auditor.agent_id,
            lens=auditor.lens,
            fallback_reason="no_llm_client",
        )
    generation = invoke_llm(llm_client, brief)
    parsed = parse_json_response(generation.text, required=("decision",))
    if session is not None:
        session.append(
            auditor.agent_id,
            {
                "event": "audit",
                "lens": auditor.lens,
                "parse_status": parsed.status,
                "raw_excerpt": (generation.text or "")[:2000],
            },
        )
    if parsed.status in {"fallback", "empty_response"} or not isinstance(parsed.data, Mapping):
        return AuditVerdict(
            decision="fallback",
            agent_id=auditor.agent_id,
            lens=auditor.lens,
            fallback_reason=f"unusable_reply:{parsed.status}",
        )
    data = dict(parsed.data)
    choice = str(data.get("decision") or "").strip()
    message = str(data.get("message") or data.get("rationale") or "")
    reasoning = str(data.get("reasoning") or data.get("rationale") or "")
    rejected_fields = _listed_fields(data.get("rejected_fields"))
    if choice in {"approve", "reject"}:
        return AuditVerdict(
            decision=choice,
            agent_id=auditor.agent_id,
            lens=auditor.lens,
            message=message,
            reasoning=reasoning,
            rejected_fields=rejected_fields,
            raw=data,
        )
    return AuditVerdict(
        decision="fallback",
        agent_id=auditor.agent_id,
        lens=auditor.lens,
        message=message,
        reasoning=reasoning,
        fallback_reason=f"unknown_decision:{choice or 'missing'}",
        raw=data,
    )


def run_audit_panel(
    *,
    llm_client: Any,
    designer: Mapping[str, Any],
    ranked: Sequence[Mapping[str, Any]],
    bias_direction: str,
    auditors: Sequence[AuditAgent],
    session: Optional[SessionStore] = None,
    scenario_config: Optional[Mapping[str, Any]] = None,
    run_dir: Optional[Path] = None,
) -> List[AuditVerdict]:
    """Run every auditor on the same slim brief. Independence is no shared conclusions."""
    evidence = collect_audit_evidence(
        designer=designer,
        ranked=ranked,
        scenario_config=scenario_config,
        run_dir=run_dir,
    )
    jobs = [
        (
            auditor,
            build_audit_brief(
                designer=designer,
                ranked=ranked,
                bias_direction=bias_direction,
                auditor=auditor,
                evidence=evidence,
            ),
        )
        for auditor in auditors
    ]
    if not jobs:
        return []
    if len(jobs) == 1:
        auditor, brief = jobs[0]
        return [
            run_lens_audit(
                llm_client=llm_client,
                brief=brief,
                auditor=auditor,
                session=session,
            )
        ]

    def _one(job: tuple) -> AuditVerdict:
        auditor, brief = job
        return run_lens_audit(
            llm_client=llm_client,
            brief=brief,
            auditor=auditor,
            session=session,
        )

    with ThreadPoolExecutor(max_workers=len(jobs), thread_name_prefix="ea-audit") as pool:
        return list(pool.map(_one, jobs))


def apply_claims_sweep(
    proposals: Dict[str, Any],
    registry: ClaimsRegistry,
    *,
    selected: Optional[Mapping[str, Any]] = None,
    extra_documents: Optional[Mapping[str, str]] = None,
) -> List[str]:
    """Rewrite naked retracted claims; refuse approved_final if any remain."""
    notes: List[str] = []
    documents = {
        "message": str(proposals.get("message") or ""),
        "reasoning": str(proposals.get("reasoning") or ""),
    }
    if extra_documents:
        documents.update(extra_documents)
    hits = registry.sweep_documents(documents)
    if not hits:
        registry.save()
        return notes

    rewritten = rewrite_body_from_selected(selected)
    proposals["message"] = rewritten["message"]
    proposals["reasoning"] = rewritten["reasoning"]
    notes.append(
        "claims sweep rewrote message/reasoning; retracted phrases were standing: "
        + ", ".join(sorted({str(hit["phrase"]) for hit in hits}))
    )
    documents["message"] = rewritten["message"]
    documents["reasoning"] = rewritten["reasoning"]
    leftover = registry.sweep_documents(documents)
    if leftover:
        notes.append(
            "claims sweep could not clear retracted phrases: "
            + ", ".join(sorted({str(hit["phrase"]) for hit in leftover}))
        )
        if proposals.get("final_status") == STATUS_APPROVED:
            proposals["final_status"] = STATUS_PROVISIONAL
            proposals["requires_supervisor_approval"] = True
            reason = str(proposals.get("selection_reason") or "").strip()
            suffix = "claims sweep: retracted assertions still stand in the body"
            proposals["selection_reason"] = f"{reason} | {suffix}".strip(" |")
            notes.append("final_status downgraded to provisional_final after failed sweep")
    registry.save()
    return notes


def strip_internal_proposal_keys(proposals: Dict[str, Any]) -> Dict[str, Any]:
    for key in INTERNAL_PROPOSAL_KEYS:
        proposals.pop(key, None)
    return proposals


def integrate_audit_panel(
    bundle: Any,
    designer: Mapping[str, Any],
    verdicts: Sequence[AuditVerdict],
    storage: DesignStorage,
) -> Dict[str, Any]:
    """Keep a runnable proposal; pin vetoed items to the installed machine.

    Auditors cannot invent a machine. Unusable replies abstain. Iterate
    also completes a partial profile from the machine this run flew, so
    an omitted key does not revert to the YAML baseline.
    """
    proposals = dict(designer)
    notes = list(proposals.get("parse_notes") or [])
    messages = list(proposals.get("deliberation_messages") or [])
    ranked = [
        dict(row)
        for row in (designer.get("ranked_candidates") or [])
        if isinstance(row, Mapping)
    ]
    selected_id = designer.get("selected_candidate_id")
    selected = next((row for row in ranked if row.get("candidate_id") == selected_id), None)
    designer_id = str(designer.get("proposed_by") or "eclss_designer_1")
    proposed_fields = dict(
        (selected or {}).get("fields") or _fields_from_changes(designer)
    )
    installed = read_capacity_fields(getattr(bundle, "scenario_config", {}) or {})
    vetoed = _collect_vetoed_fields(verdicts, proposed_fields)
    kept_fields, emptied = _pin_vetoed_to_installed(proposed_fields, vetoed, installed)
    if selected is not None:
        selected = dict(selected)
        selected["audited_fields"] = dict(kept_fields)
        selected["fields_unverified_after_audit"] = bool(vetoed)
        for index, row in enumerate(ranked):
            if row.get("candidate_id") == selected_id:
                ranked[index] = selected
                break

    if selected is not None:
        storage.claims.register(
            agent_id=designer_id,
            candidate_id=str(selected_id),
            local_candidate_id=str(selected.get("candidate_id") or ""),
            fields=kept_fields,
        )
        for record in ranked:
            if record.get("candidate_id") == selected_id:
                continue
            storage.claims.register(
                agent_id=designer_id,
                candidate_id=str(record.get("candidate_id") or ""),
                local_candidate_id=str(record.get("candidate_id") or ""),
                fields=record.get("fields") if isinstance(record.get("fields"), Mapping) else {},
            )
        storage.claims.retract_except(str(selected_id) if selected_id else None)

    usable = [row for row in verdicts if row.decision in {"approve", "reject"}]
    if emptied:
        proposals["final_status"] = STATUS_PROVISIONAL
        proposals["requires_supervisor_approval"] = True
        proposals["decision_source"] = "tool_use_audit_panel:kept_to_proceed"
        notes.append(
            "audit panel named every proposed change; kept the installed machine "
            "so the next run can proceed"
        )
        reason = str(proposals.get("selection_reason") or "").strip()
        proposals["selection_reason"] = (
            f"{reason} | audit panel would have left an empty proposal".strip(" |")
        )
    elif vetoed:
        proposals["final_status"] = STATUS_PROVISIONAL
        proposals["requires_supervisor_approval"] = True
        proposals["decision_source"] = "tool_use_audit_panel:item_veto"
        notes.append(
            "audit panel pinned vetoed items to the installed machine: "
            + ", ".join(sorted(vetoed))
        )
        reason = str(proposals.get("selection_reason") or "").strip()
        proposals["selection_reason"] = (
            f"{reason} | audit panel dropped {', '.join(sorted(vetoed))}".strip(" |")
        )
    elif usable:
        proposals["decision_source"] = "tool_use_audit_panel"
        notes.append(
            "audit panel approved: "
            + ", ".join(f"{row.agent_id}/{row.lens}" for row in usable)
        )
    else:
        notes.append("audit panel unusable; kept designer proposal")

    _write_kept_fields(proposals, kept_fields, installed=installed)

    designer_message = str(designer.get("message") or "").strip()
    designer_reasoning = str(designer.get("reasoning") or "").strip()
    proposals["message"] = designer_message
    proposals["reasoning"] = designer_reasoning
    sweep_notes = apply_claims_sweep(proposals, storage.claims, selected=selected)
    notes.extend(sweep_notes)

    audit_messages: List[str] = []
    audit_reasons: List[str] = []
    audit_records: List[Dict[str, Any]] = []
    for verdict in verdicts:
        header = f"{verdict.agent_id} ({verdict.lens}): {verdict.decision}"
        if verdict.message:
            audit_messages.append(f"{header} — {verdict.message}")
        else:
            audit_messages.append(header)
        if verdict.reasoning or verdict.fallback_reason:
            audit_reasons.append(
                f"{header} — {verdict.reasoning or verdict.fallback_reason}"
            )
        audit_records.append(
            {
                "agent_id": verdict.agent_id,
                "lens": verdict.lens,
                "decision": verdict.decision,
                "rejected_fields": list(verdict.rejected_fields),
                "message": verdict.message,
                "reasoning": verdict.reasoning,
                "fallback_reason": verdict.fallback_reason,
            }
        )
        messages.append(
            {
                "from_role": verdict.agent_id,
                "to_role": "team",
                "message": verdict.message or verdict.decision,
                "reasoning": verdict.reasoning or verdict.fallback_reason or "",
                "message_type": "comment",
                "metadata": {"lens": verdict.lens, "decision": verdict.decision},
            }
        )

    proposals["message"] = _join_sections(str(proposals.get("message") or ""), audit_messages)
    proposals["reasoning"] = _join_sections(
        str(proposals.get("reasoning") or ""), audit_reasons
    )
    proposals["audited_by"] = [verdict.agent_id for verdict in verdicts]
    proposals["audit"] = audit_records
    proposals["deliberation_messages"] = messages
    proposals["parse_notes"] = notes
    evidence = dict(proposals.get("evidence") or {})
    evidence["audit_panel"] = len(verdicts)
    proposals["evidence"] = evidence

    run_dir = Path(getattr(bundle, "run_dir", None) or ".")
    selection = {
        "selected_candidate_id": selected_id,
        "final_status": proposals.get("final_status"),
        "requires_supervisor_approval": proposals.get("requires_supervisor_approval"),
        "reason": proposals.get("selection_reason"),
    }
    _merge_audit_into_report(
        storage,
        {
            "design_family": DESIGN_FAMILY,
            "decision_source": proposals.get("decision_source"),
            "proposed_by": proposals.get("proposed_by"),
            "audited_by": proposals.get("audited_by"),
            "message": proposals["message"],
            "reasoning": proposals["reasoning"],
            "final_status": proposals.get("final_status"),
            "selection": selection,
            "audit": audit_records,
            "candidates": [DesignToolkit._ranking_row(record) for record in ranked],
            "notes": notes,
            "evidence": evidence,
        },
    )
    if ranked:
        _merge_audit_into_rankings(
            storage,
            {
                "baseline": designer.get("baseline_outcome") or {},
                "ranking": [DesignToolkit._ranking_row(record) for record in ranked],
                "selection": selection,
                "audit": audit_records,
            },
        )
    proposals["design_review_report_path"] = str(run_dir / "design_review_report.json")
    if ranked:
        proposals["candidate_rankings_path"] = str(run_dir / "candidate_rankings.json")

    return strip_internal_proposal_keys(proposals)


def _listed_fields(raw: Any) -> List[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    seen = set()
    fields: List[str] = []
    for item in raw:
        key = str(item or "").strip()
        if key and key in CAPACITY_KEYS and key not in seen:
            seen.add(key)
            fields.append(key)
    return fields


def _collect_vetoed_fields(
    verdicts: Sequence[AuditVerdict],
    proposed_fields: Mapping[str, Any],
) -> List[str]:
    allowed = {key for key in proposed_fields if key in CAPACITY_KEYS}
    seen = set()
    vetoed: List[str] = []
    for verdict in verdicts:
        if verdict.decision != "reject":
            continue
        for key in verdict.rejected_fields:
            if key in allowed and key not in seen:
                seen.add(key)
                vetoed.append(key)
    return vetoed


def _pin_vetoed_to_installed(
    proposed_fields: Mapping[str, Any],
    vetoed: Sequence[str],
    installed: Mapping[str, Any],
) -> tuple:
    """Complete three-key profile. Vetoed keys stay at the installed value."""
    dropped = set(vetoed)
    complete: Dict[str, Any] = {}
    for key in CAPACITY_KEYS:
        if key in dropped:
            if key in installed:
                complete[key] = installed[key]
            elif key in proposed_fields:
                complete[key] = proposed_fields[key]
            continue
        if key in proposed_fields:
            complete[key] = proposed_fields[key]
        elif key in installed:
            complete[key] = installed[key]
    proposed_keys = {key for key in proposed_fields if key in CAPACITY_KEYS}
    emptied = bool(dropped) and bool(proposed_keys) and proposed_keys <= dropped
    if complete:
        return complete, emptied
    return dict(proposed_fields), True


def _clip_speech(text: Any, limit: int = AUDIT_SPEECH_CHARS) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return f"{value[:limit]} …[{len(value) - limit} chars omitted]"


def _audit_outcome(outcome: Any) -> Dict[str, Any]:
    body = outcome if isinstance(outcome, Mapping) else {}
    view: Dict[str, Any] = {}
    for key in ("crew_remaining", "crew_initial", "critical_step_count", "warning_step_count"):
        if body.get(key) is not None:
            view[key] = body.get(key)
    view["scorecard"] = _scorecard(body)
    return view


def _audit_candidate_row(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "candidate_id": record.get("candidate_id"),
        "fields": record.get("fields"),
        "outcome": _audit_outcome(record.get("outcome")),
    }


def _audit_chain_view(memory: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(memory, Mapping) or memory.get("error"):
        return None
    view = {
        key: memory.get(key)
        for key in (
            "updated_after_iteration",
            "theoretical_floor",
            "best_full_survival",
            "last_effective_design",
            "known_bad_patterns",
        )
        if memory.get(key) is not None
    }
    return view or None


def _write_kept_fields(
    proposals: Dict[str, Any],
    kept_fields: Mapping[str, Any],
    *,
    installed: Mapping[str, Any],
) -> None:
    how_parts = []
    for key, value in kept_fields.items():
        before = installed.get(key)
        how_parts.append(
            f"{key}: {before} → {value}" if before is not None else f"{key}: {value}"
        )
    wrote = False
    for change in proposals.get("changes") or []:
        if not isinstance(change, dict):
            continue
        if change.get("change_kind") != "capacity_profile":
            continue
        payload = change.get("payload")
        if not isinstance(payload, dict) or "fields" not in payload:
            continue
        payload["fields"] = dict(kept_fields)
        change["how"] = ", ".join(how_parts)
        wrote = True
    if not wrote and kept_fields:
        proposals["changes"] = [
            {
                "change_kind": "capacity_profile",
                "payload": {"backend": "plant_sim", "fields": dict(kept_fields)},
                "how": ", ".join(how_parts),
            }
        ]


def _fields_from_changes(designer: Mapping[str, Any]) -> Dict[str, Any]:
    for change in designer.get("changes") or []:
        if not isinstance(change, Mapping):
            continue
        payload = change.get("payload") or {}
        fields = payload.get("fields") if isinstance(payload, Mapping) else None
        if isinstance(fields, Mapping):
            return dict(fields)
    return {}


def _join_sections(lead: str, extras: Sequence[str]) -> str:
    parts = [lead] if lead else []
    parts.extend(item for item in extras if item)
    return "\n\n".join(parts)


def _merge_audit_into_report(
    storage: DesignStorage,
    updates: Mapping[str, Any],
) -> None:
    """Keep the designer's report; add the panel. Do not replace the file."""
    report = dict(storage.artifacts.read_json("design_review_report.json"))
    existing_selection = (
        dict(report["selection"]) if isinstance(report.get("selection"), Mapping) else {}
    )
    existing_evidence = (
        dict(report["evidence"]) if isinstance(report.get("evidence"), Mapping) else {}
    )
    incoming_evidence = updates.get("evidence") if isinstance(updates.get("evidence"), Mapping) else {}
    existing_notes = list(report.get("notes") or [])
    for note in updates.get("notes") or []:
        if note not in existing_notes:
            existing_notes.append(note)
    report.update({key: value for key, value in updates.items() if key != "notes"})
    report["selection"] = {**existing_selection, **dict(updates.get("selection") or {})}
    report["evidence"] = {**existing_evidence, **dict(incoming_evidence)}
    report["notes"] = existing_notes
    storage.artifacts.write_json("design_review_report.json", report)


def _merge_audit_into_rankings(
    storage: DesignStorage,
    updates: Mapping[str, Any],
) -> None:
    """Keep the designer's ranking document; add the panel."""
    rankings = dict(storage.artifacts.read_json("candidate_rankings.json"))
    existing_selection = (
        dict(rankings["selection"]) if isinstance(rankings.get("selection"), Mapping) else {}
    )
    if not rankings.get("baseline") and updates.get("baseline"):
        rankings["baseline"] = updates["baseline"]
    rankings["ranking"] = updates.get("ranking") or rankings.get("ranking") or []
    rankings["selection"] = {**existing_selection, **dict(updates.get("selection") or {})}
    rankings["audit"] = updates.get("audit") or []
    storage.artifacts.write_json("candidate_rankings.json", rankings)
