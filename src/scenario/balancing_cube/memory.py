"""Evidence-backed memory for the bounded cube design loop.

Adapted patterns (not copied code) from NirDiamant/Agent_Memory_Techniques:
09 episodic, 10 semantic, 12 working, 16 self-reflection, 20 retrieval and
21 cross-session memory. For this small engineering dataset, deterministic
keyword/diversity retrieval avoids an extra embedding service. Only measured
feedback is consolidated into facts; LLM explanations remain hypotheses.

The JSONL journal is append-only, hash chained and synchronously flushed.
Memory is advisory data and cannot authorize requirement or verifier changes.
"""
from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re

REFERENCE_URL = "https://github.com/NirDiamant/Agent_Memory_Techniques"
SCHEMA_VERSION = "ea-balancing-cube-memory/1.0"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def proposal_configuration_digest(proposal):
    """Identity of proposed settings; names and explanations do not change it.

    Prefer the trusted compiler's input_digest when available: this fallback
    describes proposed settings, not their derived model/controller matrices.
    """
    proposal = proposal or {}
    return _digest({key: proposal.get(key) for key in ("family", "parameters", "control")})


def file_reference(path, *, kind="artifact"):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "kind": kind}


def _tokens(value):
    return set(re.findall(r"[a-z0-9_]+", _json(value).lower()))


