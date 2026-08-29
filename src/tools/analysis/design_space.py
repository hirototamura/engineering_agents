"""The ECLSS design space and its dimensionless order parameters.

The scorecard measures *outcomes* (crew, dwell, recovery). To reason about the
design->verify loop as a dynamical system we also need coordinates for the thing
the loop actually moves. This module supplies them.

Two coordinate systems are used throughout the analysis:

**Physical capacity** -- the three nameplate variables the designer may size
(``scenario.ssos_eclss_loop.design_variables``). They have different units
(kg/day, kg/day, L/operation) and baselines that differ by an order of
magnitude, so they are never compared directly.

**Coverage ratio** ``rho`` -- installed throughput divided by the crew's
metabolic demand for the same quantity, per day. ``rho`` is dimensionless, is
comparable across subsystems, and has a physically meaningful unit point:
``rho = 1`` is the smallest station that can service the crew in steady state.
``rho_min = min(rho_ars, rho_ogs, rho_wrs)`` is Liebig's law of the minimum
applied to life support, and is the single scalar order parameter of the
system.

Distances in design space are measured in ``log rho``. Sizing is multiplicative
(the sizing model is affine in the capacity *ratio*, and the rule designer
applies a constant multiplicative gain), so a log metric makes a doubling cost
the same regardless of where it starts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_variables import (
    BASELINE_CAPACITY,
    CAPACITY_VARIABLES,
    read_capacity_fields,
)

SECONDS_PER_DAY = 86_400.0

#: Analysis axes, in a fixed order so vectors are always comparable.
CAPACITY_AXES: Tuple[str, ...] = (
    "plant_sim.ars.capacity_kg_day",
    "plant_sim.ogs.max_o2_kg_day",
    "plant_sim.wrs.max_feed_l_per_operation",
)

SUBSYSTEM_BY_AXIS: Dict[str, str] = {
    axis: CAPACITY_VARIABLES[axis].subsystem for axis in CAPACITY_AXES
}

#: Crew metabolic rates, per person per day, as named in ``plant_sim.crew``.
_CREW_DEFAULTS: Dict[str, float] = {
    "co2_kg_day_person": 1.04,
    "o2_kg_day_person": 0.84,
    "potable_water_kg_day_person": 2.28,
    "urine_kg_day_person": 1.5,
    "condensate_kg_day_person": 0.75,
}

_TIME_DEFAULTS: Dict[str, float] = {
    "step_seconds": 1200.0,
    "wrs_operation_seconds": 1200.0,
}


def _num(mapping: Optional[Mapping[str, Any]], key: str, default: float) -> float:
    if not isinstance(mapping, Mapping):
        return default
    try:
        value = float(mapping.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _plant(config: Mapping[str, Any]) -> Mapping[str, Any]:
    block = config.get("plant_sim") if isinstance(config, Mapping) else None
    return block if isinstance(block, Mapping) else {}


@dataclass(frozen=True)
class CrewDemand:
    """Unconstrained metabolic load of the whole crew, per day.

    These are *demands*, not consumptions: they ignore what the tanks can
    actually supply, which is exactly what a capacity ratio needs in its
    denominator.
    """

    crew_size: int
    activity_factor: float
    co2_kg_day: float
    o2_kg_day: float
    potable_water_l_day: float
    waste_water_l_day: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "crew_size": float(self.crew_size),
            "activity_factor": self.activity_factor,
            "co2_kg_day": self.co2_kg_day,
            "o2_kg_day": self.o2_kg_day,
            "potable_water_l_day": self.potable_water_l_day,
            "waste_water_l_day": self.waste_water_l_day,
        }


def crew_demand(config: Mapping[str, Any]) -> CrewDemand:
    """Whole-crew metabolic demand implied by a scenario config."""

    crew = _plant(config).get("crew")
    crew = crew if isinstance(crew, Mapping) else {}
    size = int(_num(crew, "size", 50.0))
    activity = _num(crew, "activity_factor", 1.0)
    scale = float(size) * activity
    urine = _num(crew, "urine_kg_day_person", _CREW_DEFAULTS["urine_kg_day_person"])
    condensate = _num(
        crew, "condensate_kg_day_person", _CREW_DEFAULTS["condensate_kg_day_person"]
    )
    return CrewDemand(
        crew_size=size,
        activity_factor=activity,
        co2_kg_day=scale * _num(crew, "co2_kg_day_person", _CREW_DEFAULTS["co2_kg_day_person"]),
        o2_kg_day=scale * _num(crew, "o2_kg_day_person", _CREW_DEFAULTS["o2_kg_day_person"]),
        potable_water_l_day=scale
        * _num(
            crew,
            "potable_water_kg_day_person",
            _CREW_DEFAULTS["potable_water_kg_day_person"],
        ),
        waste_water_l_day=scale * (urine + condensate),
    )


def wrs_throughput_l_day(config: Mapping[str, Any], max_feed_l_per_operation: float) -> float:
    """WRS batch size converted to a daily rate.

    ``max_feed_l_per_operation`` is per *action*, and the busy guard allows at
    most one water_recovery per ``wrs_operation_seconds``. A step shorter than
    the operation cannot fire more often than the operation itself, so the
    limiting cadence is the longer of the two.
    """

    time_block = _plant(config).get("time")
    time_block = time_block if isinstance(time_block, Mapping) else {}
    step_s = _num(time_block, "step_seconds", _TIME_DEFAULTS["step_seconds"])
    op_s = _num(time_block, "wrs_operation_seconds", _TIME_DEFAULTS["wrs_operation_seconds"])
    cadence_s = max(step_s, op_s, 1.0)
    return max_feed_l_per_operation * (SECONDS_PER_DAY / cadence_s)


@dataclass(frozen=True)
class CoverageRatios:
    """Installed throughput / crew demand, per subsystem (dimensionless)."""

    ars: float
    ogs: float
    wrs: float

    @property
    def minimum(self) -> float:
        """Liebig's law of the minimum: the binding coverage."""

        return min(self.ars, self.ogs, self.wrs)

    @property
    def binding_subsystem(self) -> str:
        return min(
            (("ars", self.ars), ("ogs", self.ogs), ("wrs", self.wrs)),
            key=lambda item: item[1],
        )[0]

    def as_dict(self) -> Dict[str, float]:
        return {
            "rho_ars": self.ars,
            "rho_ogs": self.ogs,
            "rho_wrs": self.wrs,
            "rho_min": self.minimum,
            "binding_subsystem": self.binding_subsystem,  # type: ignore[dict-item]
        }


