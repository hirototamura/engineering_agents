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
installed last round, where each subsystem was *measured* to stop keeping the
crew alive, and the handful of ways this chain has already lost people. It is
capped at 4 KB because its only reader is a language model with a finite
context window: it is a note, not a history, and it never grows with the
iteration count.

It states no limits of its own. It used to carry a calculated minimum per
subsystem and a rule against going below it, and that rule became the answer:
from the round the gas subsystems first touched their calculated minimum,
twenty further rounds moved neither. Worse, one of the three calculations was
wrong — the water figure ignored that the crew only starts the recycler once
five litres have collected — and three rounds lost four occupants each
rediscovering it. What is recorded now is what happened when a sizing was
actually run. A designer shown that twelve occupants died at 20.45 does not
need to be told 20.8 is a floor.

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

PATTERN_DESCRIPTIONS = {
    # Kept as a canary. Completing every hand-off to a whole machine should make
    # this impossible; if it ever fires again, that fix has regressed.
    PATTERN_DROPPED_TO_BASELINE: (
        "A partial proposal omitted ARS/OGS and the next run reset them to "
        "baseline, losing the crew."
    ),
}

OBJECTIVE = {
    "primary": "maximize_crew_remaining",
    "secondary": "maximize_evaluation_score",
    "notes": "Treat survival as lexicographically prior to score.",
}

PROPOSAL_GUIDANCE = {
    # No "do not reduce" clause. Shrinking is the whole point of the exercise
    # once everyone is coming back, and the measured limits below say where it
    # stops working without anyone having to forbid anything.
    "prefer_complete_capacity_profile": True,
    "include_all_design_variables": list(CAPACITY_KEYS),
}

# Ranking used only to break a tie on score: a design that can be paid for
# beats one that cannot, and a known over-budget design beats an unknown.
_CONSTRAINT_RANK = {"ok": 0, "over_budget": 1}
_CONSTRAINT_RANK_OTHER = 2

TIER_FULL = "full_survival"
TIER_PARTIAL = "partial_survival"
TIER_ZERO = "zero_survival"

STAGNATION_ACTIVE = "stagnated"
STAGNATION_IMPROVING = "improving"
STAGNATION_WARMING_UP = "collecting"
STAGNATION_COOLDOWN = "cooldown"
# The window straddles two survival tiers, so its scores were never answering
# the same question. Distinct from "compared, and the chain is moving".
STAGNATION_NOT_COMPARABLE = "not_comparable"

MODE_DIVERSIFY = "diversify"

# How many rounds of no real progress count as stuck, and what counts as real.
# Four rather than three: three fires during ordinary fine-tuning, four still
# catches a stall early enough to matter in a ten-round chain. The runs are
# deterministic, so a quarter of a point is comfortably outside the noise.
DEFAULT_STAGNATION_WINDOW = 4
DEFAULT_MIN_SCORE_DELTA = 0.25
DEFAULT_COOLDOWN_ITERATIONS = 2

# Enough recent sizings for "do not just try that again" to mean something,
# few enough that the note stays a note.
MAX_RECENT_FIELD_SETS = 3

EXPLORATION_STRATEGIES = [
    "try a smaller footprint while holding ARS and OGS at the theoretical floor",
    "move WRS between the smallest batch that avoided a water warning and the "
    "recent high values, rather than repeating either end",
    "compare one exact-floor sizing against one modest-margin sizing when the "
    "candidate budget allows both",
]

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


