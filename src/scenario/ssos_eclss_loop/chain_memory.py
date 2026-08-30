"""The little the next iteration is told about the ones before it.

Each iteration of the design chain reads its own run and nothing else. That is
deliberate — the state a decision is taken from is assembled fresh, so nothing
has to be remembered. But it means the chain has no memory *between* rounds,
and an observed fifty-iteration run paid for that: iteration 24 kept all fifty
occupants alive with ARS 20.8 / OGS 42.0, iteration 25 proposed a WRS-only
change, ARS and OGS fell back to their baseline values, and the next run came
back 0/50. The design that worked was not rejected. It was forgotten.

This module keeps one small file at the root of a chain — a few hundred bytes
naming the best design that kept everyone alive, the sizing that was actually
installed last round, the theoretical floor under each subsystem, and the
handful of ways this chain has already lost the crew. It is capped at 4 KB
because its only reader is a language model with a finite context window: it is
a note, not a history, and it never grows with the iteration count.

What it is not: it does not *apply* anything. A partial proposal still drops
the fields it omits — fixing that means merging applied designs, which is a
change to how proposals are carried, not to what the designer is told. This
file only makes the loss visible to whoever writes the next proposal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_variables import (
    BASELINE_CAPACITY,
    CAPACITY_KEYS,
    read_capacity_fields,
)

CHAIN_MEMORY_FILENAME = "compact_chain_memory.json"
SCHEMA_VERSION = "1.0"

# The file is read into a prompt, so its size is a design constraint and not an
# implementation detail. Anything past this is trimmed before it is written.
MAX_MEMORY_BYTES = 4096
MAX_BAD_PATTERNS = 5

ARS_KEY = "plant_sim.ars.capacity_kg_day"
OGS_KEY = "plant_sim.ogs.max_o2_kg_day"
WRS_KEY = "plant_sim.wrs.max_feed_l_per_operation"

PATTERN_DROPPED_TO_BASELINE = "dropped_ars_ogs_to_baseline"
PATTERN_BELOW_FLOOR = "below_theoretical_floor"

PATTERN_DESCRIPTIONS = {
    PATTERN_DROPPED_TO_BASELINE: (
        "A partial proposal omitted ARS/OGS and the next run reset them to "
        "baseline, losing the crew."
    ),
    PATTERN_BELOW_FLOOR: (
        "ARS or OGS installed below the theoretical floor, and occupants were lost."
    ),
}

OBJECTIVE = {
    "primary": "maximize_crew_remaining",
    "secondary": "maximize_evaluation_score",
    "notes": "Treat survival as lexicographically prior to score.",
}

PROPOSAL_GUIDANCE = {
    "prefer_complete_capacity_profile": True,
    "include_all_design_variables": list(CAPACITY_KEYS),
    "do_not_reduce_below_best_without_reason": True,
}

# Ranking used only to break a tie on score: a design that can be paid for
# beats one that cannot, and a known over-budget design beats an unknown.
_CONSTRAINT_RANK = {"ok": 0, "over_budget": 1}
_CONSTRAINT_RANK_OTHER = 2

_TOOL_THEORETICAL_CAPACITY = "compute_theoretical_capacity"


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #
def chain_memory_path(chain_dir: Path) -> Path:
    return Path(chain_dir) / CHAIN_MEMORY_FILENAME


def find_chain_memory(run_dir: Path) -> Optional[Path]:
    """The memory file governing *run_dir*, if a chain wrote one.

    An iteration lives one level under the chain root, so the file is looked
    for beside the run and then above it. A run that is not part of a chain
    finds nothing, which is not an error — it is the first round.
    """
    run_dir = Path(run_dir)
    for candidate in (run_dir, run_dir.parent):
        path = candidate / CHAIN_MEMORY_FILENAME
        if path.is_file():
            return path
    return None


def load_chain_memory(run_dir: Path) -> Optional[Dict[str, Any]]:
    """What the earlier iterations left for this one.

    ``None`` when there is no memory yet. A file that cannot be read comes back
    as an error object rather than an exception: a corrupt note is a reason to
    design without one, never a reason to stop designing.
    """
    path = find_chain_memory(run_dir)
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "error": "failed_to_load_chain_memory",
            "path": str(path),
            "message": f"{type(exc).__name__}: {exc}",
        }
    if not isinstance(payload, Mapping):
        return {
            "error": "failed_to_load_chain_memory",
            "path": str(path),
            "message": "chain memory is not a JSON object",
        }
    return dict(payload)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def capacity_keys_in_document(document: Optional[Mapping[str, Any]]) -> List[str]:
    """Which design variables a proposal document actually named.

    A proposal that names two of the three is the failure this module exists to
    make visible, so "which ones" has to be answerable from the document alone.
    """
    named: List[str] = []
    for change in (document or {}).get("changes") or []:
        if not isinstance(change, Mapping):
            continue
        if change.get("change_kind") != "capacity_profile":
            continue
        fields = (change.get("payload") or {}).get("fields")
        if not isinstance(fields, Mapping):
            continue
        for key in fields:
            if key in CAPACITY_KEYS and key not in named:
                named.append(key)
    return named


# --------------------------------------------------------------------------- #
# the theoretical floor
# --------------------------------------------------------------------------- #
def theoretical_floor_from_trace(trace_path: Path) -> Dict[str, float]:
    """The smallest each subsystem can be and still meet the crew's demand.

    Taken from the design agent's own ``compute_theoretical_capacity`` call
    rather than recomputed here, so the number in the memory is the number the
    designer was shown. Calls that overrode the crew size are skipped: they
    answer a different question.
    """
    trace_path = Path(trace_path)
    if not trace_path.is_file():
        return {}
    floor: Dict[str, float] = {}
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, Mapping) or row.get("tool") != _TOOL_THEORETICAL_CAPACITY:
            continue
        if (row.get("arguments") or {}).get("crew_size") is not None:
            continue
        result = row.get("result")
        if not isinstance(result, Mapping):
            result = _parse_excerpt(row.get("result_excerpt"))
        subsystems = (result or {}).get("subsystems")
        if not isinstance(subsystems, Mapping):
            continue
        found = {
            ARS_KEY: _number((subsystems.get("ars") or {}).get("required_nameplate_kg_day")),
            OGS_KEY: _number((subsystems.get("ogs") or {}).get("required_nameplate_kg_day")),
            # The WRS batch has to clear one step's worth of feed, or the buffer
            # grows however many operations a day the busy guard allows.
            WRS_KEY: _number((subsystems.get("wrs") or {}).get("expected_feed_l_per_step")),
        }
        floor.update({key: value for key, value in found.items() if value is not None})
    return floor


def _parse_excerpt(excerpt: Any) -> Dict[str, Any]:
    """A traced result that was only kept as clipped text, if it survived intact."""
    if not isinstance(excerpt, str):
        return {}
    try:
        payload = json.loads(excerpt)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# --------------------------------------------------------------------------- #
# updating
# --------------------------------------------------------------------------- #
def _blank_memory() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_after_iteration": None,
        "objective": dict(OBJECTIVE),
        "theoretical_floor": {},
        "best_full_survival": None,
        "last_effective_design": None,
        "known_bad_patterns": [],
        "proposal_guidance": dict(PROPOSAL_GUIDANCE),
    }


def _constraint_rank(status: Any) -> int:
    return _CONSTRAINT_RANK.get(str(status), _CONSTRAINT_RANK_OTHER)


def _constraint_status(config: Mapping[str, Any], fields: Mapping[str, float]) -> Optional[str]:
    try:
        constraints = DesignConstraints.from_scenario_config(config)
        return constraints.evaluate(fields).get("constraint_status")
    except Exception:  # a label is a nicety; losing it must not lose the memory
        return None


def _round_fields(fields: Mapping[str, float]) -> Dict[str, float]:
    return {key: round(float(value), 4) for key, value in fields.items()}


def _bump_pattern(
    patterns: List[Dict[str, Any]],
    pattern_id: str,
    *,
    thresholds: Optional[Mapping[str, Any]] = None,
) -> None:
    for pattern in patterns:
        if pattern.get("id") == pattern_id:
            pattern["observed_count"] = int(pattern.get("observed_count") or 0) + 1
            if thresholds:
                pattern["thresholds"] = dict(thresholds)
            return
    record: Dict[str, Any] = {
        "id": pattern_id,
        "description": PATTERN_DESCRIPTIONS.get(pattern_id, pattern_id),
        "observed_count": 1,
        "avoid_if_possible": True,
    }
    if thresholds:
        record["thresholds"] = dict(thresholds)
    patterns.append(record)


def _detect_dropped_to_baseline(
    *,
    applied_capacity_keys: Optional[Sequence[str]],
    fields: Mapping[str, float],
    previous: Optional[Mapping[str, Any]],
) -> bool:
    """Did a partial proposal hand back a subsystem the chain had already grown?

    ``applied_capacity_keys`` is what the document applied to *this* run named.
    ``None`` means nothing was applied, which cannot drop anything.
    """
    if not applied_capacity_keys:
        return False
    named = set(applied_capacity_keys)
    previous_fields = (previous or {}).get("fields") or {}
    for key in (ARS_KEY, OGS_KEY):
        if key in named:
            continue
        if abs(float(fields.get(key, 0.0)) - BASELINE_CAPACITY[key]) > 1e-9:
            continue
        was = _number(previous_fields.get(key))
        if was is None or was > BASELINE_CAPACITY[key] + 1e-9:
            # Either the chain had grown it and this run gave it back, or there
            # is no earlier record and an omitted field sits exactly on the
            # baseline. Both are the shape being counted.
            return True
    return False


def _detect_below_floor(
    *,
    fields: Mapping[str, float],
    floor: Mapping[str, Any],
    crew_remaining: Any,
    crew_initial: Any,
) -> Optional[Dict[str, Any]]:
    if not isinstance(crew_remaining, int) or not isinstance(crew_initial, int):
        return None
    if crew_remaining >= crew_initial:
        return None
    breached: Dict[str, Any] = {}
    for key in (ARS_KEY, OGS_KEY):
        limit = _number(floor.get(key))
        installed = _number(fields.get(key))
        if limit is None or installed is None:
            continue
        if installed < limit - 1e-9:
            breached[key] = limit
    return breached or None


def _fit(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Trim until the note fits the budget it is written against.

    Rarest patterns go first: a failure seen twelve times is what the next
    designer most needs told, and one seen once is the cheapest thing to lose.
    """
    patterns = list(memory.get("known_bad_patterns") or [])
    patterns.sort(key=lambda p: -int(p.get("observed_count") or 0))
    memory["known_bad_patterns"] = patterns[:MAX_BAD_PATTERNS]
    while len(_encode(memory)) > MAX_MEMORY_BYTES and memory["known_bad_patterns"]:
        memory["known_bad_patterns"] = memory["known_bad_patterns"][:-1]
    return memory