def coverage_ratios(
    config: Mapping[str, Any],
    capacity: Optional[Mapping[str, float]] = None,
) -> CoverageRatios:
    """Dimensionless coverage of each subsystem for the configured crew.

    ``capacity`` overrides the values read from ``config``, which lets a caller
    price a hypothetical design against the same crew.
    """

    demand = crew_demand(config)
    fields = dict(read_capacity_fields(config))
    if capacity:
        fields.update({key: float(value) for key, value in capacity.items()})

    def ratio(numerator: float, denominator: float) -> float:
        if denominator <= 0.0:
            return math.inf
        return numerator / denominator

    return CoverageRatios(
        ars=ratio(fields["plant_sim.ars.capacity_kg_day"], demand.co2_kg_day),
        ogs=ratio(fields["plant_sim.ogs.max_o2_kg_day"], demand.o2_kg_day),
        wrs=ratio(
            wrs_throughput_l_day(config, fields["plant_sim.wrs.max_feed_l_per_operation"]),
            demand.waste_water_l_day,
        ),
    )


@dataclass(frozen=True)
class DesignPoint:
    """One point of the design space, with everything needed to place it.

    ``vector`` is the log-capacity coordinate used for every distance and angle
    in the loop-dynamics analysis; ``coverage`` is the physical reading of the
    same point.
    """

    capacity: Dict[str, float]
    coverage: CoverageRatios
    vector: Tuple[float, ...]
    footprint: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"capacity": dict(self.capacity)}
        out.update(self.coverage.as_dict())
        out.update({f"footprint_{k}": v for k, v in self.footprint.items()})
        return out


