"""ROS 2 bridge to SSOS ECLSS (ARS + OGS + WRS).

Telemetry uses a persistent ``rclpy`` subscriber when available; otherwise
parallel ``ros2 topic echo`` CLI calls. Actions and services stay CLI-based so
the bridge works in the SSOS Docker container without extra pip dependencies.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence, Tuple

from environment.ssos.ros2_eclss_telemetry import get_rclpy_telemetry_reader

from environment.ssos.eclss_topics import (
    ACTION_AIR_REVITALISATION,
    ACTION_OXYGEN_GENERATION,
    ACTION_WATER_RECOVERY,
    ACTION_TYPE_AIR_REVITALISATION,
    ACTION_TYPE_OXYGEN_GENERATION,
    ACTION_TYPE_WATER_RECOVERY,
    MSG_TYPE_BOOL,
    MSG_TYPE_FLOAT64,
    SERVICE_ARS_REQUEST_CO2,
    SERVICE_GREY_WATER,
    SERVICE_OGS_REQUEST_O2,
    SERVICE_WRS_PRODUCT_WATER,
    SERVICE_TYPE_CO2_REQUEST,
    SERVICE_TYPE_GREY_WATER,
    SERVICE_TYPE_O2_REQUEST,
    SERVICE_TYPE_PRODUCT_WATER,
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


def _ros2_shell_preamble() -> str:
    """Re-source ROS in a subshell (``PYTHONPATH`` from the parent breaks ``ros2cli``)."""
    distro = os.environ.get("ROS_DISTRO", "jazzy")
    parts = [f"source /opt/ros/{distro}/setup.bash"]
    for candidate in (
        os.environ.get("SSOS_WS_SETUP"),
        os.path.expanduser("~/ssos_ws/install/setup.bash"),
        "/root/ssos_ws/install/setup.bash",
    ):
        if candidate and os.path.isfile(candidate):
            parts.append(f"source {candidate}")
            break
    return " && ".join(parts)


def _should_wrap_ros2_cli() -> bool:
    return bool(os.environ.get("PYTHONPATH"))


def _run_ros2_cli(args: Sequence[str], timeout_s: float = 30.0) -> Tuple[int, str, str]:
    if _should_wrap_ros2_cli():
        quoted = " ".join(shlex.quote(a) for a in ["ros2", *args])
        cmd = f"{_ros2_shell_preamble()} && {quoted}"
        proc = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    else:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            ["ros2", *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=env,
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


def _extract_float64_data(text: str) -> Optional[float]:
    """Parse ``data`` from ``ros2 topic echo`` (YAML or Jazzy Python repr)."""
    for pattern in (
        r"data:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)",
        r"data=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)",
    ):
        value = _extract_float(text, pattern)
        if value is not None:
            return value
    return None


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
    return _extract_float64_data(combined)


def _echo_float_topics_parallel(
    topics: Sequence[str],
    timeout_s: float,
) -> dict[str, Optional[float]]:
    """Fetch multiple float topics concurrently via ``ros2 topic echo``."""
    if not topics:
        return {}
    if len(topics) == 1:
        topic = topics[0]
        return {topic: _echo_float_topic(topic, timeout_s=timeout_s)}

    results: dict[str, Optional[float]] = {}
    with ThreadPoolExecutor(max_workers=len(topics)) as pool:
        futures = {pool.submit(_echo_float_topic, topic, timeout_s): topic for topic in topics}
        for future, topic in futures.items():
            try:
                results[topic] = future.result()
            except Exception:
                results[topic] = None
    return results


def _force_cli_telemetry() -> bool:
    return os.environ.get("SSOS_ECLSS_FORCE_CLI_TELEMETRY", "").lower() in {"1", "true", "yes"}


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
        co2: Optional[float]
        o2: Optional[float]
        water: Optional[float]

        if not _force_cli_telemetry():
            reader = get_rclpy_telemetry_reader()
            if reader is not None:
                co2, o2, water = reader.read(wait_timeout_s=self.topic_timeout_s)
            else:
                co2, o2, water = self._poll_telemetry_cli()
        else:
            co2, o2, water = self._poll_telemetry_cli()

        raw: dict[str, object] = {}
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

    def _poll_telemetry_cli(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        values = _echo_float_topics_parallel(
            (TOPIC_CO2_STORAGE, TOPIC_O2_STORAGE, TOPIC_WRS_PRODUCT_WATER_RESERVE),
            timeout_s=self.topic_timeout_s,
        )
        return (
            values.get(TOPIC_CO2_STORAGE),
            values.get(TOPIC_O2_STORAGE),
            values.get(TOPIC_WRS_PRODUCT_WATER_RESERVE),
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
        goal_yaml = f"{{urine_volume: {goal.urine_volume}}}"
        combined, err = self._send_action_goal(
            ACTION_WATER_RECOVERY,
            ACTION_TYPE_WATER_RECOVERY,
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
                "total_purified_water": _extract_float(
                    combined, r"total_purified_water:\s*([-+]?[0-9]*\.?[0-9]+)"
                ),
                "total_cycles": _extract_float(combined, r"total_cycles:\s*([-+]?[0-9]*\.?[0-9]+)"),
            },
        )

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
        return self._call_service(
            SERVICE_WRS_PRODUCT_WATER,
            SERVICE_TYPE_PRODUCT_WATER,
            f"{{amount: {liters}}}",
            response_field="water_granted",
        )

    def submit_grey_water(self, liters: float) -> ServiceResult:
        return self._call_service(
            SERVICE_GREY_WATER,
            SERVICE_TYPE_GREY_WATER,
            f"{{gray_water_liters: {liters}}}",
        )

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
            code, out, err = _run_ros2_cli(
                [
                    "action",
                    "send_goal",
                    "--feedback",
                    ros_cli_action_name(action_name),
                    action_type,
                    goal_yaml,
                ],
                timeout_s=self.action_timeout_s,
            )
        except FileNotFoundError:
            return "", "ros2 CLI not found"
        except subprocess.TimeoutExpired:
            return "", f"action goal timed out after {self.action_timeout_s}s"

        combined = f"{out}\n{err}"
        if code != 0:
            return combined, combined.strip() or f"ros2 action send_goal exited {code}"
        return combined, None

    def _call_service(
        self,
        service_name: str,
        service_type: str,
        request_yaml: str,
        *,
        response_field: Optional[str] = None,
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
        response_value = (
            _extract_service_field_float(combined, response_field) or 0.0
            if response_field
            else 0.0
        )
        message = _extract_service_message(combined)
        return ServiceResult(success=success, response_value=response_value, message=message or "")