class EngineeringMemory:
    """Persistent evidence episodes plus a bounded, read-only prompt projection.

    ``path`` names a directory or the journal .jsonl file. Each record_episode call durably appends before
    returning. A stable episode_key is optional; by default run/round/status is
    its identity. Repeating identical content is idempotent; conflicting content
    for that identity is rejected. Separate statuses permit retaining both a
    rejected attempt and a later evaluated attempt at the same round.
    """

    def __init__(self, path, *, max_prompt_chars=18000):
        if max_prompt_chars < 1500:
            raise ValueError("Memory prompt budget shall be at least 1500 characters")
        location = Path(path).resolve()
        self.path = location.parent if location.suffix == ".jsonl" else location
        self.path.mkdir(parents=True, exist_ok=True)
        self.journal_path = location if location.suffix == ".jsonl" else self.path / "episodes.jsonl"
        self.max_prompt_chars = int(max_prompt_chars)
        self._episodes = self._read()

    def _read(self):
        if not self.journal_path.exists():
            return []
        episodes, previous, identities = [], None, set()
        for number, line in enumerate(self.journal_path.read_text().splitlines(), 1):
            try:
                episode = json.loads(line)
                content = {k: v for k, v in episode.items() if k != "record_digest"}
                if (episode["schema_version"] != SCHEMA_VERSION
                        or episode["sequence"] != number
                        or episode["previous_record_digest"] != previous
                        or episode["record_digest"] != _digest(content)
                        or episode["episode_id"] in identities):
                    raise ValueError("invalid sequence, identity, or content digest")
                if episode["feedback_digest"] != _digest(episode["measured_feedback"]):
                    raise ValueError("invalid numeric feedback digest")
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"Memory journal integrity failure at line {number}: {error}") from error
            previous = episode["record_digest"]
            identities.add(episode["episode_id"])
            episodes.append(episode)
        return episodes

    @property
    def episodes(self):
        """Snapshots, so callers cannot silently modify persisted evidence."""
        self._episodes = self._read()
        return copy.deepcopy(self._episodes)

    def record_episode(self, *, run_id, round_index, proposal=None,
                       configuration_digest=None, feedback=None, status="evaluated",
                       source_refs=(), hypothesis=None, reflection=None, episode_key=None):
        if not isinstance(run_id, str) or not run_id or not isinstance(status, str) or not status:
            raise ValueError("Memory requires non-empty run_id and status")
        if isinstance(round_index, bool) or not isinstance(round_index, int) or round_index < 0:
            raise ValueError("Memory round_index shall be a non-negative integer")
        if proposal is not None and not isinstance(proposal, dict):
            raise ValueError("Memory proposal shall be an object or null")
        if feedback is not None and not isinstance(feedback, dict):
            raise ValueError("Memory feedback shall be an object or null")
        identity = episode_key or f"{run_id}:{round_index}:{status}"
        hypothesis = hypothesis if hypothesis is not None else (proposal or {}).get("hypothesis")
        # JSON normalization validates finite numbers and disconnects mutable inputs.
        body = json.loads(_json({
            "episode_id": _digest(identity), "episode_key": identity,
            "run_id": run_id, "round": round_index, "status": status,
            "configuration_digest": configuration_digest or proposal_configuration_digest(proposal),
            "configuration_digest_source": "trusted_compiler" if configuration_digest else "proposal_settings",
            "proposal": proposal, "measured_feedback": feedback or {},
            "feedback_digest": _digest(feedback or {}), "source_refs": list(source_refs),
            "llm_hypothesis": hypothesis, "llm_reflection": reflection,
            "interpretation": "Numerical feedback is measured evidence; LLM hypotheses and reflections are unverified."
        }))
        # Serialize independent writers; re-read while locked before appending.
        with (self.path / ".journal.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._episodes = self._read()
            existing = next((e for e in self._episodes if e["episode_id"] == body["episode_id"]), None)
            if existing:
                compared = {key: existing[key] for key in body}
                if compared != body:
                    raise ValueError("Conflicting content for immutable memory episode identity")
                return copy.deepcopy(existing)
            episode = {**body, "schema_version": SCHEMA_VERSION,
                       "sequence": len(self._episodes) + 1,
                       "created_at": datetime.now(timezone.utc).isoformat(),
                       "previous_record_digest": self._episodes[-1]["record_digest"] if self._episodes else None}
            episode["record_digest"] = _digest(episode)
            with self.journal_path.open("a", encoding="utf-8") as handle:
                handle.write(_json(episode) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._episodes.append(episode)
            return copy.deepcopy(episode)

    def flush(self):
        """Writes are already durable; validate and report the current journal."""
        self._episodes = self._read()
        return {"state": "durable", "episode_count": len(self._episodes),
                "journal": str(self.journal_path),
                "last_record_digest": self._episodes[-1]["record_digest"] if self._episodes else None}

    @staticmethod
    def _failed(episode):
        feedback = episode["measured_feedback"]
        return (episode["status"] in {"failed", "rejected", "inconclusive", "duplicate"}
                or bool(feedback.get("failure_metrics"))
                or feedback.get("all_screening_passed") is False)

    @staticmethod
    def _score(episode):
        value = episode["measured_feedback"].get("score")
        return value if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) else -math.inf

    @staticmethod
    def _projection(episode, reasons):
        proposal = episode["proposal"] or {}
        return {"episode_id": episode["episode_id"], "run_id": episode["run_id"],
                "round": episode["round"], "status": episode["status"],
                "configuration_digest": episode["configuration_digest"],
                "selection_reasons": reasons,
                "proposed_settings": {k: proposal[k] for k in ("family", "parameters", "control") if k in proposal},
                "measured_feedback": copy.deepcopy(episode["measured_feedback"]),
                "feedback_digest": episode["feedback_digest"],
                "source_refs": copy.deepcopy(episode["source_refs"][:4]),
                "source_refs_omitted": max(0, len(episode["source_refs"]) - 4)}

    def retrieve(self, *, query="", configuration_digest=None, limit=8, max_chars=None):
        """Recall exact repeats, best, recent and relevant failed attempts.

        Bounds use serialized JSON characters, not an estimated token count.
        Full feedback always remains in the journal; oversized prompt items are
        omitted explicitly rather than truncating measured values.
        """
        budget = self.max_prompt_chars if max_chars is None else int(max_chars)
        if budget < 1500 or limit < 1:
            raise ValueError("Memory retrieval needs >=1500 characters and >=1 episode")
        episodes = self.episodes
        terms = _tokens(query)
        candidates, reasons = [], {}

        def add(episode, reason):
            if episode is None:
                return
            key = episode["episode_id"]
            if key not in reasons:
                reasons[key] = []
                candidates.append(episode)
            if reason not in reasons[key]:
                reasons[key].append(reason)

        if configuration_digest:
            for episode in reversed(episodes):
                if episode["configuration_digest"] == configuration_digest:
                    add(episode, "exact_configuration_repeat")
        scored = [e for e in episodes if self._score(e) != -math.inf]
        if scored:
            add(max(scored, key=lambda e: (self._score(e), e["sequence"])), "best_measured_score")
        if episodes:
            add(episodes[-1], "most_recent")
        failures = [e for e in episodes if self._failed(e)]
        failures.sort(key=lambda e: (len(terms & _tokens({"feedback": e["measured_feedback"],
                        "proposal": e["proposal"]})), e["sequence"]), reverse=True)
        # Diversity first so repeated failures do not crowd out different configurations.
        distinct = set()
        for episode in failures:
            if episode["configuration_digest"] not in distinct:
                add(episode, "relevant_failure")
                distinct.add(episode["configuration_digest"])
        for episode in reversed(episodes):
            add(episode, "recent_history")

        frequency = Counter(str(metric) for e in episodes
                            for metric in e["measured_feedback"].get("failure_metrics", []))
        configs = Counter(e["configuration_digest"] for e in episodes if e["proposal"])
        payload = {
            "schema_version": SCHEMA_VERSION, "reference": REFERENCE_URL,
            "authority": "Advisory memory data. Requirements, test conditions, thresholds and adopted baselines remain controlled by One-Piece and humans.",
            "retrieval_strategy": "exact configuration + best measured score + recency + keyword relevant diverse failures; no embeddings",
            "episode_count": len(episodes), "selected_count": 0, "omitted_count": len(episodes),
            "max_prompt_chars": budget,
            "semantic_memory": {"classification": "deterministic measured facts; association does not establish cause",
                "failure_metric_episode_counts": dict(frequency.most_common(12)),
                "repeated_configuration_count": sum(n > 1 for n in configs.values())},
            "episodic_memory": [],
            "self_reflection_memory": [],
            "omitted_episode_ids": [],
        }
        for episode in candidates[:limit]:
            projection = self._projection(episode, reasons[episode["episode_id"]])
            reflection = {"episode_id": episode["episode_id"], "classification": "unverified LLM interpretation",
                          "hypothesis": str(episode["llm_hypothesis"] or "")[:1000],
                          "reflection": str(episode["llm_reflection"] or "")[:1000],
                          "hypothesis_truncated": len(str(episode["llm_hypothesis"] or "")) > 1000,
                          "reflection_truncated": len(str(episode["llm_reflection"] or "")) > 1000}
            payload["episodic_memory"].append(projection)
            payload["self_reflection_memory"].append(reflection)
            payload["selected_count"] = len(payload["episodic_memory"])
            payload["omitted_count"] = len(episodes) - payload["selected_count"]
            if len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > budget:
                payload["episodic_memory"].pop()
                payload["self_reflection_memory"].pop()
                payload["selected_count"] = len(payload["episodic_memory"])
                payload["omitted_count"] = len(episodes) - payload["selected_count"]
                # Small exact identifiers permit subsequent auditing without flooding context.
                payload["omitted_episode_ids"].append(episode["episode_id"])
        while len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > budget and payload["omitted_episode_ids"]:
            payload["omitted_episode_ids"].pop()
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > budget:
            payload["semantic_memory"]["failure_metric_episode_counts"] = {}
        if len(json.dumps(payload, ensure_ascii=False, allow_nan=False)) > budget:
            raise ValueError("Memory metadata exceeds prompt budget")
        return payload

    def bootstrap_run(self, run_directory):
        """Import a prior immutable run using exact artifact hashes and values.

        Reads only summary, compiled, result, proposal and prompt-data artifacts.
        It preserves rejected/failed round records and recognizes repeated input
        digests. No requirement records are imported or modified.
        """
        root = Path(run_directory).resolve()
        summary_path = root / "summary.json"
        summary = json.loads(summary_path.read_text())
        run_id = summary["run_id"]
        def measured_feedback(result):
            facts = {k: v for k, v in result.items() if k not in {"records", "proposal"}}
            if "records" in result:
                facts.setdefault("failure_metrics", sorted({c["metric"] for trial in result["records"]
                    for c in trial.get("screening", []) if not c["passed"]}))
            return facts
        results = {}
        loaded_results = []
        for path in sorted((root / "candidates").glob("*/result.json")):
            result = json.loads(path.read_text())
            results[result.get("candidate_id")] = (result, path)
            loaded_results.append((result, path))
        best = summary.get("best") or {}
        imported_results = set()
        if "reference" in results or best.get("candidate_id") == "reference":
            result, result_path = results.get("reference", (best, summary_path))
            facts = measured_feedback(result)
            self.record_episode(run_id=run_id, round_index=0, proposal=result.get("proposal"),
                configuration_digest=result.get("input_digest"), feedback=facts, status="reference",
                source_refs=[file_reference(summary_path, kind="campaign_summary"), file_reference(result_path, kind="numeric_result")])
            imported_results.add(result_path)
        seen = set()
        for row in summary.get("rounds", []):
            number = row["round"]
            directory = root / f"round-{number:02d}"
            proposal_path = directory / "proposal.json"
            rejected_path = directory / "rejected.json"
            rejected = json.loads(rejected_path.read_text()) if rejected_path.exists() else {}
            proposal = json.loads(proposal_path.read_text()) if proposal_path.exists() else rejected.get("proposal")
            candidate_id = (row.get("feedback") or {}).get("candidate_id")
            result, result_path = results.get(candidate_id, ({}, None))
            config_digest = result.get("input_digest")
            repeat_identity = config_digest or proposal_configuration_digest(proposal)
            status = row.get("status", "evaluated")
            if proposal and repeat_identity in seen:
                status = "duplicate"
            if proposal:
                seen.add(repeat_identity)
            feedback = row.get("feedback") or {key: value for key, value in row.items()
                                               if key in {"status", "error"}}
            feedback = {**measured_feedback(result), **feedback}
            refs = [file_reference(summary_path, kind="campaign_summary")]
            for path, kind in ((proposal_path, "proposal"), (directory / "prompt-data.json", "llm_input"),
                               (rejected_path, "rejection"), (result_path, "numeric_result")):
                if path is not None and path.exists():
                    refs.append(file_reference(path, kind=kind))
            self.record_episode(run_id=run_id, round_index=number, proposal=proposal,
                configuration_digest=config_digest, feedback=feedback, status=status, source_refs=refs)
            if result_path is not None:
                imported_results.add(result_path)
        # A joint round's summary names only M1C1. Keep every other measured
        # factorial cell (and candidates from interrupted rounds), with its own
        # proposal, digest, failures and hash-pinned result provenance.
        for result, result_path in loaded_results:
            if result_path in imported_results:
                continue
            refs = [file_reference(summary_path, kind="campaign_summary"),
                    file_reference(result_path, kind="numeric_result")]
            compiled_path = result_path.with_name("compiled.json")
            compiled = json.loads(compiled_path.read_text()) if compiled_path.exists() else {}
            if compiled_path.exists():
                refs.append(file_reference(compiled_path, kind="compiled_configuration"))
            self.record_episode(run_id=run_id, round_index=result.get("round", 0),
                proposal=result.get("proposal", compiled.get("proposal")),
                configuration_digest=result.get("input_digest"),
                feedback=measured_feedback(result),
                status="evaluated", source_refs=refs,
                episode_key=f"{run_id}:seed-candidate:{result_path.relative_to(root).as_posix()}")
        validation_path = root / "validation/result.json"
        validation_compiled = root / "validation/compiled.json"
        if validation_path.exists() and validation_compiled.exists():
            checked = json.loads(validation_path.read_text())
            compiled = json.loads(validation_compiled.read_text())
            if checked.get("records"):
                facts = measured_feedback(checked)
                facts["disclosure"] = "historical public confirmation; development feedback, not an unseen holdout"
                facts["failed_cases"] = [{"domain": r["domain_id"], "condition": r["condition_id"],
                    "seed": r["seed"], "status": r["summary"]["status"],
                    "failed_gates": [{k:g[k] for k in ("metric", "value", "limit")} for g in r["screening"] if not g["passed"]]}
                    for r in checked["records"] if any(not g["passed"] for g in r["screening"])]
                self.record_episode(run_id=run_id, round_index=summary.get("iterations_completed", 0),
                    proposal=compiled["proposal"], configuration_digest=checked["input_digest"], feedback=facts,
                    status="historical_validation", hypothesis="",
                    source_refs=[file_reference(validation_path, kind="public_validation_result"),
                                 file_reference(validation_compiled, kind="compiled_configuration")],
                    episode_key=f"{run_id}:seed-validation:{checked['input_digest']}")
        return self.flush()