def design_vector(capacity: Mapping[str, float]) -> Tuple[float, ...]:
    """Log-capacity coordinate, normalised so the shipped baseline is the origin.

    Component ``i`` is ``ln(capacity_i / baseline_i)``, so the zero vector is
    the shipped station and a unit step is a factor of ``e`` on one axis.
    """

    out = []
    for axis in CAPACITY_AXES:
        value = float(capacity.get(axis, BASELINE_CAPACITY[axis]))
        base = float(BASELINE_CAPACITY[axis])
        out.append(math.log(max(value, 1e-12) / base))
    return tuple(out)


def design_footprint(
    config: Mapping[str, Any],
    capacity: Optional[Mapping[str, float]] = None,
) -> Dict[str, float]:
    """Mass / volume / cost of a capacity set under the scenario sizing model."""

    constraints = DesignConstraints.from_scenario_config(config)
    fields = dict(read_capacity_fields(config))
    if capacity:
        fields.update({key: float(value) for key, value in capacity.items()})
    raw = constraints.footprint(fields)
    return {
        "total_mass_kg": float(raw["total_mass_kg"]),
        "total_volume_m3": float(raw["total_volume_m3"]),
        "total_cost_musd": float(raw["total_cost_musd"]),
        "hardware_cost_musd": float(raw["hardware_cost_musd"]),
        "launch_cost_musd": float(raw["launch_cost_musd"]),
    }


def design_point(
    config: Mapping[str, Any],
    capacity: Optional[Mapping[str, float]] = None,
) -> DesignPoint:
    """Assemble the full description of one design against one scenario."""

    fields = dict(read_capacity_fields(config))
    if capacity:
        fields.update({key: float(value) for key, value in capacity.items()})
    return DesignPoint(
        capacity=fields,
        coverage=coverage_ratios(config, fields),
        vector=design_vector(fields),
        footprint=design_footprint(config, fields),
    )


def budget_limits(config: Mapping[str, Any]) -> Dict[str, float]:
    """Mass / cost / volume ceilings declared by ``design_constraints.budgets``."""

    constraints = DesignConstraints.from_scenario_config(config)
    return {key: float(value) for key, value in constraints.budgets.items()}


