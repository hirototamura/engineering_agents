"""Sizing / budget model for ECLSS capacity candidates (design doc §8).

The coefficients are an **exploration model**, not flight hardware estimates:
``rack_affine_linear_v1`` says each subsystem costs a fixed rack (structure,
controller, plumbing, redundancy) plus a variable part that scales linearly with
capacity relative to the baseline machine::

    ratio  = candidate_capacity / baseline_capacity
    mass   = fixed + variable_at_baseline * ratio
    volume = fixed + variable_at_baseline * ratio
    cost   = fixed + variable_at_baseline * ratio          # hardware only
    launch = total_mass_kg * launch_cost_musd_per_kg
    total  = hardware + launch

Constraint evaluation deliberately does **not** stop a candidate from being
simulated (design doc §8.1). Only ``preflight`` (schema / numeric / variable
scope) blocks a run; budgets and engineering bounds are labels that steer the
final choice, because "over-budget but everyone survives" is still a useful
lesson for the designer.

Bounds and budgets are not the same kind of limit. An out-of-bounds machine
cannot be built, so it cannot be adopted (``require_in_bounds_final``). A
budget is money: an over-budget design that keeps the whole crew alive is still
the answer, reported as ``provisional_final`` for a human to accept or refuse
(``require_feasible_final``, off by default).

``design_constraints.enabled: false`` turns the labelling off entirely: the
footprint is still reported, but no candidate is called over-budget or out of
bounds, so neither gate filters. ``preflight`` is not affected — a candidate
that names a variable outside the design scope is still invalid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from scenario.ssos_eclss_loop.design_variables import (
    BASELINE_CAPACITY,
    CAPACITY_KEYS,
    CAPACITY_VARIABLES,
    read_capacity_fields,
    validate_capacity_fields,
)

SIZING_MODE = "rack_affine_linear_v1"

# The objective is implemented in :mod:`design_eval` (full survival clears, then
# less CRITICAL dwell, then the smallest footprint). ``design_constraints.objective``
# in scenario.yaml documents it; any other value is a config/behaviour mismatch
# and is rejected at load time rather than silently ignored.
SUPPORTED_OBJECTIVES: Dict[str, Tuple[str, ...]] = {
    "primary": ("require_full_survival",),
    "secondary": ("minimize_resource_footprint",),
}

STATUS_FEASIBLE = "feasible"
STATUS_OVER_BUDGET = "over_budget"
STATUS_OUT_OF_BOUNDS = "out_of_bounds"
STATUS_INVALID = "invalid"

_SUBSYSTEMS = ("ars", "ogs", "wrs")

_CAPACITY_KEY_BY_SUBSYSTEM = {
    var.subsystem: key for key, var in CAPACITY_VARIABLES.items()
}

# Defaults mirror scenario.yaml `design_constraints:`; they keep the module
# usable (and unit-testable) when a scenario omits the section entirely.
DEFAULT_BUDGETS: Dict[str, float] = {
    "max_total_mass_kg": 4000.0,
    "max_total_cost_musd": 500.0,
    "max_total_volume_m3": 14.0,
}

DEFAULT_BOUNDS: Dict[str, Dict[str, float]] = {
    "ars": {"min": 4.5, "max": 80.0},
    "ogs": {"min": 9.25, "max": 80.0},
    "wrs": {"min": 1.0, "max": 20.0},
}

DEFAULT_SIZING: Dict[str, Any] = {
    "baseline": {
        "ars": BASELINE_CAPACITY["plant_sim.ars.capacity_kg_day"],
        "ogs": BASELINE_CAPACITY["plant_sim.ogs.max_o2_kg_day"],
        "wrs": BASELINE_CAPACITY["plant_sim.wrs.max_feed_l_per_operation"],
    },
    "mass_kg": {
        "ars": {"fixed": 180.0, "variable_at_baseline": 270.0},
        "ogs": {"fixed": 250.0, "variable_at_baseline": 450.0},
        "wrs": {"fixed": 300.0, "variable_at_baseline": 350.0},
    },
    "volume_m3": {
        "ars": {"fixed": 0.8, "variable_at_baseline": 1.2},
        "ogs": {"fixed": 1.0, "variable_at_baseline": 1.3},
        "wrs": {"fixed": 1.2, "variable_at_baseline": 1.3},
    },
    "hardware_cost_musd": {
        "ars": {"fixed": 15.0, "variable_at_baseline": 25.0},
        "ogs": {"fixed": 20.0, "variable_at_baseline": 45.0},
        "wrs": {"fixed": 18.0, "variable_at_baseline": 37.0},
    },
    "launch_cost_musd_per_kg": 0.055,
}

DEFAULT_SIMULATION_POLICY: Dict[str, bool] = {
    "run_invalid_candidates": False,
    "run_over_budget_candidates": True,
    "run_out_of_bounds_candidates": True,
    # An unbuildable machine is not a design, so bounds gate adoption. Budgets
    # do not: an over-budget design that saves the whole crew is reported as
    # provisional and left for a human to accept or refuse.
    "require_in_bounds_final": True,
    "require_feasible_final": False,
}

DEFAULT_PENALTY_WEIGHTS: Dict[str, float] = {"mass": 0.5, "cost": 0.3, "volume": 0.2}


def _num(source: Mapping[str, Any], key: str, default: float) -> float:
    try:
        value = float(source.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _merge_affine(
    defaults: Mapping[str, Any],
    override: Any,
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    override = override if isinstance(override, Mapping) else {}
    for sub in _SUBSYSTEMS:
        base = dict(defaults.get(sub) or {})
        incoming = override.get(sub)
        incoming = incoming if isinstance(incoming, Mapping) else {}
        out[sub] = {
            "fixed": _num(incoming, "fixed", float(base.get("fixed", 0.0))),
            "variable_at_baseline": _num(
                incoming,
                "variable_at_baseline",
                float(base.get("variable_at_baseline", 0.0)),
            ),
        }
    return out


@dataclass(frozen=True)
class DesignConstraints:
    enabled: bool = True
    objective_primary: str = "require_full_survival"
    objective_secondary: str = "minimize_resource_footprint"
    budgets: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BUDGETS))
    bounds: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_BOUNDS.items()}
    )
    sizing_mode: str = SIZING_MODE
    baseline_capacity: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_SIZING["baseline"])
    )
    # What is actually installed in the scenario this review is sizing against.
    # A candidate that names only ARS is still a whole station: the other two
    # subsystems weigh what the machine currently in the config weighs, not what
    # the sizing-model baseline weighs.
    installed_capacity: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_SIZING["baseline"])
    )
    mass_kg: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: _merge_affine(DEFAULT_SIZING["mass_kg"], {})
    )
    volume_m3: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: _merge_affine(DEFAULT_SIZING["volume_m3"], {})
    )
    hardware_cost_musd: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: _merge_affine(DEFAULT_SIZING["hardware_cost_musd"], {})
    )
    launch_cost_musd_per_kg: float = float(DEFAULT_SIZING["launch_cost_musd_per_kg"])
    simulation_policy: Dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_SIMULATION_POLICY)
    )
    penalty_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PENALTY_WEIGHTS)
    )

    # ------------------------------------------------------------------ #
    @classmethod
    def from_scenario_config(cls, config: Optional[Mapping[str, Any]]) -> "DesignConstraints":
        installed = cls._installed_from_config(config)
        section = (config or {}).get("design_constraints")
        if not isinstance(section, Mapping):
            return cls(installed_capacity=installed)

        objective = section.get("objective")
        objective = objective if isinstance(objective, Mapping) else {}
        cls._check_objective(objective)
        budgets_raw = section.get("budgets")
        budgets_raw = budgets_raw if isinstance(budgets_raw, Mapping) else {}
        budgets = {
            key: _num(budgets_raw, key, default) for key, default in DEFAULT_BUDGETS.items()
        }

        bounds_raw = section.get("subsystem_bounds")
        bounds_raw = bounds_raw if isinstance(bounds_raw, Mapping) else {}
        bounds: Dict[str, Dict[str, float]] = {}
        min_keys = {"ars": "min_capacity_kg_day", "ogs": "min_o2_kg_day", "wrs": "min_feed_l_per_operation"}
        max_keys = {"ars": "max_capacity_kg_day", "ogs": "max_o2_kg_day", "wrs": "max_feed_l_per_operation"}
        for sub in _SUBSYSTEMS:
            block = bounds_raw.get(sub)
            block = block if isinstance(block, Mapping) else {}
            bounds[sub] = {
                "min": _num(block, min_keys[sub], DEFAULT_BOUNDS[sub]["min"]),
                "max": _num(block, max_keys[sub], DEFAULT_BOUNDS[sub]["max"]),
            }

        sizing = section.get("sizing_model")
        sizing = sizing if isinstance(sizing, Mapping) else {}
        baseline_raw = sizing.get("baseline")
        baseline_raw = baseline_raw if isinstance(baseline_raw, Mapping) else {}
        baseline = {
            "ars": _num(baseline_raw, "ars_capacity_kg_day", DEFAULT_SIZING["baseline"]["ars"]),
            "ogs": _num(baseline_raw, "ogs_max_o2_kg_day", DEFAULT_SIZING["baseline"]["ogs"]),
            "wrs": _num(
                baseline_raw,
                "wrs_max_feed_l_per_operation",
                DEFAULT_SIZING["baseline"]["wrs"],
            ),
        }

        policy_raw = section.get("simulation_policy")
        policy_raw = policy_raw if isinstance(policy_raw, Mapping) else {}
        policy = {
            key: bool(policy_raw.get(key, default))
            for key, default in DEFAULT_SIMULATION_POLICY.items()
        }

        weights_raw = section.get("penalty_weights")
        weights_raw = weights_raw if isinstance(weights_raw, Mapping) else {}
        weights = {
            key: _num(weights_raw, key, default)
            for key, default in DEFAULT_PENALTY_WEIGHTS.items()
        }

        return cls(
            enabled=bool(section.get("enabled", True)),
            objective_primary=str(objective.get("primary", cls.objective_primary)),
            objective_secondary=str(objective.get("secondary", cls.objective_secondary)),
            budgets=budgets,
            bounds=bounds,
            sizing_mode=str(sizing.get("mode", SIZING_MODE)),
            baseline_capacity=baseline,
            mass_kg=_merge_affine(DEFAULT_SIZING["mass_kg"], sizing.get("mass_kg")),
            volume_m3=_merge_affine(DEFAULT_SIZING["volume_m3"], sizing.get("volume_m3")),
            hardware_cost_musd=_merge_affine(
                DEFAULT_SIZING["hardware_cost_musd"], sizing.get("hardware_cost_musd")
            ),
            launch_cost_musd_per_kg=_num(
                sizing,
                "launch_cost_musd_per_kg",
                float(DEFAULT_SIZING["launch_cost_musd_per_kg"]),
            ),
            simulation_policy=policy,
            penalty_weights=weights,
            installed_capacity=installed,
        )

    @staticmethod
    def _installed_from_config(config: Optional[Mapping[str, Any]]) -> Dict[str, float]:
        """Per-subsystem capacity currently configured (baseline when absent)."""
        fields = read_capacity_fields(config or {})
        return {
            sub: float(fields[_CAPACITY_KEY_BY_SUBSYSTEM[sub]]) for sub in _SUBSYSTEMS
        }

    @staticmethod
    def _check_objective(objective: Mapping[str, Any]) -> None:
        """Fail loudly on an objective the ranking does not implement (§9).

        The ranking is a safety property, not a knob: it is written in code on
        purpose. The YAML key documents which objective that code implements, so
        a value the code does not implement is a mismatch, not a preference.
        """
        problems = []
        for name, supported in SUPPORTED_OBJECTIVES.items():
            value = objective.get(name)
            if value is None:
                continue
            if str(value) not in supported:
                problems.append(
                    f"design_constraints.objective.{name}={value!r} is not implemented "
                    f"(supported: {', '.join(supported)})"
                )
        if problems:
            raise ValueError("; ".join(problems))

    # ------------------------------------------------------------------ #
    def capacity_by_subsystem(self, fields: Mapping[str, Any]) -> Dict[str, float]:
        """Fill the three variables, defaulting to the *installed* machine.

        A partial candidate (``fields`` naming only ARS) is still evaluated as a
        whole station. Defaulting the unnamed subsystems to the sizing-model
        baseline would price a station that is not the one the candidate
        simulation actually runs.
        """
        out: Dict[str, float] = {}
        for sub in _SUBSYSTEMS:
            key = _CAPACITY_KEY_BY_SUBSYSTEM[sub]
            fallback = float(self.installed_capacity.get(sub, self.baseline_capacity[sub]))
            raw = fields.get(key, fallback)
            try:
                out[sub] = float(raw)
            except (TypeError, ValueError):
                out[sub] = fallback
        return out

    def capacity_source(self, fields: Mapping[str, Any]) -> Dict[str, str]:
        """Whether each subsystem's capacity came from the candidate or the config."""
        return {
            sub: ("candidate" if _CAPACITY_KEY_BY_SUBSYSTEM[sub] in fields else "installed")
            for sub in _SUBSYSTEMS
        }

    def _affine(self, table: Mapping[str, Mapping[str, float]], sub: str, ratio: float) -> float:
        block = table.get(sub) or {}
        return float(block.get("fixed", 0.0)) + float(
            block.get("variable_at_baseline", 0.0)
        ) * ratio

    def footprint(self, fields: Mapping[str, Any]) -> Dict[str, Any]:
        """Mass / volume / cost of a full capacity set (no feasibility verdict)."""
        capacity = self.capacity_by_subsystem(fields)
        by_subsystem: Dict[str, Dict[str, float]] = {}
        total_mass = total_volume = total_hw_cost = 0.0
        for sub in _SUBSYSTEMS:
            baseline = max(float(self.baseline_capacity[sub]), 1e-9)
            ratio = capacity[sub] / baseline
            mass = self._affine(self.mass_kg, sub, ratio)
            volume = self._affine(self.volume_m3, sub, ratio)
            cost = self._affine(self.hardware_cost_musd, sub, ratio)
            by_subsystem[sub] = {
                "capacity": capacity[sub],
                "capacity_ratio": ratio,
                "mass_kg": mass,
                "volume_m3": volume,
                "hardware_cost_musd": cost,
            }
            total_mass += mass
            total_volume += volume
            total_hw_cost += cost
        launch_cost = total_mass * self.launch_cost_musd_per_kg
        return {
            "sizing_mode": self.sizing_mode,
            "by_subsystem": by_subsystem,
            "total_mass_kg": total_mass,
            "total_volume_m3": total_volume,
            "hardware_cost_musd": total_hw_cost,
            "launch_cost_musd": launch_cost,
            "total_cost_musd": total_hw_cost + launch_cost,
        }

    def baseline_footprint(self) -> Dict[str, Any]:
        """Footprint of the sizing-model baseline machine (the reference point)."""
        return self.footprint(
            {
                _CAPACITY_KEY_BY_SUBSYSTEM[sub]: self.baseline_capacity[sub]
                for sub in _SUBSYSTEMS
            }
        )

    def installed_footprint(self) -> Dict[str, Any]:
        """Footprint of the machine the scenario currently configures."""
        return self.footprint({})

    def max_footprint(self) -> Dict[str, Any]:
        return self.footprint(
            {
                _CAPACITY_KEY_BY_SUBSYSTEM[sub]: self.bounds[sub]["max"]
                for sub in _SUBSYSTEMS
            }
        )

    # ------------------------------------------------------------------ #
    def preflight(self, fields: Any) -> Tuple[str, List[str]]:
        """Block only candidates that cannot meaningfully be simulated."""
        errors = validate_capacity_fields(fields)
        if errors:
            return STATUS_INVALID, errors
        return "valid", []

    def evaluate(self, fields: Mapping[str, Any]) -> Dict[str, Any]:
        """Label a candidate: footprint, bound / budget violations, status."""
        preflight_status, preflight_errors = self.preflight(fields)
        if preflight_status == STATUS_INVALID:
            return {
                "constraint_status": STATUS_INVALID,
                "constraints_enforced": self.enabled,
                "preflight_status": preflight_status,
                "preflight_errors": preflight_errors,
                "violations": preflight_errors,
                "fields": dict(fields) if isinstance(fields, Mapping) else {},
            }

        footprint = self.footprint(fields)
        baseline = self.baseline_footprint()
        capacity = self.capacity_by_subsystem(fields)

        # ``enabled: false`` keeps the footprint numbers (they still describe the
        # candidate) but stops labelling anything infeasible, so budgets and
        # engineering bounds no longer steer the final choice.
        bound_violations: List[str] = []
        budget_violations: List[str] = []
        if self.enabled:
            for sub in _SUBSYSTEMS:
                key = _CAPACITY_KEY_BY_SUBSYSTEM[sub]
                if key not in fields:
                    continue
                low, high = self.bounds[sub]["min"], self.bounds[sub]["max"]
                value = capacity[sub]
                if value < low:
                    bound_violations.append(f"{key}={value:g} below min {low:g}")
                elif value > high:
                    bound_violations.append(f"{key}={value:g} above max {high:g}")

            checks = (
                ("max_total_mass_kg", footprint["total_mass_kg"], "total_mass_kg"),
                ("max_total_cost_musd", footprint["total_cost_musd"], "total_cost_musd"),
                ("max_total_volume_m3", footprint["total_volume_m3"], "total_volume_m3"),
            )
            for budget_key, value, label in checks:
                cap = self.budgets.get(budget_key)
                if cap is None:
                    continue
                if value > cap + 1e-9:
                    budget_violations.append(
                        f"{label}={value:.3f} exceeds {budget_key}={cap:g}"
                    )

        if bound_violations:
            status = STATUS_OUT_OF_BOUNDS
        elif budget_violations:
            status = STATUS_OVER_BUDGET
        else:
            status = STATUS_FEASIBLE

        installed = self.installed_footprint()
        added = {
            "added_mass_kg": footprint["total_mass_kg"] - baseline["total_mass_kg"],
            "added_volume_m3": footprint["total_volume_m3"] - baseline["total_volume_m3"],
            "added_cost_musd": footprint["total_cost_musd"] - baseline["total_cost_musd"],
        }
        # Signed: a candidate that downsizes a subsystem gives mass back.
        delta_installed = {
            "delta_installed_mass_kg": footprint["total_mass_kg"] - installed["total_mass_kg"],
            "delta_installed_volume_m3": (
                footprint["total_volume_m3"] - installed["total_volume_m3"]
            ),
            "delta_installed_cost_musd": (
                footprint["total_cost_musd"] - installed["total_cost_musd"]
            ),
        }
        return {
            "constraint_status": status,
            "constraints_enforced": self.enabled,
            "preflight_status": preflight_status,
            "preflight_errors": [],
            "fields": {key: float(value) for key, value in fields.items()},
            "capacity_by_subsystem": capacity,
            "capacity_source": self.capacity_source(fields),
            "installed_capacity": dict(self.installed_capacity),
            **footprint,
            **added,
            **delta_installed,
            "baseline_total_mass_kg": baseline["total_mass_kg"],
            "baseline_total_volume_m3": baseline["total_volume_m3"],
            "baseline_total_cost_musd": baseline["total_cost_musd"],
            "installed_total_mass_kg": installed["total_mass_kg"],
            "installed_total_volume_m3": installed["total_volume_m3"],
            "installed_total_cost_musd": installed["total_cost_musd"],
            "bound_violations": bound_violations,
            "budget_violations": budget_violations,
            "violations": bound_violations + budget_violations,
            "design_penalty": self.design_penalty(added),
            "simulate_allowed": self.should_simulate(status),
            "budgets": dict(self.budgets),
            "subsystem_bounds": {k: dict(v) for k, v in self.bounds.items()},
        }

    def design_penalty(self, added: Mapping[str, float]) -> float:
        """Explanatory footprint score in ~[0, 1]; the rank key stays canonical."""
        ceiling = self.max_footprint()
        baseline = self.baseline_footprint()
        spans = {
            "mass": max(ceiling["total_mass_kg"] - baseline["total_mass_kg"], 1e-9),
            "cost": max(ceiling["total_cost_musd"] - baseline["total_cost_musd"], 1e-9),
            "volume": max(ceiling["total_volume_m3"] - baseline["total_volume_m3"], 1e-9),
        }
        values = {
            "mass": float(added.get("added_mass_kg", 0.0)),
            "cost": float(added.get("added_cost_musd", 0.0)),
            "volume": float(added.get("added_volume_m3", 0.0)),
        }
        return sum(
            self.penalty_weights.get(name, 0.0) * values[name] / spans[name] for name in spans
        )

    def should_simulate(self, status: str) -> bool:
        policy = self.simulation_policy
        if status == STATUS_INVALID:
            return bool(policy.get("run_invalid_candidates", False))
        if status == STATUS_OVER_BUDGET:
            return bool(policy.get("run_over_budget_candidates", True))
        if status == STATUS_OUT_OF_BOUNDS:
            return bool(policy.get("run_out_of_bounds_candidates", True))
        return True

    @property
    def require_feasible_final(self) -> bool:
        """Whether busting a budget disqualifies a candidate (default: no)."""
        return bool(self.simulation_policy.get("require_feasible_final", False))

    @property
    def require_in_bounds_final(self) -> bool:
        """Whether a machine outside the engineering bounds may be adopted."""
        return bool(self.simulation_policy.get("require_in_bounds_final", True))

    def clamp_to_bounds(self, subsystem: str, value: float) -> float:
        """Keep a sized capacity inside what can actually be built."""
        block = self.bounds.get(subsystem) or {}
        low = float(block.get("min", 0.0))
        high = float(block.get("max", float("inf")))
        return min(max(float(value), low), high)

    def describe(self) -> Dict[str, Any]:
        """Compact, LLM-facing description of the constraint environment."""
        return {
            "enabled": self.enabled,
            "objective": {
                "primary": self.objective_primary,
                "secondary": self.objective_secondary,
                "note": (
                    "full survival is the clearance line, not a score: a design that "
                    "loses an occupant is never adopted. Among designs that keep every "
                    "occupant alive, less CRITICAL dwell wins first, then warning "
                    "dwell, then the smallest mass, volume, and cost."
                ),
            },
            "design_variables": list(CAPACITY_KEYS),
            "installed_capacity": dict(self.installed_capacity),
            "budgets": dict(self.budgets),
            "subsystem_bounds": {k: dict(v) for k, v in self.bounds.items()},
            "sizing_model": {
                "mode": self.sizing_mode,
                "baseline_capacity": dict(self.baseline_capacity),
                "launch_cost_musd_per_kg": self.launch_cost_musd_per_kg,
                "note": (
                    "exploration coefficients, not flight hardware estimates; "
                    "mass/volume/cost = fixed + variable_at_baseline * "
                    "(capacity / baseline_capacity)"
                ),
            },
            "simulation_policy": dict(self.simulation_policy),
            "baseline_footprint": {
                key: value
                for key, value in self.baseline_footprint().items()
                if key != "by_subsystem"
            },
            "installed_footprint": {
                key: value
                for key, value in self.installed_footprint().items()
                if key != "by_subsystem"
            },
        }


__all__ = [
    "DesignConstraints",
    "SIZING_MODE",
    "SUPPORTED_OBJECTIVES",
    "STATUS_FEASIBLE",
    "STATUS_INVALID",
    "STATUS_OUT_OF_BOUNDS",
    "STATUS_OVER_BUDGET",
]
