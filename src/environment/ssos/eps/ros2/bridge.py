"""ROS 2 bridge to SSOS EPS (solar + BCDU) — Phase 3.

Uses ``ros2`` CLI subprocess calls (same pattern as ``Ros2EclssBridge``).
Phase 3a interim: ``request_discharge`` arms a local duration timer; support watts
are taken from live ``/bcdu/status`` when discharging (``current_draw * bus_voltage``),
with armed watts as fallback when SSOS has not entered discharge yet.
"""

from __future__ import annotations

from typing import Optional, Tuple

from environment.scrubber.eps.types import BcduMode, BcduStatus, DischargeResult, SarjReading
from environment.ssos.eps.ros2.adapters import (
    estimate_discharge_w,
    parse_bcdu_status,
    sarj_reading_from_topics,
)
from environment.ssos.ros2.cli import echo_float_topic, run_ros2_cli
from environment.ssos.eps.ros2.topic_map import (
    MSG_TYPE_BCDU_STATUS,
    SSOS_TOPIC_SOLAR_VOLTAGE,
    SSOS_TOPIC_SUN_BETA,
)
from environment.scrubber.eps.topics import BCDU_STATUS


def _echo_topic_once(
    topic: str,
    msg_type: str,
    timeout_s: float = 10.0,
) -> Tuple[Optional[str], Optional[str]]:
    try:
        code, out, err = run_ros2_cli(
            ["topic", "echo", topic, msg_type, "--once"],
            timeout_s=timeout_s,
        )
    except (FileNotFoundError, OSError):
        return None, "ros2 CLI not found"
    if code != 0:
        combined = f"{out}\n{err}".strip()
        return None, combined or f"ros2 topic echo exited {code}"
    return f"{out}\n{err}", None


