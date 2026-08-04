"""Shared ``ros2`` CLI helpers for ECLSS and EPS bridges."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Sequence, Tuple

MSG_TYPE_FLOAT64 = "std_msgs/msg/Float64"


def ros2_shell_preamble() -> str:
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


def should_wrap_ros2_cli() -> bool:
    return bool(os.environ.get("PYTHONPATH"))


def run_ros2_cli(args: Sequence[str], timeout_s: float = 30.0) -> Tuple[int, str, str]:
    if should_wrap_ros2_cli():
        quoted = " ".join(shlex.quote(a) for a in ["ros2", *args])
        cmd = f"{ros2_shell_preamble()} && {quoted}"
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


def extract_float(text: str, pattern: str) -> Optional[float]:
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def extract_bool(text: str, pattern: str) -> Optional[bool]:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    token = match.group(1).strip().lower()
    if token in {"true", "1"}:
        return True
    if token in {"false", "0"}:
        return False
    return None


def extract_string(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def extract_float64_data(text: str) -> Optional[float]:
    """Parse ``data`` from ``ros2 topic echo`` (YAML or Jazzy Python repr)."""
    for pattern in (
        r"data:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)",
        r"data=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)",
    ):
        value = extract_float(text, pattern)
        if value is not None:
            return value
    return None


def extract_service_success(text: str) -> Optional[bool]:
    """Parse ``success`` from ros2 service call output (YAML or Jazzy Python repr)."""
    return extract_bool(text, r"success:\s*(true|false)") or extract_bool(
        text, r"success=(true|false)"
    )


def extract_service_field_float(text: str, field: str) -> Optional[float]:
    """Parse a numeric response field (``field: 1.0`` or ``field=1.0``)."""
    pattern = rf"{re.escape(field)}:\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)"
    value = extract_float(text, pattern)
    if value is not None:
        return value
    return extract_float(text, rf"{re.escape(field)}=([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)")


def extract_service_message(text: str) -> Optional[str]:
    """Parse ``message`` from ros2 service call output."""
    for pattern in (
        r"message:\s*'([^']*)'",
        r'message:\s*"([^"]*)"',
        r"message='([^']*)'",
        r'message="([^"]*)"',
    ):
        value = extract_string(text, pattern)
        if value is not None:
            return value
    return None


def echo_float_topic(topic: str, timeout_s: float = 10.0) -> Optional[float]:
    try:
        code, out, err = run_ros2_cli(
            ["topic", "echo", topic, MSG_TYPE_FLOAT64, "--once"],
            timeout_s=timeout_s,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if code != 0:
        return None
    combined = f"{out}\n{err}"
    return extract_float64_data(combined)


def echo_float_topics_parallel(
    topics: Sequence[str],
    timeout_s: float,
) -> dict[str, Optional[float]]:
    """Fetch multiple float topics concurrently via ``ros2 topic echo``."""
    if not topics:
        return {}
    if len(topics) == 1:
        topic = topics[0]
        return {topic: echo_float_topic(topic, timeout_s=timeout_s)}

    results: dict[str, Optional[float]] = {}
    with ThreadPoolExecutor(max_workers=len(topics)) as pool:
        futures = {pool.submit(echo_float_topic, topic, timeout_s): topic for topic in topics}
        for future, topic in futures.items():
            try:
                results[topic] = future.result()
            except Exception:
                results[topic] = None
    return results


# Backward-compatible aliases for tests and EPS bridge imports.
_run_ros2_cli = run_ros2_cli
_echo_float_topic = echo_float_topic
_echo_float_topics_parallel = echo_float_topics_parallel
