"""One designer, then an independent audit panel, then a deterministic merge."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.agents.persona import ARCHETYPE_LENSES
from core.llm.base import invoke_llm
from core.llm.parsing import parse_json_response
from core.storage import DesignStorage
from core.storage.claims import ClaimsRegistry, rewrite_body_from_selected
from core.storage.session import SessionStore
from scenario.ssos_eclss_loop.design_eval import STATUS_APPROVED, STATUS_PROVISIONAL
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

AUDIT_CONTRACT = """\
Reply with ONE JSON object and nothing else.

If this lens finds no item to drop:
{"decision": "approve", "message": "what survived this lens",
 "reasoning": "what you checked"}

If this lens found a problem with one or more proposed items:
{"decision": "reject",
 "rejected_fields": ["plant_sim.wrs.max_feed_l_per_operation"],
 "message": "which items fail this lens",
 "reasoning": "why those items, not the whole machine"}

Rules: rejected_fields must be copied from the proposal. Do not invent a
machine, a new field, or a value. Items you do not name stay. An empty
proposal cannot be applied, so do not try to delete every item unless
you can name each one. You do not see the other auditors.
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
    count = max(1, int(raw.get("count") or len(DEFAULT_AUDIT_LENSES)))
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


def build_audit_brief(
    *,
    designer: Mapping[str, Any],
    ranked: Sequence[Mapping[str, Any]],
    bias_direction: str,
    auditor: AuditAgent,
) -> str:
    """Show one designer proposal to one auditor. Other auditors are absent."""
    selected_id = designer.get("selected_candidate_id")
    selected = next(
        (row for row in ranked if row.get("candidate_id") == selected_id),
        None,
    )
    proposal = {
        "proposed_by": designer.get("proposed_by"),
        "selected_candidate_id": selected_id,
        "final_status": designer.get("final_status"),
        "message": designer.get("message"),
        "reasoning": designer.get("reasoning"),
        "fields": (selected or {}).get("fields") or _fields_from_changes(designer),
        "outcome": {
            key: ((selected or {}).get("outcome") or {}).get(key)
            for key in (
                "crew_remaining",
                "crew_initial",
                "critical_step_count",
                "warning_step_count",
                "evaluation_compact",
            )
        }
        if selected
        else designer.get("expected_outcome"),
    }
    catalog = [
        {
            "candidate_id": record.get("candidate_id"),
            "fields": record.get("fields"),
            "final_eligible": record.get("final_eligible"),
            "final_ineligible_reasons": record.get("final_ineligible_reasons"),
            "rank": record.get("rank"),
            "outcome": {
                key: (record.get("outcome") or {}).get(key)
                for key in (
                    "crew_remaining",
                    "crew_initial",
                    "critical_step_count",
                    "warning_step_count",
                    "evaluation_compact",
                )
            },
        }
        for record in ranked
    ]
    sections = [
        f"You are {auditor.agent_id}, an independent adoption auditor.",
        auditor.persona,
        "",
        "One designer (no thinking lens) proposed a verified machine.",
        "Check that proposal from your lens. Approve it or reject it.",
        "You do not see the other auditors. You may not invent a machine.",
    ]
    if bias_direction:
        sections += ["", "### Declared bias of this run", bias_direction]
    sections += [
        "",
        "### Designer proposal (shown to you only among the auditors)",
        json.dumps(proposal, ensure_ascii=False, default=str, indent=2),
        "",
        "### Verified candidates the designer already simulated",
        json.dumps(catalog, ensure_ascii=False, default=str, indent=2),
        "",
        "### Output contract",
        AUDIT_CONTRACT,
    ]
    return "\n".join(sections)


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
    """Keep a runnable proposal; drop only the items the panel named.

    Auditors cannot invent a machine. Unusable replies abstain. If every
    item would be dropped, the designer's fields stay so the next run can
    proceed, and the document is provisional.
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
    vetoed = _collect_vetoed_fields(verdicts, proposed_fields)
    kept_fields, emptied = _keep_runnable_fields(proposed_fields, vetoed)
    if selected is not None:
        selected = dict(selected)
        selected["fields"] = dict(kept_fields)
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
            "audit panel named every item; kept designer fields so the next run can proceed"
        )
        reason = str(proposals.get("selection_reason") or "").strip()
        proposals["selection_reason"] = (
            f"{reason} | audit panel would have left an empty proposal".strip(" |")
        )
    elif vetoed:
        proposals["final_status"] = STATUS_PROVISIONAL
        proposals["requires_supervisor_approval"] = True
        proposals["decision_source"] = "tool_use_audit_panel:item_veto"
        notes.append("audit panel dropped items: " + ", ".join(sorted(vetoed)))
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

    _write_kept_fields(
        proposals,
        kept_fields,
        installed=read_capacity_fields(getattr(bundle, "scenario_config", {}) or {}),
    )

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
    report = {
        "design_family": DESIGN_FAMILY,
        "decision_source": proposals.get("decision_source"),
        "proposed_by": proposals.get("proposed_by"),
        "audited_by": proposals.get("audited_by"),
        "message": proposals["message"],
        "reasoning": proposals["reasoning"],
        "final_status": proposals.get("final_status"),
        "selection": {
            "selected_candidate_id": selected_id,
            "final_status": proposals.get("final_status"),
            "requires_supervisor_approval": proposals.get("requires_supervisor_approval"),
            "reason": proposals.get("selection_reason"),
        },
        "audit": audit_records,
        "candidates": [DesignToolkit._ranking_row(record) for record in ranked],
        "notes": notes,
    }
    storage.artifacts.write_json("design_review_report.json", report)
    if ranked:
        storage.artifacts.write_json(
            "candidate_rankings.json",
            {
                "baseline": designer.get("baseline_outcome") or {},
                "ranking": [DesignToolkit._ranking_row(record) for record in ranked],
                "selection": report["selection"],
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


def _keep_runnable_fields(
    proposed_fields: Mapping[str, Any],
    vetoed: Sequence[str],
) -> tuple:
    dropped = {key for key in vetoed}
    kept = {key: value for key, value in proposed_fields.items() if key not in dropped}
    if kept:
        return kept, False
    return dict(proposed_fields), True


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
