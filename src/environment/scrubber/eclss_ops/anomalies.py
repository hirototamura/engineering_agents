"""Composite anomaly injection for ECLSS mock simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from environment.protocol import AnomalySpec


@dataclass
class ActiveAnomaly:
    spec: AnomalySpec
    activated: bool = False


class AnomalyManager:
    def __init__(self, specs: List[AnomalySpec] | None = None):
        self._anomalies: List[ActiveAnomaly] = [
            ActiveAnomaly(spec=s) for s in (specs or [])
        ]

    def register(self, spec: AnomalySpec) -> None:
        self._anomalies.append(ActiveAnomaly(spec=spec))

    def on_step(self, step: int) -> List[str]:
        """Activate anomalies due at this step; return active anomaly names."""
        active_names: List[str] = []
        for entry in self._anomalies:
            if step >= entry.spec.start_step:
                entry.activated = True
            if entry.activated:
                active_names.append(entry.spec.name)
        return active_names

    def active_specs(self, step: int) -> List[AnomalySpec]:
        self.on_step(step)
        return [a.spec for a in self._anomalies if a.activated]

    def apply_effects(
        self,
        step: int,
        scrubber_efficiency: float,
        power_margin_w: float,
        co2_multiplier: float,
    ) -> tuple[float, float, float]:
        specs = self.active_specs(step)
        eff = scrubber_efficiency
        power = power_margin_w
        mult = co2_multiplier
        for spec in specs:
            eff = max(0.05, eff - spec.scrubber_efficiency_decay_per_step)
            power -= spec.power_margin_decay_per_step
            mult = max(mult, spec.co2_production_multiplier)
        return eff, power, mult
