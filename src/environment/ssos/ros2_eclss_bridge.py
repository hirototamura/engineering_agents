"""ROS 2 bridge to SSOS ECLSS (ARS + OGS in Phase 1b).

Uses ``ros2`` CLI subprocess calls so the bridge works in the SSOS Docker
container without extra Python dependencies. When ``rclpy`` is importable, future
phases may switch hot paths to native clients; Phase 1b stays CLI-first.
"""

from __future__ import annotations

import re
import subprocess
from typing import Optional, Sequence, Tuple

from environment.ssos.eclss_topics import (
    ACTION_AIR_REVITALISATION,
    ACTION_OXYGEN_GENERATION,
    ACTION_TYPE_AIR_REVITALISATION,
    ACTION_TYPE_OXYGEN_GENERATION,
    MSG_TYPE_BOOL,
    MSG_TYPE_FLOAT64,
    SERVICE_ARS_REQUEST_CO2,
    SERVICE_OGS_REQUEST_O2,
    SERVICE_TYPE_CO2_REQUEST,
    SERVICE_TYPE_O2_REQUEST,
    TOPIC_ARS_SELF_DIAGNOSIS,
    TOPIC_CO2_STORAGE,
    TOPIC_O2_STORAGE,
    TOPIC_OGS_SELF_DIAGNOSIS,
    TOPIC_WRS_PRODUCT_WATER_RESERVE,
    TOPIC_WRS_SELF_DIAGNOSIS,
    ros_cli_action_name,
)
from environment.ssos.eclss_types import (
    ActionResult,
    ArsGoal,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)

_SELF_DIAGNOSIS_BY_SUBSYSTEM = {
    "ars": TOPIC_ARS_SELF_DIAGNOSIS,
    "ogs": TOPIC_OGS_SELF_DIAGNOSIS,
    "wrs": TOPIC_WRS_SELF_DIAGNOSIS,
}


