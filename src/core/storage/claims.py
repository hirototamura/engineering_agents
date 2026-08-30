"""Claims table and mechanical sweep of retracted assertions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


STATUS_STANDING = "standing"
STATUS_RETRACTED = "retracted"


def _norm(value: Any) -> str:
    return str(value).strip()


def claim_phrases(
    *,
    candidate_id: Optional[str],
    local_candidate_id: Optional[str] = None,
    fields: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    """Search strings that would leave this recommendation standing in prose."""
    phrases: List[str] = []
    # Namespaced ids only. The local tail (candidate_001) is a substring of
    # every namespaced id and would false-hit the adopted recommendation.
    text = _norm(candidate_id)
    if text:
        phrases.append(text)
    _ = local_candidate_id
    for key, value in (fields or {}).items():
        if value is None:
            continue
        phrases.append(f"{key}={value}")
        phrases.append(f"{key}: {value}")
    # Stable unique order, longest first so a namespaced id hits before the tail.
    unique = sorted(set(phrases), key=len, reverse=True)
    return unique


class ClaimsRegistry:
    """Register design claims, retract losers, sweep document bodies."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.claims: List[Dict[str, Any]] = []
        if self.path.exists():
            self.load()

    def register(
        self,
        *,
        agent_id: str,
        candidate_id: str,
        fields: Optional[Mapping[str, Any]] = None,
        local_candidate_id: Optional[str] = None,
        status: str = STATUS_STANDING,
    ) -> Dict[str, Any]:
        claim = {
            "claim_id": f"{agent_id}:{candidate_id}",
            "agent_id": agent_id,
            "candidate_id": candidate_id,
            "local_candidate_id": local_candidate_id,
            "fields": dict(fields or {}),
            "status": status,
            "phrases": claim_phrases(
                candidate_id=candidate_id,
                local_candidate_id=local_candidate_id,
                fields=fields,
            ),
        }
        self.claims.append(claim)
        return claim

    def retract_except(self, selected_candidate_id: Optional[str]) -> None:
        selected = _norm(selected_candidate_id)
        for claim in self.claims:
            if selected and _norm(claim.get("candidate_id")) == selected:
                claim["status"] = STATUS_STANDING
            else:
                claim["status"] = STATUS_RETRACTED

    def retracted(self) -> List[Dict[str, Any]]:
        return [claim for claim in self.claims if claim.get("status") == STATUS_RETRACTED]

    def standing(self) -> List[Dict[str, Any]]:
        return [claim for claim in self.claims if claim.get("status") == STATUS_STANDING]

    def sweep_text(self, text: str) -> List[Dict[str, Any]]:
        """Hits where a retracted phrase stands without a retraction note nearby.

        Phrases that also belong to a still-standing claim (same fields as the
        adopted design) are not hits — the body is allowed to state the winner.
        """
        body = text or ""
        lowered = body.lower()
        standing_phrases = {
            phrase
            for claim in self.standing()
            for phrase in (claim.get("phrases") or [])
            if phrase
        }
        hits: List[Dict[str, Any]] = []
        for claim in self.retracted():
            for phrase in claim.get("phrases") or []:
                if not phrase or phrase not in body or phrase in standing_phrases:
                    continue
                index = body.find(phrase)
                window = lowered[max(0, index - 80) : index + len(phrase) + 80]
                if any(
                    token in window
                    for token in ("not adopted", "withdrawn", "[retracted]", "this claim is retracted")
                ):
                    continue
                hits.append(
                    {
                        "claim_id": claim.get("claim_id"),
                        "candidate_id": claim.get("candidate_id"),
                        "phrase": phrase,
                    }
                )
                break
        return hits

    def sweep_documents(self, documents: Mapping[str, str]) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for name, text in documents.items():
            for hit in self.sweep_text(text):
                hits.append({**hit, "document": name})
        return hits

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"claims": self.claims}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.claims = []
            return
        rows = data.get("claims") if isinstance(data, dict) else None
        self.claims = [row for row in (rows or []) if isinstance(row, dict)]


def rewrite_body_from_selected(
    selected: Optional[Mapping[str, Any]],
) -> Dict[str, str]:
    """Deterministic prose that only states the adopted candidate."""
    if not selected:
        return {
            "message": "No candidate was adopted.",
            "reasoning": "The ensemble ranking found no selectable design.",
        }
    candidate_id = selected.get("candidate_id")
    fields = selected.get("fields") or {}
    field_bits = ", ".join(f"{key}={value}" for key, value in fields.items())
    return {
        "message": (
            f"Adopted ranked candidate {candidate_id}"
            + (f" ({field_bits})" if field_bits else "")
            + "."
        ),
        "reasoning": (
            f"Ensemble ranking selected {candidate_id}. "
            "Losing lens recommendations are retracted and must not stand in the body."
        ),
    }