def capacity_bounds(config: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    """Per-subsystem ``{min, max}`` sizing bounds declared by the scenario."""

    constraints = DesignConstraints.from_scenario_config(config)
    return {
        sub: {"min": float(edge["min"]), "max": float(edge["max"])}
        for sub, edge in constraints.bounds.items()
    }


def euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


# --------------------------------------------------------------------------- #
# the full actuation space
# --------------------------------------------------------------------------- #
#: Every scalar a designer is allowed to move, with the subspace it belongs to,
#: where it is stored, and its shipped value.
#:
#: ``capacity`` is installed hardware (scenario config). ``action`` is the
#: payload the crew sends to hardware it already has (agents config). ``policy``
#: is the band edge that decides when the crew acts at all (scenario config,
#: mirrored into the agents config).
#:
#: Keeping all three in one vector is what makes "the loop did not move" and
#: "the loop moved somewhere useless" distinguishable: a designer confined to
#: ``action`` has a large step norm and a zero capacity component.
ACTUATION_AXES: Dict[str, Dict[str, Any]] = {
    "ars_capacity_kg_day": {
        "subspace": "capacity",
        "source": "scenario",
        "path": ("plant_sim", "ars", "capacity_kg_day"),
        "baseline": 4.5,
    },
    "ogs_max_o2_kg_day": {
        "subspace": "capacity",
        "source": "scenario",
        "path": ("plant_sim", "ogs", "max_o2_kg_day"),
        "baseline": 9.25,
    },
    "wrs_max_feed_l": {
        "subspace": "capacity",
        "source": "scenario",
        "path": ("plant_sim", "wrs", "max_feed_l_per_operation"),
        "baseline": 10.0,
    },
    "ars_action_co2_mass": {
        "subspace": "action",
        "source": "agents",
        "path": ("actor", "policy", "ars_goal", "initial_co2_mass"),
        "baseline": 4.5,
    },
    "ogs_action_water_mass": {
        "subspace": "action",
        "source": "agents",
        "path": ("actor", "policy", "ogs_goal", "input_water_mass"),
        "baseline": 0.15,
    },
    "wrs_action_urine_volume": {
        "subspace": "action",
        "source": "agents",
        "path": ("actor", "policy", "wrs_goal", "urine_volume"),
        "baseline": 0.5,
    },
    "request_co2_amount": {
        "subspace": "action",
        "source": "agents",
        "path": ("actor", "policy", "request_co2_amount"),
        "baseline": 0.025,
    },
    "co2_threshold_high": {
        "subspace": "policy",
        "source": "scenario",
        "path": ("thresholds", "co2_storage_high_kg"),
        "baseline": 2.0,
    },
    "o2_threshold_low": {
        "subspace": "policy",
        "source": "scenario",
        "path": ("thresholds", "o2_storage_low_kg"),
        "baseline": 6.0,
    },
    "water_threshold_low": {
        "subspace": "policy",
        "source": "scenario",
        "path": ("thresholds", "product_water_low_l"),
        "baseline": 50.0,
    },
}

ACTUATION_AXIS_NAMES: Tuple[str, ...] = tuple(ACTUATION_AXES)

SUBSPACES: Tuple[str, ...] = ("capacity", "action", "policy")


def _dig(mapping: Mapping[str, Any], path: Sequence[str]) -> Any:
    cursor: Any = mapping
    for part in path:
        if not isinstance(cursor, Mapping) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def actuation_vector(
    scenario_config: Mapping[str, Any],
    agents_config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, float]:
    """Log-ratio coordinate of every actuation axis, baseline at the origin.

    Absent axes read as their shipped baseline (coordinate 0), so a config that
    never mentions an axis is placed at the origin on it rather than dropped.
    """

    agents = agents_config or {}
    out: Dict[str, float] = {}
    for name, spec in ACTUATION_AXES.items():
        source = scenario_config if spec["source"] == "scenario" else agents
        raw = _dig(source, spec["path"])
        value = _num({"v": raw}, "v", float(spec["baseline"]))
        if value <= 0.0:
            value = float(spec["baseline"])
        out[name] = math.log(value / float(spec["baseline"]))
    return out


def subspace_of(axis: str) -> str:
    spec = ACTUATION_AXES.get(axis)
    return str(spec["subspace"]) if spec else "other"


def subspace_norms(delta: Mapping[str, float]) -> Dict[str, float]:
    """Euclidean norm of a step, restricted to each actuation subspace."""

    sums: Dict[str, float] = {name: 0.0 for name in SUBSPACES}
    for axis, value in delta.items():
        subspace = subspace_of(axis)
        if subspace in sums:
            sums[subspace] += float(value) ** 2
    return {name: math.sqrt(total) for name, total in sums.items()}


__all__ = [
    "ACTUATION_AXES",
    "ACTUATION_AXIS_NAMES",
    "CAPACITY_AXES",
    "CoverageRatios",
    "CrewDemand",
    "DesignPoint",
    "SUBSPACES",
    "SUBSYSTEM_BY_AXIS",
    "actuation_vector",
    "budget_limits",
    "capacity_bounds",
    "coverage_ratios",
    "crew_demand",
    "design_footprint",
    "design_point",
    "design_vector",
    "euclidean",
    "subspace_norms",
    "subspace_of",
    "wrs_throughput_l_day",
]