class Ros2EpsBridge:
    """EpsBackend implementation backed by SSOS EPS ROS 2 graph."""

    def __init__(
        self,
        *,
        topic_timeout_s: float = 10.0,
        max_discharge_w: float = 500.0,
        eclipse_threshold_v: float = 90.0,
    ) -> None:
        self.topic_timeout_s = topic_timeout_s
        self.max_discharge_w = max_discharge_w
        self.eclipse_threshold_v = eclipse_threshold_v
        self._step_count = 0
        self._last_solar_voltage_v = 0.0
        self._last_beta_deg = 0.0
        self._last_bcdu: Optional[BcduStatus] = None
        self._armed_support_w = 0.0
        self._support_steps_remaining = 0

    @staticmethod
    def ros2_available() -> bool:
        try:
            code, _, _ = run_ros2_cli(["--help"], timeout_s=5.0)
            return code == 0
        except (FileNotFoundError, OSError):
            return False

    @property
    def support_w(self) -> float:
        if self._support_steps_remaining > 0:
            if self._last_bcdu is not None:
                live = estimate_discharge_w(self._last_bcdu)
                if live > 0.0:
                    return live
            return self._armed_support_w
        return 0.0

    @property
    def support_steps_remaining(self) -> int:
        return self._support_steps_remaining

    @property
    def bcdu_mode(self) -> BcduMode:
        if self._last_bcdu is not None:
            return self._last_bcdu.mode
        return BcduMode.IDLE

    def poll_solar(self) -> SarjReading:
        voltage = echo_float_topic(SSOS_TOPIC_SOLAR_VOLTAGE, timeout_s=self.topic_timeout_s)
        beta = echo_float_topic(SSOS_TOPIC_SUN_BETA, timeout_s=self.topic_timeout_s)
        if voltage is not None:
            self._last_solar_voltage_v = voltage
        if beta is not None:
            self._last_beta_deg = beta
        self._step_count += 1
        return sarj_reading_from_topics(
            step=self._step_count,
            solar_voltage_v=self._last_solar_voltage_v,
            beta_angle_deg=self._last_beta_deg,
            eclipse_threshold_v=self.eclipse_threshold_v,
        )

    def poll_bcdu(self) -> BcduStatus:
        status = self._read_bcdu_status()
        if status is not None:
            self._last_bcdu = status
        return self._bcdu_snapshot()

    def tick_bcdu(self) -> BcduStatus:
        status = self._read_bcdu_status()
        if status is not None:
            self._last_bcdu = status
        if self._support_steps_remaining > 0:
            self._support_steps_remaining -= 1
            if self._support_steps_remaining == 0:
                self._armed_support_w = 0.0
        return self._bcdu_snapshot()

    def request_discharge(self, support_w: float, duration_steps: int) -> DischargeResult:
        status = self._read_bcdu_status()
        if status is not None:
            self._last_bcdu = status

        if status is not None and status.fault:
            return DischargeResult(
                success=False,
                message=f"BCDU fault latched: {status.fault_message}",
                status=self._bcdu_snapshot(),
            )
        if not (0.0 < support_w <= self.max_discharge_w):
            return DischargeResult(
                success=False,
                message=f"discharge watts out of range: {support_w}",
                status=self._bcdu_snapshot(),
            )
        if duration_steps < 1:
            return DischargeResult(
                success=False,
                message=f"duration_steps must be >= 1, got {duration_steps}",
                status=self._bcdu_snapshot(),
            )

        self._armed_support_w = float(support_w)
        self._support_steps_remaining = int(duration_steps)
        msg = (
            f"discharge armed {self._armed_support_w:.1f} W "
            f"for {self._support_steps_remaining} steps (Phase 3a interim; "
            "awaiting SSOS BCDU discharge telemetry)"
        )
        return DischargeResult(success=True, message=msg, status=self._bcdu_snapshot())

    def consume_scheduled_support(self) -> float:
        if self._support_steps_remaining <= 0:
            return 0.0
        if self._last_bcdu is not None:
            live = estimate_discharge_w(self._last_bcdu)
            if live > 0.0:
                return live
        if self._armed_support_w > 0.0:
            return self._armed_support_w
        return 0.0

    def poll_topics(self) -> dict[str, object]:
        """Read solar + BCDU topics once (smoke / observability).

        Missing topics are reported as ``None`` so smoke tests can fail loudly
        instead of masking absent publishers with cached zero defaults.
        """
        voltage = echo_float_topic(SSOS_TOPIC_SOLAR_VOLTAGE, timeout_s=self.topic_timeout_s)
        beta = echo_float_topic(SSOS_TOPIC_SUN_BETA, timeout_s=self.topic_timeout_s)
        if voltage is not None:
            self._last_solar_voltage_v = voltage
        if beta is not None:
            self._last_beta_deg = beta

        solar = sarj_reading_from_topics(
            step=self._step_count + 1,
            solar_voltage_v=self._last_solar_voltage_v if voltage is not None else 0.0,
            beta_angle_deg=self._last_beta_deg if beta is not None else 0.0,
            eclipse_threshold_v=self.eclipse_threshold_v,
        )
        self._step_count = solar.step

        bcdu = self._read_bcdu_status()
        if bcdu is not None:
            self._last_bcdu = bcdu

        payload: dict[str, object] = {
            "solar_voltage_v": voltage,
            "beta_angle_deg": beta,
            "in_eclipse": solar.in_eclipse if voltage is not None else None,
        }
        if bcdu is not None:
            payload.update(
                {
                    "bcdu_mode": bcdu.mode.value,
                    "bus_voltage_v": bcdu.bus_voltage_v,
                    "current_draw_a": bcdu.current_draw_a,
                    "estimated_discharge_w": estimate_discharge_w(bcdu),
                    "fault": bcdu.fault,
                }
            )
        else:
            payload["bcdu_mode"] = None
        return payload

    def _read_bcdu_status(self) -> Optional[BcduStatus]:
        text, _ = _echo_topic_once(BCDU_STATUS, MSG_TYPE_BCDU_STATUS, timeout_s=self.topic_timeout_s)
        if text is None:
            return None
        return parse_bcdu_status(
            text,
            step=self._step_count,
            support_w=self._armed_support_w if self._support_steps_remaining > 0 else 0.0,
            support_steps_remaining=self._support_steps_remaining,
        )

    def _bcdu_snapshot(self) -> BcduStatus:
        if self._last_bcdu is not None:
            return BcduStatus(
                step=self._last_bcdu.step,
                mode=self._last_bcdu.mode,
                bus_voltage_v=self._last_bcdu.bus_voltage_v,
                regulation_voltage_v=self._last_bcdu.regulation_voltage_v,
                current_draw_a=self._last_bcdu.current_draw_a,
                fault=self._last_bcdu.fault,
                fault_message=self._last_bcdu.fault_message,
                support_w=self.support_w,
                support_steps_remaining=self._support_steps_remaining,
            )
        return BcduStatus(
            step=self._step_count,
            mode=BcduMode.IDLE,
            bus_voltage_v=0.0,
            regulation_voltage_v=0.0,
            current_draw_a=0.0,
            support_w=self.support_w,
            support_steps_remaining=self._support_steps_remaining,
        )
