"""Find out where each subsystem actually stops keeping the crew alive.

The chain used to be handed a *calculated* minimum for each subsystem — crew
demand divided by how often the machine can run — and told not to go below it.
Two things were wrong with that.

The calculation was not always right. It assumes the machine runs at full batch
every time it is available, which the crew's own operating rules do not do: the
water recycler is only started once five litres have collected, so a batch
smaller than that leaves feed behind every cycle. The calculated minimum for it
was 1.5625 L. The real one is 2.0. Three separate rounds proposed the
calculated value, and each lost four occupants finding that out again.

And handing a designer a line it may not cross makes that line the answer. From
the round the gas subsystems first touched their calculated minimum, twenty
further rounds moved neither of them — not because anything had been measured,
but because a number had been asserted.

So the number is measured instead. This walks each subsystem down from a sizing
that is known to work until the crew starts dying, and reports the two ends it
actually observed. Nothing here forbids anything: a designer shown that twelve
occupants died at 19.76 does not need to be told 20.8 is a floor, and a
designer shown nothing below 2.0 was ever survivable can still try 1.9 if the
evidence changes. The difference is that both statements are now facts about
runs that happened.

It is deterministic, it costs a handful of simulations once per chain, and it
never asks a model anything.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from scenario.ssos_eclss_loop.design_variables import (
    CAPACITY_KEYS,
    CAPACITY_VARIABLES,
    apply_capacity_fields,
    sync_action_payloads,
)

MEASURED_LIMITS_FILENAME = "measured_limits.json"
SCHEMA_VERSION = "1.0"

# The search cuts a quarter off at a time until the crew is lost, then halves
# the remaining gap. Geometric rather than a fixed set of fractions, because how
# far the starting sizing sits above the edge is not known in advance -- that is
# the thing being measured. Four bisections land inside about 2% of the true
# edge, finer than any sizing a designer proposes.
DESCENT_RATIO = 0.75
MAX_DESCENT_STEPS = 16
DEFAULT_REFINE_STEPS = 4

# If the starting sizing does not keep everyone alive there is nothing to walk
# down from, so it is grown until it does. Eight steps covers a machine sized at
# a fifth of what the crew turns out to need, which is where the shipped
# scenario starts.
GROWTH_RATIO = 1.25
MAX_GROWTH_STEPS = 8

STATUS_BRACKETED = "bracketed"
STATUS_NO_CLIFF_FOUND = "no_cliff_found"
STATUS_NO_SAFE_ANCHOR = "no_safe_anchor"
STATUS_SKIPPED = "skipped"


def _crew(summary: Mapping[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    remaining, initial = summary.get("crew_remaining"), summary.get("crew_initial")
    return (
        remaining if isinstance(remaining, int) else None,
        initial if isinstance(initial, int) else None,
    )


def _full_survival(summary: Mapping[str, Any]) -> bool:
    remaining, initial = _crew(summary)
    return remaining is not None and initial is not None and initial > 0 and remaining == initial


def _crew_text(summary: Mapping[str, Any]) -> str:
    remaining, initial = _crew(summary)
    if remaining is None or initial is None:
        return "unknown"
    return f"{remaining}/{initial}"


def _round(value: float) -> float:
    return round(float(value), 4)


class _Sims:
    """Runs one sizing and remembers it, so a repeat costs nothing."""

    def __init__(self, runner: Callable[[Dict[str, float], str], Mapping[str, Any]]):
        self._runner = runner
        self._seen: Dict[str, Dict[str, Any]] = {}
        self.count = 0

    def __call__(self, fields: Mapping[str, float], label: str) -> Dict[str, Any]:
        rounded = {key: _round(value) for key, value in fields.items()}
        key = json.dumps(rounded, sort_keys=True)
        cached = self._seen.get(key)
        if cached is not None:
            return cached
        summary = dict(self._runner(rounded, label) or {})
        record = {
            "fields": rounded,
            "crew": _crew_text(summary),
            "full_survival": _full_survival(summary),
            "crew_lost_by_cause": {
                cause: n for cause, n in (summary.get("crew_lost_by_cause") or {}).items() if n
            },
        }
        self._seen[key] = record
        self.count += 1
        return record


def _anchor(sims: _Sims, start: Mapping[str, float]) -> Optional[Dict[str, Any]]:
    """A sizing that brings everyone back, to walk down from.

    Grown rather than assumed: the calculated minimum is exactly the thing under
    test, so it cannot also be the thing relied on.
    """
    fields = dict(start)
    for step in range(MAX_GROWTH_STEPS + 1):
        result = sims(fields, f"anchor_{step}")
        if result["full_survival"]:
            return result
        fields = {key: value * GROWTH_RATIO for key, value in fields.items()}
    return None


def _walk_down(
    sims: _Sims,
    anchor: Mapping[str, float],
    key: str,
    *,
    refine_steps: int,
    lower_bound: Optional[float] = None,
) -> Dict[str, Any]:
    """Lower one subsystem, holding the rest, until the crew starts dying.

    Steps down until someone is lost, then halves the remaining gap. Below
    *lower_bound* nothing can be built, so a subsystem that survives all the way
    there has no cliff to find and the report says so instead of naming the
    smallest thing tried as if it were the edge.
    """
    safe = float(anchor[key])
    fatal: Optional[float] = None
    fatal_result: Optional[Dict[str, Any]] = None

    for _ in range(MAX_DESCENT_STEPS):
        probe = safe * DESCENT_RATIO
        at_bound = lower_bound is not None and probe <= lower_bound
        if at_bound:
            probe = float(lower_bound)
        if probe >= safe:
            break
        result = sims({**anchor, key: probe}, f"{key}_{probe:.4g}")
        if not result["full_survival"]:
            fatal, fatal_result = probe, result
            break
        safe = probe
        if at_bound:
            # The smallest machine that can be built still brings everyone back,
            # so this subsystem has no survival edge to find.
            break

    if fatal is None or fatal_result is None:
        return {
            "status": STATUS_NO_CLIFF_FOUND,
            "lowest_survivable": _round(safe),
            "lowest_survivable_crew": "all",
            "note": "everyone came back at every sizing tried, down to %g" % _round(safe),
        }

    for _ in range(max(0, int(refine_steps))):
        middle = (safe + fatal) / 2.0
        if math.isclose(middle, safe, rel_tol=1e-3) or math.isclose(middle, fatal, rel_tol=1e-3):
            break
        result = sims({**anchor, key: middle}, f"{key}_{middle:.4g}")
        if result["full_survival"]:
            safe = middle
        else:
            fatal, fatal_result = middle, result
    return {
        "status": STATUS_BRACKETED,
        "lowest_survivable": _round(safe),
        "lowest_survivable_crew": "all",
        "highest_fatal": _round(fatal),
        "highest_fatal_crew": fatal_result["crew"],
        "highest_fatal_causes": fatal_result["crew_lost_by_cause"],
    }


def measure_survival_limits(
    *,
    start: Mapping[str, float],
    runner: Callable[[Dict[str, float], str], Mapping[str, Any]],
    keys: Optional[List[str]] = None,
    bounds: Optional[Mapping[str, float]] = None,
    refine_steps: int = DEFAULT_REFINE_STEPS,
) -> Dict[str, Any]:
    """Walk each design variable down and report where the crew was lost.

    *runner* simulates one sizing and returns its summary; everything else here
    is arithmetic. Returns a record naming, per subsystem, the smallest sizing
    observed to bring everyone back and the largest observed to lose someone.
    """
    keys = list(keys or CAPACITY_KEYS)
    sims = _Sims(runner)
    anchor = _anchor(sims, start)
    if anchor is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": STATUS_NO_SAFE_ANCHOR,
            "note": (
                "no sizing tried kept every occupant alive, so there was no working "
                "machine to measure downwards from"
            ),
            "simulations": sims.count,
            "limits": {},
        }

    # The anchor is grown until it works, so it starts oversized. Each subsystem
    # is measured and then held at the smallest value that survived, so the next
    # one is measured against a machine that is already tight rather than
    # against slack elsewhere that is quietly covering for it.
    held = dict(anchor["fields"])
    limits: Dict[str, Any] = {}
    for key in keys:
        if key not in held:
            limits[key] = {"status": STATUS_SKIPPED}
            continue
        found = _walk_down(
            sims,
            held,
            key,
            refine_steps=refine_steps,
            lower_bound=(bounds or {}).get(key),
        )
        limits[key] = {
            "subsystem": CAPACITY_VARIABLES[key].subsystem if key in CAPACITY_VARIABLES else None,
            "unit": CAPACITY_VARIABLES[key].unit if key in CAPACITY_VARIABLES else None,
            **found,
        }
        held[key] = float(found["lowest_survivable"])
    return {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_BRACKETED,
        "note": (
            "measured, not calculated: each subsystem was lowered on its own until "
            "occupants were lost, holding the others at the smallest sizing that "
            "had survived"
        ),
        "started_from": anchor["fields"],
        "smallest_surviving_machine": held,
        "simulations": sims.count,
        "limits": limits,
    }


def scenario_runner(
    *,
    scenario_config: Mapping[str, Any],
    output_root: Path,
    actor_mode: Optional[str] = None,
    policy_hint: Optional[Mapping[str, Any]] = None,
    steps: Optional[int] = None,
) -> Callable[[Dict[str, float], str], Mapping[str, Any]]:
    """A *runner* that re-simulates the scenario at one sizing.

    Built the same way a design candidate is, so a limit measured here means the
    same thing as a candidate that was verified: same backend, same crew, same
    operating rules, post-run design switched off.
    """

    def run(fields: Dict[str, float], label: str) -> Mapping[str, Any]:
        from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

        config = copy.deepcopy(dict(scenario_config))
        apply_capacity_fields(config, fields)
        sync_action_payloads(config, policy_hint=policy_hint)
        agents = config.setdefault("agents", {})
        agents.setdefault("design", {})["mode"] = "none"
        if actor_mode:
            agents.setdefault("actor", {})["mode"] = actor_mode
        if steps is not None:
            config.setdefault("simulation", {})["steps"] = int(steps)
        out_dir = Path(output_root) / label
        SsosEclssLoopScenario().run(
            output_dir=out_dir, overrides=config, recreate_output=True
        )
        try:
            return json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    return run


def write_measured_limits(directory: Path, record: Mapping[str, Any]) -> Path:
    path = Path(directory) / MEASURED_LIMITS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return path


__all__ = [
    "MEASURED_LIMITS_FILENAME",
    "STATUS_BRACKETED",
    "STATUS_NO_CLIFF_FOUND",
    "STATUS_NO_SAFE_ANCHOR",
    "measure_survival_limits",
    "scenario_runner",
    "write_measured_limits",
]