def record_measured_limits(chain_dir: Path, measured: Mapping[str, Any]) -> Optional[Path]:
    """Put what the probe observed into the note, compactly.

    Only the two ends of each bracket travel: the smallest sizing seen to bring
    everyone back, and the largest seen to lose someone, with the cause. The
    sweep that found them stays in ``measured_limits.json`` for a person to read.
    """
    compact: Dict[str, Any] = {}
    for key, found in (measured.get("limits") or {}).items():
        if not isinstance(found, Mapping):
            continue
        row: Dict[str, Any] = {"smallest_that_kept_everyone": found.get("lowest_survivable")}
        if found.get("highest_fatal") is not None:
            row["largest_that_lost_someone"] = found.get("highest_fatal")
            row["and_lost"] = found.get("highest_fatal_crew")
            causes = found.get("highest_fatal_causes")
            if causes:
                row["cause"] = causes
        else:
            row["note"] = "nothing below this was tried, or nothing below it failed"
        compact[key] = row
    if not compact:
        return None
    memory = load_chain_memory(chain_dir)
    if not isinstance(memory, Mapping) or memory.get("error"):
        memory = _blank_memory()
    else:
        memory = {**_blank_memory(), **dict(memory)}
    memory["measured_limits"] = {
        "how": (
            "each subsystem was lowered on its own, holding the others at the "
            "smallest sizing that had survived, until occupants were lost"
        ),
        "smallest_surviving_machine": measured.get("smallest_surviving_machine"),
        "by_subsystem": compact,
    }
    path = chain_memory_path(chain_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encode(_fit(memory)))
    return path


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
        # Set once, by measurement, not by this module.
        "measured_limits": None,
        "best_full_survival": None,
        "last_effective_design": None,
        "known_bad_patterns": [],
        "proposal_guidance": dict(PROPOSAL_GUIDANCE),
        "stagnation": None,
        "exploration_directive": None,
        # Bookkeeping for the detector, not advice: the last few rounds and the
        # best score each tier reached before them. Bounded, so the note still
        # does not grow with the chain.
        "recent_points": [],
        "best_score_before_window": {},
        "cooldown_until": None,
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


# The recent-rounds ledger is bookkeeping the designer never reads, and the
# dotted key names cost more bytes than the numbers do. Stored short, expanded
# again for anything that goes in front of the model.
_SHORT_KEYS = {ARS_KEY: "ars", OGS_KEY: "ogs", WRS_KEY: "wrs"}
_LONG_KEYS = {short: long for long, short in _SHORT_KEYS.items()}


def _short_fields(fields: Mapping[str, float]) -> Dict[str, float]:
    return {_SHORT_KEYS[key]: value for key, value in fields.items() if key in _SHORT_KEYS}


