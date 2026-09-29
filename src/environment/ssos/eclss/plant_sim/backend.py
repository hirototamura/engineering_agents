"""PlantSimEclssBackend — EclssBackend adapter over the mass-balance PlantModel.

Directly implements the ``EclssBackend`` protocol (does NOT inherit
``MockEclssBackend``) to keep a single source of truth for inventory and avoid
the parent's hidden ``_telemetry`` / ``_grey_water_buffer`` duplication.

Responsibilities that live here (not in the model):
- input validation (reject negative / NaN / Inf; allow 0 as no-op for goals)
- subsystem-failure gating (no mutation while a subsystem is failed)
- wrapping model result dicts into ActionResult / ServiceResult
- telemetry mapping (cabin CO2 -> co2_storage_kg; extras -> raw_topics.plant_sim)

Design reference: SSOS_MOCK_ECLSS_DESIGN_PLAN.md v2 §3.3, §6, §8, §9.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

from environment.ssos.eclss.plant_sim.config import PlantSimConfig
from environment.ssos.eclss.plant_sim.model import PlantModel
from environment.ssos.eclss.types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)

_SUBSYSTEMS = ("ars", "ogs", "wrs")
_PHYSICS_LIMITING_LABELS = {
    "o2": "o2_physics",
    "water": "water_physics",
    "co2": "co2_physics",
}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _map_physics_limiting(limiting: list) -> list[str]:
    mapped: list[str] = []
    for item in limiting:
        label = _PHYSICS_LIMITING_LABELS.get(str(item), str(item))
        if label not in mapped:
            mapped.append(label)
    return mapped


class PlantSimEclssBackend:
    """Deterministic mass-balance ECLSS backend for agent simulation."""

    def __init__(self, config: Optional[PlantSimConfig] = None) -> None:
        self.config = config or PlantSimConfig()
        self.model = PlantModel(self.config)
        self._failure_flags: Dict[str, bool] = {sub: False for sub in _SUBSYSTEMS}
        self.last_ars_goal: Optional[ArsGoal] = None
        self.last_ogs_goal: Optional[OgsGoal] = None
        self.last_wrs_goal: Optional[WrsGoal] = None
        self._last_metabolism: Optional[Dict[str, float]] = None
        # What each subsystem actually processed during the current step.
        # The physics gate audits a run from telemetry alone, so the
        # quantities it checks against installed capacity have to be in the
        # telemetry rather than only in the action results. Cleared at the
        # step boundary, not on poll: a step is polled more than once and
        # clearing on the first poll would drop the operations before the
        # post-ops row is written.
        self._operations_this_step: List[Dict[str, Any]] = []
        self._last_survival: Dict[str, Any] = {"lost_this_step": 0, "limiting": []}
        # Operation duration guard (design doc §7.1): a subsystem accepted now
        # stays busy for ceil(operation_seconds / step_seconds) steps.
        self._step_index = 0
        self._busy_remaining: Dict[str, int] = {sub: 0 for sub in _SUBSYSTEMS}

    @classmethod
    def from_scenario_config(cls, config: Mapping[str, Any]) -> "PlantSimEclssBackend":
        return cls(PlantSimConfig.from_scenario_config(config))

    # ------------------------------------------------------------------ #
    # step capability (StepAdvanceableBackend)
    # ------------------------------------------------------------------ #
    def advance_step(self) -> None:
        self._last_survival = {"lost_this_step": 0, "limiting": []}
        self._operations_this_step = []
        self._step_index += 1
        for sub, remaining in self._busy_remaining.items():
            if remaining > 0:
                self._busy_remaining[sub] = remaining - 1
        self._last_metabolism = self.model.advance_step()

    # ------------------------------------------------------------------ #
    # operation duration / busy guard
    # ------------------------------------------------------------------ #
    def busy_steps(self, subsystem: str) -> int:
        """Steps a single ``subsystem`` operation occupies (>= 1)."""
        c = self.config
        seconds = {
            "ars": c.ars_operation_seconds,
            "ogs": c.ogs_operation_seconds,
            "wrs": c.wrs_operation_seconds,
        }[subsystem]
        step_seconds = max(float(c.step_seconds), 1e-9)
        return max(1, int(math.ceil(float(seconds) / step_seconds)))

    def busy_remaining_steps(self, subsystem: str) -> int:
        return int(self._busy_remaining.get(subsystem, 0))

    def _busy_rejection(self, subsystem: str, label: str) -> Optional[ActionResult]:
        if not self.config.operation_busy_guard_enabled:
            return None
        remaining = int(self._busy_remaining.get(subsystem, 0))
        if remaining <= 0:
            return None
        return ActionResult(
            False,
            f"{label} rejected: {subsystem.upper()} is busy for {remaining} more step(s)",
            {
                "rejected": True,
                "reason": "subsystem_busy",
                "subsystem": subsystem,
                "remaining_steps": remaining,
                "busy_until_step": self._step_index + remaining,
                "operation_busy_steps": self.busy_steps(subsystem),
            },
        )

    def _mark_busy(self, subsystem: str) -> None:
        if not self.config.operation_busy_guard_enabled:
            return
        self._busy_remaining[subsystem] = self.busy_steps(subsystem)

    def apply_capacity_drop(self) -> Dict[str, Any]:
        """Physics floor after band-dwell; returns physics-only lost/limiting.

        Telemetry ``survival`` merges this with any dwell losses already
        recorded by ``set_crew_alive`` in the same step.
        """
        result = dict(self.model.apply_capacity_drop())
        result["limiting"] = _map_physics_limiting(list(result.get("limiting") or []))
        self._merge_last_survival(
            int(result.get("lost_this_step") or 0),
            list(result.get("limiting") or []),
        )
        return result

    def set_crew_alive(self, n: int, limiting: Optional[list] = None) -> int:
        """Hard-set live occupants; never increases. Returns additional lost."""
        s = self.model.state
        current = int(s.crew_alive)
        n = max(0, min(int(n), current))
        lost = current - n
        s.crew_alive = n
        s.crew_lost_total += lost
        self._merge_last_survival(lost, list(limiting or []))
        return lost

    def _merge_last_survival(self, lost: int, limiting: list) -> None:
        if lost <= 0 and not limiting:
            return
        prev_lost = int(self._last_survival.get("lost_this_step") or 0)
        prev_lim = list(self._last_survival.get("limiting") or [])
        extra = [item for item in limiting if item not in prev_lim]
        self._last_survival = {
            "lost_this_step": prev_lost + max(0, int(lost)),
            "limiting": prev_lim + extra,
        }

    _OPERATION_FIELDS = {
        "ars": ("co2_removed_kg", "captured_co2_kg", "vented_co2_kg", "goal_scale"),
        "ogs": ("processed_water_kg", "o2_generated_kg", "sabatier_co2_used_kg"),
        "wrs": ("urine_feed_l", "grey_feed_l", "recovered_water_l", "brine_loss_l"),
    }

    def _record_operation(self, subsystem: str, result: Mapping[str, Any]) -> None:
        """Remember what one operation processed, for the next telemetry poll."""
        entry: Dict[str, Any] = {"subsystem": subsystem}
        for field in self._OPERATION_FIELDS[subsystem]:
            value = result.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                entry[field] = float(value)
        self._operations_this_step.append(entry)

    def poll_telemetry(self) -> EclssTelemetrySnapshot:
        s = self.model.state
        plant_sim_topic: Dict[str, Any] = {
            "simulation_time_s": s.simulation_time_s,
            # Persist enough cumulative bookkeeping for the deterministic
            # evaluator to independently audit each candidate run.
            "initial_captured_co2_kg": self.config.initial_captured_co2_kg,
            "initial_urine_buffer_l": self.config.initial_urine_buffer_l,
            "initial_grey_water_l": self.config.initial_grey_water_l,
            "captured_co2_kg": s.captured_co2_kg,
            "urine_buffer_l": s.urine_buffer_l,
            "total_co2_vented_kg": s.total_co2_vented_kg,
            "total_h2_vented_kg": s.total_h2_vented_kg,
            "total_ch4_vented_kg": s.total_ch4_vented_kg,
            "total_wrs_brine_loss_l": s.total_wrs_brine_loss_l,
            "total_o2_shortfall_kg": s.total_o2_shortfall_kg,
            "total_water_shortfall_l": s.total_water_shortfall_l,
            "total_unrecoverable_crew_water_l": s.total_unrecoverable_crew_water_l,
            "total_co2_generated_kg": s.total_co2_generated_kg,
            "total_o2_consumed_kg": s.total_o2_consumed_kg,
            "total_potable_water_consumed_l": s.total_potable_water_consumed_l,
            "total_urine_generated_l": s.total_urine_generated_l,
            "total_condensate_generated_l": s.total_condensate_generated_l,
            "total_o2_generated_kg": s.total_o2_generated_kg,
            "total_electrolysis_water_kg": s.total_electrolysis_water_kg,
            "total_sabatier_co2_used_kg": s.total_sabatier_co2_used_kg,
            "total_water_regenerated_l": s.total_water_regenerated_l,
            "total_wrs_recovered_water_l": s.total_wrs_recovered_water_l,
            "total_o2_delivered_kg": s.total_o2_delivered_kg,
            "total_co2_delivered_kg": s.total_co2_delivered_kg,
            "total_product_water_delivered_l": s.total_product_water_delivered_l,
            "total_external_grey_water_submitted_l": s.total_external_grey_water_submitted_l,
            "ars_busy_steps_remaining": int(self._busy_remaining["ars"]),
            "ogs_busy_steps_remaining": int(self._busy_remaining["ogs"]),
            "wrs_busy_steps_remaining": int(self._busy_remaining["wrs"]),
            "crew_initial": self.config.crew_size,
            "crew_alive": s.crew_alive,
            "crew_lost_total": s.crew_lost_total,
            "survival": {
                "enabled": bool(self.config.survival_enabled),
                "lost_this_step": int(self._last_survival.get("lost_this_step") or 0),
                "limiting": list(self._last_survival.get("limiting") or []),
            },
        }
        # The gate must not read scenario config, so the operating envelope it
        # checks against travels with the measurement it checks.
        plant_sim_topic["installed_capacity"] = {
            "ars_capacity_kg_day": self.config.ars_capacity_kg_day,
            "ogs_max_o2_kg_day": self.config.ogs_max_o2_kg_day,
            "wrs_max_feed_l_per_operation": self.config.wrs_max_feed_l_per_operation,
            "step_seconds": self.config.step_seconds,
            "ars_operation_seconds": self.config.ars_operation_seconds,
            "ogs_operation_seconds": self.config.ogs_operation_seconds,
            "wrs_operation_seconds": self.config.wrs_operation_seconds,
        }
        plant_sim_topic["failure_state"] = {
            name: bool(flag) for name, flag in self._failure_flags.items()
        }
        plant_sim_topic["operations_this_step"] = list(self._operations_this_step)
        if self._last_metabolism is not None:
            plant_sim_topic["last_metabolism"] = dict(self._last_metabolism)
            self._last_metabolism = None
        return EclssTelemetrySnapshot(
            co2_storage_kg=s.cabin_co2_kg,
            o2_storage_kg=s.available_o2_kg,
            product_water_reserve_l=s.product_water_l,
            grey_water_collected_l=s.grey_water_l,
            ars_failure_enabled=self._failure_flags["ars"],
            ogs_failure_enabled=self._failure_flags["ogs"],
            wrs_failure_enabled=self._failure_flags["wrs"],
            raw_topics={"plant_sim": plant_sim_topic},
        )

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult:
        self.last_ars_goal = goal
        mass = goal.initial_co2_mass
        if not _finite(mass) or mass < 0:
            return ActionResult(
                False,
                "invalid ARS goal: initial_co2_mass must be finite and >= 0",
                {"rejected": True, "initial_co2_mass": mass},
            )
        for name, value in (
            ("initial_moisture_content", goal.initial_moisture_content),
            ("initial_contaminants", goal.initial_contaminants),
        ):
            if not _finite(value) or not 0.0 <= value <= 100.0:
                return ActionResult(
                    False, f"invalid ARS goal: {name} must be within 0..100", {"rejected": True}
                )
        if self._failure_flags["ars"]:
            return ActionResult(False, "ARS subsystem failure: no operation", {"failed": True})
        busy = self._busy_rejection("ars", "air_revitalisation")
        if busy is not None:
            return busy

        self._mark_busy("ars")
        result = self.model.run_ars(mass)
        self._record_operation("ars", result)
        result["ignored_inputs"] = ["initial_moisture_content", "initial_contaminants"]
        return ActionResult(True, "air_revitalisation complete", result)

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        self.last_ogs_goal = goal
        water = goal.input_water_mass
        if not _finite(water) or water < 0:
            return ActionResult(
                False,
                "invalid OGS goal: input_water_mass must be finite and >= 0",
                {"rejected": True, "input_water_mass": water},
            )
        if self._failure_flags["ogs"]:
            return ActionResult(False, "OGS subsystem failure: no operation", {"failed": True})
        busy = self._busy_rejection("ogs", "oxygen_generation")
        if busy is not None:
            return busy

        result = self.model.run_ogs(water)
        if result["processed_water_kg"] <= 0.0:
            # Nothing was electrolysed (empty tank or a zero request), so the
            # cell never ran and does not occupy OGS — same rule as WRS no_feed.
            result["reason"] = "no_water"
            return ActionResult(False, "oxygen_generation no-op: no water available", result)
        self._mark_busy("ogs")
        self._record_operation("ogs", result)
        return ActionResult(True, "oxygen_generation complete", result)

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        self.last_wrs_goal = goal
        urine = goal.urine_volume
        if not _finite(urine) or urine < 0:
            return ActionResult(
                False,
                "invalid WRS goal: urine_volume must be finite and >= 0",
                {"rejected": True, "urine_volume": urine},
            )
        if self._failure_flags["wrs"]:
            return ActionResult(False, "WRS subsystem failure: no operation", {"failed": True})
        busy = self._busy_rejection("wrs", "water_recovery")
        if busy is not None:
            return busy

        result = self.model.run_wrs(urine)
        if not result["has_feed"]:
            # A no-feed batch never ran, so it does not occupy the WRS.
            result["reason"] = "no_feed"
            return ActionResult(False, "water_recovery no-op: no feed available", result)
        self._mark_busy("wrs")
        self._record_operation("wrs", result)
        return ActionResult(True, "water_recovery complete", result)

    # ------------------------------------------------------------------ #
    # services (payout / intake from existing inventory; independent of failures)
    # ------------------------------------------------------------------ #
    def request_o2(self, amount: float) -> ServiceResult:
        return self._request(amount, self.model.request_o2, "o2")

    def request_co2(self, amount: float) -> ServiceResult:
        return self._request(amount, self.model.request_co2, "co2")

    def request_product_water(self, liters: float) -> ServiceResult:
        return self._request(liters, self.model.request_product_water, "product water")

    def submit_grey_water(self, liters: float) -> ServiceResult:
        if not _finite(liters) or liters <= 0:
            return ServiceResult(False, 0.0, "invalid grey water volume: must be finite and > 0")
        accepted = self.model.submit_grey_water(liters)
        return ServiceResult(True, accepted, "grey water accepted")

    def _request(self, amount: float, payout, label: str) -> ServiceResult:
        if not _finite(amount) or amount <= 0:
            return ServiceResult(False, 0.0, f"invalid {label} request: must be finite and > 0")
        granted = payout(amount)
        success = granted >= amount - self.config.invariant_tolerance
        message = f"{label} delivered" if success else f"partial: insufficient {label}"
        return ServiceResult(success, granted, message)

    # ------------------------------------------------------------------ #
    def set_subsystem_failure(self, subsystem: str, enabled: bool) -> None:
        key = subsystem.lower().removesuffix("_failure")
        if key not in self._failure_flags:
            raise ValueError(f"unknown subsystem: {subsystem!r}")
        self._failure_flags[key] = enabled


__all__ = ["PlantSimEclssBackend"]