def _encode(memory: Mapping[str, Any]) -> bytes:
    return (json.dumps(memory, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")


def update_compact_chain_memory(
    chain_dir: Path,
    iteration_dir: Path,
    *,
    iteration: int,
    applied_capacity_keys: Optional[Sequence[str]] = None,
) -> Optional[Path]:
    """Fold one finished iteration into the chain's memory and write it.

    Called after the iteration's simulation, evaluation and proposals exist, so
    the round it records is the round that actually ran. Returns the path
    written, or ``None`` when the iteration left nothing to record.
    """
    chain_dir = Path(chain_dir)
    iteration_dir = Path(iteration_dir)

    summary = _read_json(iteration_dir / "summary.json")
    evaluation = _read_json(iteration_dir / "evaluation.json")
    config = _read_yaml(iteration_dir / "scenario_config.yaml")
    if not summary and not config:
        return None

    memory = load_chain_memory(chain_dir)
    if not isinstance(memory, Mapping) or memory.get("error"):
        memory = _blank_memory()
    else:
        memory = {**_blank_memory(), **dict(memory)}
    memory["schema_version"] = SCHEMA_VERSION
    memory["objective"] = dict(OBJECTIVE)
    memory["proposal_guidance"] = dict(PROPOSAL_GUIDANCE)

    previous_effective = memory.get("last_effective_design")
    previous_effective = previous_effective if isinstance(previous_effective, Mapping) else None

    # What was installed, not what was asked for. A proposal that was written
    # and a machine that was built are different things, and only the second
    # one produced the numbers beside it.
    fields = _round_fields(read_capacity_fields(config)) if config else {}

    floor = theoretical_floor_from_trace(iteration_dir / "tool_trace.jsonl")
    if floor:
        memory["theoretical_floor"] = _round_fields(floor)
    existing_floor = memory.get("theoretical_floor")
    existing_floor = existing_floor if isinstance(existing_floor, Mapping) else {}

    crew_initial = summary.get("crew_initial")
    crew_remaining = summary.get("crew_remaining")
    score = _number((evaluation.get("scores") or {}).get("total"))
    status = evaluation.get("status")
    gate_passed = bool((evaluation.get("physics_gate") or {}).get("passed"))
    constraint_status = _constraint_status(config, fields) if fields else None

    if fields:
        memory["last_effective_design"] = {
            "iteration": iteration,
            "crew_remaining": crew_remaining,
            "score": score,
            "fields": fields,
        }

    full_survival = (
        isinstance(crew_initial, int)
        and isinstance(crew_remaining, int)
        and crew_initial > 0
        and crew_remaining == crew_initial
    )
    if full_survival and gate_passed and status == "scored" and score is not None and fields:
        best = memory.get("best_full_survival")
        best = best if isinstance(best, Mapping) else None
        incumbent = _number((best or {}).get("score"))
        better = (
            incumbent is None
            or score > incumbent
            or (
                score == incumbent
                and _constraint_rank(constraint_status)
                < _constraint_rank((best or {}).get("constraint_status"))
            )
        )
        if better:
            memory["best_full_survival"] = {
                "iteration": iteration,
                "crew_remaining": crew_remaining,
                "crew_initial": crew_initial,
                "score": score,
                "fields": fields,
                "constraint_status": constraint_status,
                "physics_gate_passed": gate_passed,
            }

    patterns = [dict(p) for p in memory.get("known_bad_patterns") or [] if isinstance(p, Mapping)]
    if _detect_dropped_to_baseline(
        applied_capacity_keys=applied_capacity_keys,
        fields=fields,
        previous=previous_effective,
    ):
        _bump_pattern(patterns, PATTERN_DROPPED_TO_BASELINE)
    breached = _detect_below_floor(
        fields=fields,
        floor=existing_floor,
        crew_remaining=crew_remaining,
        crew_initial=crew_initial,
    )
    if breached:
        _bump_pattern(patterns, PATTERN_BELOW_FLOOR, thresholds=breached)
    memory["known_bad_patterns"] = patterns
    memory["updated_after_iteration"] = iteration

    path = chain_memory_path(chain_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encode(_fit(memory)))
    return path


__all__ = [
    "ARS_KEY",
    "CHAIN_MEMORY_FILENAME",
    "MAX_BAD_PATTERNS",
    "MAX_MEMORY_BYTES",
    "OBJECTIVE",
    "OGS_KEY",
    "PATTERN_BELOW_FLOOR",
    "PATTERN_DROPPED_TO_BASELINE",
    "PROPOSAL_GUIDANCE",
    "SCHEMA_VERSION",
    "WRS_KEY",
    "capacity_keys_in_document",
    "chain_memory_path",
    "find_chain_memory",
    "load_chain_memory",
    "theoretical_floor_from_trace",
    "update_compact_chain_memory",
]