def _run_ros2_cli(args: Sequence[str], timeout_s: float = 30.0) -> Tuple[int, str, str]:
    proc = subprocess.run(
        ["ros2", *args],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _extract_float(text: str, pattern: str) -> Optional[float]:
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_bool(text: str, pattern: str) -> Optional[bool]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    token = match.group(1).strip().lower()
    if token in {"true", "1"}:
        return True
    if token in {"false", "0"}:
        return False
    return None


def _extract_service_success(text: str) -> Optional[bool]:
    """Parse ``success`` from ros2 service call output (YAML or Jazzy Python repr)."""
    return _extract_bool(text, r"success:\s*(true|false)") or _extract_bool(
        text, r"success=(true|false)"
    )


def _extract_service_field_float(text: str, field: str) -> Optional[float]:
    """Parse a numeric response field (``field: 1.0`` or ``field=1.0``)."""
    pattern = rf"{re.escape(field)}:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
    value = _extract_float(text, pattern)
    if value is not None:
        return value
    return _extract_float(text, rf"{re.escape(field)}=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")


def _extract_service_message(text: str) -> Optional[str]:
    """Parse ``message`` from ros2 service call output."""
    for pattern in (
        r"message:\s*'([^']*)'",
        r'message:\s*"([^"]*)"',
        r"message='([^']*)'",
        r'message="([^"]*)"',
    ):
        value = _extract_string(text, pattern)
        if value is not None:
            return value
    return None


def _extract_string(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _echo_float_topic(topic: str, timeout_s: float = 10.0) -> Optional[float]:
    try:
        code, out, err = _run_ros2_cli(
            ["topic", "echo", topic, MSG_TYPE_FLOAT64, "--once"],
            timeout_s=timeout_s,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if code != 0:
        return None
    combined = f"{out}\n{err}"
    return _extract_float(combined, r"data:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")


class Ros2EclssBridge:
    """EclssBackend implementation backed by SSOS ROS 2 graph."""

    def __init__(
        self,
        *,
        action_timeout_s: float = 120.0,
        service_timeout_s: float = 30.0,
        topic_timeout_s: float = 10.0,
    ) -> None:
        self.action_timeout_s = action_timeout_s
        self.service_timeout_s = service_timeout_s
        self.topic_timeout_s = topic_timeout_s
        self._failure_flags: dict[str, bool] = {
            "ars": False,
            "ogs": False,
            "wrs": False,
        }

    @staticmethod
    def ros2_available() -> bool:
        try:
            code, _, _ = _run_ros2_cli(["--help"], timeout_s=5.0)
            return code == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def poll_telemetry(self) -> EclssTelemetrySnapshot:
        raw: dict[str, object] = {}
        co2 = _echo_float_topic(TOPIC_CO2_STORAGE, timeout_s=self.topic_timeout_s)
        o2 = _echo_float_topic(TOPIC_O2_STORAGE, timeout_s=self.topic_timeout_s)
        water = _echo_float_topic(TOPIC_WRS_PRODUCT_WATER_RESERVE, timeout_s=self.topic_timeout_s)
        if co2 is not None:
            raw[TOPIC_CO2_STORAGE] = co2
        if o2 is not None:
            raw[TOPIC_O2_STORAGE] = o2
        if water is not None:
            raw[TOPIC_WRS_PRODUCT_WATER_RESERVE] = water
        return EclssTelemetrySnapshot(
            co2_storage_kg=co2,
            o2_storage_kg=o2,
            product_water_reserve_l=water,
            ars_failure_enabled=self._failure_flags["ars"],
            ogs_failure_enabled=self._failure_flags["ogs"],
            wrs_failure_enabled=self._failure_flags["wrs"],
            raw_topics=raw,
        )

    def send_air_revitalisation_goal(self, goal: ArsGoal) -> ActionResult:
        goal_yaml = (
            f"{{initial_co2_mass: {goal.initial_co2_mass}, "
            f"initial_moisture_content: {goal.initial_moisture_content}, "
            f"initial_contaminants: {goal.initial_contaminants}}}"
        )
        combined, err = self._send_action_goal(
            ACTION_AIR_REVITALISATION,
            ACTION_TYPE_AIR_REVITALISATION,
            goal_yaml,
        )
        if err:
            return ActionResult(success=False, summary_message=err)
        success = "Goal finished with status: SUCCEEDED" in combined or "Result:" in combined
        summary = _extract_string(combined, r"summary_message:\s*'([^']*)'") or _extract_string(
            combined, r'summary_message:\s*"([^"]*)"'
        )
        return ActionResult(
            success=success,
            summary_message=summary or "",
            details={
                "cycles_completed": _extract_float(combined, r"cycles_completed:\s*([-+]?[0-9]*\.?[0-9]+)"),
                "total_vents": _extract_float(combined, r"total_vents:\s*([-+]?[0-9]*\.?[0-9]+)"),
                "total_co2_vented": _extract_float(combined, r"total_co2_vented:\s*([-+]?[0-9]*\.?[0-9]+)"),
            },
        )

    def send_oxygen_generation_goal(self, goal: OgsGoal) -> ActionResult:
        goal_yaml = (
            f"{{input_water_mass: {goal.input_water_mass}, "
            f"iodine_concentration: {goal.iodine_concentration}}}"
        )
        combined, err = self._send_action_goal(
            ACTION_OXYGEN_GENERATION,
            ACTION_TYPE_OXYGEN_GENERATION,
            goal_yaml,
        )
        if err:
            return ActionResult(success=False, summary_message=err)
        success = "Goal finished with status: SUCCEEDED" in combined or "Result:" in combined
        summary = _extract_string(combined, r"summary_message:\s*'([^']*)'") or _extract_string(
            combined, r'summary_message:\s*"([^"]*)"'
        )
        return ActionResult(
            success=success,
            summary_message=summary or "",
            details={
                "total_o2_generated": _extract_float(
                    combined, r"total_o2_generated:\s*([-+]?[0-9]*\.?[0-9]+)"
                ),
                "total_ch4_vented": _extract_float(
                    combined, r"total_ch4_vented:\s*([-+]?[0-9]*\.?[0-9]+)"
                ),
            },
        )

    def send_water_recovery_goal(self, goal: WrsGoal) -> ActionResult:
        raise NotImplementedError("WRS actions are Phase 2")

    def request_o2(self, amount: float) -> ServiceResult:
        return self._call_service(
            SERVICE_OGS_REQUEST_O2,
            SERVICE_TYPE_O2_REQUEST,
            f"{{o2_req: {amount}}}",
            response_field="o2_resp",
        )

    def request_co2(self, amount: float) -> ServiceResult:
        return self._call_service(
            SERVICE_ARS_REQUEST_CO2,
            SERVICE_TYPE_CO2_REQUEST,
            f"{{co2_req: {amount}}}",
            response_field="co2_resp",
        )

    def request_product_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("WRS product water is Phase 2")

    def submit_grey_water(self, liters: float) -> ServiceResult:
        raise NotImplementedError("grey water service is Phase 2")

    def set_subsystem_failure(self, subsystem: str, enabled: bool) -> None:
        key = subsystem.lower().removesuffix("_failure")
        topic = _SELF_DIAGNOSIS_BY_SUBSYSTEM.get(key)
        if topic is None:
            raise ValueError(f"unknown subsystem: {subsystem!r}")
        payload = f"{{data: {'true' if enabled else 'false'}}}"
        code, out, err = _run_ros2_cli(
            ["topic", "pub", "--once", topic, MSG_TYPE_BOOL, payload],
            timeout_s=self.service_timeout_s,
        )
        if code != 0:
            raise RuntimeError(err or out or f"ros2 topic pub exited {code}")
        self._failure_flags[key] = enabled

    def _send_action_goal(
        self,
        action_name: str,
        action_type: str,
        goal_yaml: str,
    ) -> Tuple[str, Optional[str]]:
        try:
            proc = subprocess.run(
                [
                    "ros2",
                    "action",
                    "send_goal",
                    "--feedback",
                    ros_cli_action_name(action_name),
                    action_type,
                    goal_yaml,
                ],
                capture_output=True,
                text=True,
                timeout=self.action_timeout_s,
                check=False,
            )
        except FileNotFoundError:
            return "", "ros2 CLI not found"
        except subprocess.TimeoutExpired:
            return "", f"action goal timed out after {self.action_timeout_s}s"

        combined = f"{proc.stdout}\n{proc.stderr}"
        if proc.returncode != 0:
            return combined, combined.strip() or f"ros2 action send_goal exited {proc.returncode}"
        return combined, None

    def _call_service(
        self,
        service_name: str,
        service_type: str,
        request_yaml: str,
        *,
        response_field: str,
    ) -> ServiceResult:
        try:
            code, out, err = _run_ros2_cli(
                ["service", "call", service_name, service_type, request_yaml],
                timeout_s=self.service_timeout_s,
            )
        except FileNotFoundError:
            return ServiceResult(success=False, message="ros2 CLI not found")
        except subprocess.TimeoutExpired:
            return ServiceResult(success=False, message=f"service call timed out after {self.service_timeout_s}s")

        combined = f"{out}\n{err}"
        if code != 0:
            return ServiceResult(success=False, message=combined.strip() or f"ros2 service call exited {code}")

        success = _extract_service_success(combined) or False
        response_value = _extract_service_field_float(combined, response_field) or 0.0
        message = _extract_service_message(combined)
        return ServiceResult(success=success, response_value=response_value, message=message or "")
