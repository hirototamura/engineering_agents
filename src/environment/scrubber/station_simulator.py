"""Station facade: ECLSS plant + EPS (SARJ/BCDU) for scrubber_degradation runs."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from environment.protocol import (
    AnomalySpec,
    CommandKind,
    CommandResult,
    DesignState,
    RecoveryCommand,
    TelemetrySnapshot,
    TopologyGraph,
)
from environment.scrubber.eps.backend import EpsBackend
from environment.scrubber.eps.types import BcduStatus, SarjReading
from environment.scrubber.mock_eclss import MockEclssSimulator
from environment.scrubber.eps.mock.backend import MockEpsBackend
from environment.scrubber.topics import EVENT_RECOVERY


class StationSimulator:
    """
    Implements SimulatorProtocol by coupling MockEclssSimulator with an EpsBackend.

    request_eps_boost routes to BCDU discharge; support watts are applied to
    ECLSS power_margin at the start of each step (matching pre-EPS-3 timing).
    """

    def __init__(
        self,
        eclss: MockEclssSimulator,
        eps: Optional[EpsBackend] = None,
    ):
        self.eclss = eclss
        self.eps: EpsBackend = eps or MockEpsBackend()
        self._last_solar: Optional[SarjReading] = None
        self._last_bcdu: Optional[BcduStatus] = None

    @property
    def last_solar(self) -> Optional[SarjReading]:
        return self._last_solar

    @property
    def last_bcdu(self) -> Optional[BcduStatus]:
        return self._last_bcdu

    def inject_anomaly(self, spec: AnomalySpec) -> None:
        self.eclss.inject_anomaly(spec)

    def step(self) -> TelemetrySnapshot:
        solar = self.eps.poll_solar()
        self._last_solar = solar

        support = self.eps.consume_scheduled_support()
        snap = self.eclss.step()
        if support > 0:
            snap = replace(
                snap,
                power_margin_w=round(snap.power_margin_w + support, 2),
                eps_support_w=round(self.eps.support_w, 2),
                eps_support_steps_remaining=self.eps.support_steps_remaining,
            )
        else:
            snap = replace(
                snap,
                eps_support_w=0.0,
                eps_support_steps_remaining=0,
            )

        self._last_bcdu = self.eps.tick_bcdu()
        return snap

    def apply_command(self, cmd: RecoveryCommand) -> CommandResult:
        if cmd.kind == CommandKind.REQUEST_EPS_BOOST:
            return self._apply_eps_boost(cmd)
        return self.eclss.apply_command(cmd)

    def _apply_eps_boost(self, cmd: RecoveryCommand) -> CommandResult:
        from environment.scrubber.eclss_ops.commands import validate_command

        error = validate_command(cmd)
        if error:
            return error

        watts = float(cmd.value)
        duration = int(self.eclss.design.parameters.get("eps_support_duration_steps", 5.0))
        duration = max(1, duration)
        discharge = self.eps.request_discharge(watts, duration)

        if discharge.success:
            self.eclss._event_log.append(
                {
                    "step": self.eclss.step_count,
                    "kind": EVENT_RECOVERY,
                    "command": cmd.to_dict(),
                    "message": discharge.message,
                    "eps": {"bcdu_mode": self.eps.bcdu_mode.value},
                }
            )

        snap = self._current_telemetry()
        return CommandResult(
            success=discharge.success,
            message=discharge.message,
            telemetry=snap,
        )

    def get_topology(self) -> TopologyGraph:
        return self.eclss.get_topology()

    def get_design_parameters(self) -> Dict[str, float]:
        return self.eclss.get_design_parameters()

    def get_design_state(self) -> DesignState:
        return self.eclss.get_design_state()

    def get_events(self) -> List[dict]:
        return self.eclss.get_events()

    def eps_telemetry_dict(self, step: int) -> Dict[str, object]:
        """Row for eps_telemetry.jsonl (EPS-4 observability)."""
        solar = self._last_solar
        bcdu = self._last_bcdu
        return {
            "step": step,
            "solar_voltage_v": solar.solar_voltage_v if solar else None,
            "beta_angle_deg": solar.beta_angle_deg if solar else None,
            "in_eclipse": solar.in_eclipse if solar else False,
            "bcdu_mode": bcdu.mode.value if bcdu else "idle",
            "bus_voltage_v": bcdu.bus_voltage_v if bcdu else None,
            "support_w": bcdu.support_w if bcdu else 0.0,
            "support_steps_remaining": bcdu.support_steps_remaining if bcdu else 0,
            "fault": bcdu.fault if bcdu else False,
            "fault_message": bcdu.fault_message if bcdu else "",
        }

    def _current_telemetry(self) -> TelemetrySnapshot:
        flags = self.eclss.anomalies.on_step(self.eclss.step_count)
        snap = self.eclss._snapshot(flags)
        if self.eps.support_steps_remaining > 0 and self.eps.support_w > 0:
            return replace(
                snap,
                eps_support_w=round(self.eps.support_w, 2),
                eps_support_steps_remaining=self.eps.support_steps_remaining,
            )
        return snap