def _long_fields(fields: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, value in (fields or {}).items():
        number = _number(value)
        if number is None:
            continue
        out[_LONG_KEYS.get(str(key), str(key))] = number
    return out


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


# --------------------------------------------------------------------------- #
# stagnation
# --------------------------------------------------------------------------- #
def survival_tier(crew_remaining: Any, crew_initial: Any) -> Optional[str]:
    """Which of the three answers to "did they come back" this round gave.

    Scores are only comparable inside a tier. Survival is the primary
    objective, so a round that saved four more people and scored two points
    lower did not stagnate — it moved, in the direction that counts.
    """
    if not isinstance(crew_remaining, int) or not isinstance(crew_initial, int):
        return None
    if crew_initial <= 0:
        return None
    if crew_remaining >= crew_initial:
        return TIER_FULL
    if crew_remaining <= 0:
        return TIER_ZERO
    return TIER_PARTIAL


def exploration_settings(config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """``iteration.exploration`` from the run's own config, with defaults."""
    raw = ((config or {}).get("iteration") or {}).get("exploration")
    raw = raw if isinstance(raw, Mapping) else {}

    def positive_int(key: str, default: int) -> int:
        try:
            value = int(raw[key])
        except (KeyError, TypeError, ValueError):
            return default
        return value if value > 0 else default

    def positive_float(key: str, default: float) -> float:
        try:
            value = float(raw[key])
        except (KeyError, TypeError, ValueError):
            return default
        return value if value > 0 else default

    return {
        "stagnation_window": positive_int("stagnation_window", DEFAULT_STAGNATION_WINDOW),
        "min_score_delta": positive_float("min_score_delta", DEFAULT_MIN_SCORE_DELTA),
        "require_same_survival_tier": bool(raw.get("require_same_survival_tier", True)),
        # Zero is meaningful here: fire again the moment the next window stalls.
        "cooldown_iterations": max(
            0,
            int(raw["cooldown_iterations"])
            if str(raw.get("cooldown_iterations", "")).lstrip("-").isdigit()
            else DEFAULT_COOLDOWN_ITERATIONS,
        ),
    }


def _detect_stagnation(
    recent: Sequence[Mapping[str, Any]],
    best_before: Mapping[str, Any],
    *,
    settings: Mapping[str, Any],
    iteration: int,
    cooldown_until: Optional[int],
) -> Dict[str, Any]:
    """Has the chain stopped getting anywhere, and is it allowed to say so?

    Only the window's own tier is judged, and only against the best score
    reached in that tier before the window opened. Comparing a full-survival
    round against a zero-survival one would call any recovery "improvement" and
    any careful refinement "stagnation".
    """
    window = int(settings["stagnation_window"])
    delta = float(settings["min_score_delta"])
    same_tier_required = bool(settings["require_same_survival_tier"])
    base: Dict[str, Any] = {
        "window": window,
        "min_score_delta": delta,
        "iterations": [int(point["iteration"]) for point in recent],
    }

    if len(recent) < window:
        return {**base, "status": STAGNATION_WARMING_UP}

    tiers = {point.get("survival_tier") for point in recent}
    if same_tier_required and len(tiers) != 1:
        # The chain moved between tiers inside the window. Whatever that is, it
        # is not the same neighbourhood being tried over and over -- and a round
        # that lost people is information, not a stall.
        return {**base, "status": STAGNATION_NOT_COMPARABLE, "survival_tier": None}
    tier = recent[-1].get("survival_tier")

    scores = [_number(point.get("score")) for point in recent]
    scores = [value for value in scores if value is not None]
    if not scores:
        return {**base, "status": STAGNATION_WARMING_UP, "survival_tier": tier}
    in_window = max(scores)
    before = _number(best_before.get(str(tier)))
    result = {
        **base,
        "survival_tier": tier,
        "best_score_in_window": round(in_window, 6),
        "best_score_before_window": None if before is None else round(before, 6),
    }
    if before is None:
        # The window is the whole history of this tier, so there is nothing it
        # could have failed to improve on yet.
        return {**result, "status": STAGNATION_WARMING_UP}
    result["score_delta"] = round(in_window - before, 6)
    if in_window - before >= delta:
        return {**result, "status": STAGNATION_IMPROVING}
    if cooldown_until is not None and iteration <= int(cooldown_until):
        # Already told to explore; saying it again every round would make the
        # directive permanent rather than a response to being stuck.
        return {**result, "status": STAGNATION_COOLDOWN, "cooldown_until": int(cooldown_until)}
    return {**result, "status": STAGNATION_ACTIVE}


def _exploration_directive(
    stagnation: Mapping[str, Any],
    recent: Sequence[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """What to do about being stuck, in terms a proposal can be written from.

    Issued when the chain stalls and kept for the cooldown rounds that follow.
    The cooldown stops the *detector* re-firing every round; it is not a reason
    to stop exploring one round after being told to start.
    """
    if stagnation.get("status") not in {STAGNATION_ACTIVE, STAGNATION_COOLDOWN}:
        return None
    seen: List[Dict[str, float]] = []
    for point in reversed(recent):
        fields = _long_fields(point.get("fields") or {})
        if fields and fields not in seen:
            seen.append(fields)
        if len(seen) >= MAX_RECENT_FIELD_SETS:
            break
    return {
        "mode": MODE_DIVERSIFY,
        "reason": (
            "the score has not improved by at least %g points over %d comparable "
            "iterations" % (stagnation.get("min_score_delta"), stagnation.get("window"))
        ),
        "avoid_repeating_recent_fields": True,
        "preferred_strategies": list(EXPLORATION_STRATEGIES),
        "recent_field_sets": seen,
    }


def _fit(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Trim until the note fits the budget it is written against.

    Rarest patterns go first: a failure seen twelve times is what the next
    designer most needs told, and one seen once is the cheapest thing to lose.
    """
    patterns = list(memory.get("known_bad_patterns") or [])
    patterns.sort(key=lambda p: -int(p.get("observed_count") or 0))
    memory["known_bad_patterns"] = patterns[:MAX_BAD_PATTERNS]
    directive = memory.get("exploration_directive")
    if isinstance(directive, Mapping) and directive.get("recent_field_sets"):
        directive = dict(directive)
        directive["recent_field_sets"] = list(directive["recent_field_sets"])[
            :MAX_RECENT_FIELD_SETS
        ]
        memory["exploration_directive"] = directive
    # Advice first, then the bookkeeping behind it, then the rarest failures.
    # A pattern seen twelve times is the thing the next designer most needs
    # told; a strategy sentence it can infer is the cheapest thing to lose.
    while len(_encode(memory)) > MAX_MEMORY_BYTES:
        if _drop_one(memory):
            continue
        break
    return memory


def _drop_one(memory: Dict[str, Any]) -> bool:
    """Remove the least valuable single item. ``False`` when nothing is left."""
    directive = memory.get("exploration_directive")
    if isinstance(directive, Mapping):
        strategies = list(directive.get("preferred_strategies") or [])
        if len(strategies) > 1:
            directive = dict(directive)
            directive["preferred_strategies"] = strategies[:-1]
            memory["exploration_directive"] = directive
            return True
    points = list(memory.get("recent_points") or [])
    if points:
        memory["recent_points"] = points[1:]
        return True
    patterns = list(memory.get("known_bad_patterns") or [])
    if patterns:
        memory["known_bad_patterns"] = patterns[:-1]
        return True
    return False


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
    memory["known_bad_patterns"] = patterns

    settings = exploration_settings(config)
    tier = survival_tier(crew_remaining, crew_initial)
    recent = [
        dict(point)
        for point in memory.get("recent_points") or []
        if isinstance(point, Mapping)
    ]
    best_before = dict(memory.get("best_score_before_window") or {})
    if fields and tier is not None:
        recent.append(
            {
                "iteration": iteration,
                "score": score,
                "survival_tier": tier,
                "fields": _short_fields(fields),
            }
        )
    # A round leaving the window is not forgotten -- it becomes the bar the
    # window has to clear. Otherwise "no improvement over four rounds" would
    # quietly mean "no improvement over the four rounds we still remember".
    while len(recent) > int(settings["stagnation_window"]):
        evicted = recent.pop(0)
        evicted_score = _number(evicted.get("score"))
        evicted_tier = str(evicted.get("survival_tier"))
        if evicted_score is None:
            continue
        previous = _number(best_before.get(evicted_tier))
        best_before[evicted_tier] = (
            evicted_score if previous is None else max(previous, evicted_score)
        )
    memory["recent_points"] = recent
    memory["best_score_before_window"] = best_before

    stagnation = _detect_stagnation(
        recent,
        best_before,
        settings=settings,
        iteration=iteration,
        cooldown_until=_number(memory.get("cooldown_until")),
    )
    memory["stagnation"] = stagnation
    memory["exploration_directive"] = _exploration_directive(stagnation, recent)
    if stagnation.get("status") == STAGNATION_ACTIVE:
        memory["cooldown_until"] = iteration + int(settings["cooldown_iterations"])

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
    "PATTERN_DROPPED_TO_BASELINE",
    "PROPOSAL_GUIDANCE",
    "SCHEMA_VERSION",
    "WRS_KEY",
    "DEFAULT_COOLDOWN_ITERATIONS",
    "DEFAULT_MIN_SCORE_DELTA",
    "DEFAULT_STAGNATION_WINDOW",
    "MODE_DIVERSIFY",
    "STAGNATION_ACTIVE",
    "STAGNATION_COOLDOWN",
    "STAGNATION_IMPROVING",
    "STAGNATION_NOT_COMPARABLE",
    "STAGNATION_WARMING_UP",
    "TIER_FULL",
    "TIER_PARTIAL",
    "TIER_ZERO",
    "capacity_keys_in_document",
    "chain_memory_path",
    "exploration_settings",
    "find_chain_memory",
    "load_chain_memory",
    "record_measured_limits",
    "survival_tier",
    "update_compact_chain_memory",
]
