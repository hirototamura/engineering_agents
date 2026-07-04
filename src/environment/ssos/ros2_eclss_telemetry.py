"""Persistent rclpy subscriptions for ECLSS storage telemetry.

A single background spin thread keeps the latest ``Float64`` samples for CO₂,
O₂, and product-water topics so ``poll_telemetry()`` avoids per-call
``ros2 topic echo`` subprocesses.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Tuple

from environment.ssos.eclss_topics import (
    TOPIC_CO2_STORAGE,
    TOPIC_O2_STORAGE,
    TOPIC_WRS_PRODUCT_WATER_RESERVE,
)

_TELEMETRY_TOPICS: Tuple[str, ...] = (
    TOPIC_CO2_STORAGE,
    TOPIC_O2_STORAGE,
    TOPIC_WRS_PRODUCT_WATER_RESERVE,
)

_reader_lock = threading.Lock()
_reader_instance: Optional["RclpyEclssTelemetryReader"] = None
_reader_init_failed = False


def rclpy_telemetry_available() -> bool:
    try:
        import rclpy  # noqa: F401
        from std_msgs.msg import Float64  # noqa: F401

        return True
    except ImportError:
        return False


def get_rclpy_telemetry_reader() -> Optional["RclpyEclssTelemetryReader"]:
    """Return a process-wide telemetry reader, or ``None`` if rclpy is unavailable."""
    global _reader_instance, _reader_init_failed
    if _reader_init_failed or not rclpy_telemetry_available():
        return None
    with _reader_lock:
        if _reader_init_failed:
            return None
        if _reader_instance is None:
            try:
                _reader_instance = RclpyEclssTelemetryReader()
            except Exception:
                _reader_init_failed = True
                return None
        return _reader_instance


def reset_rclpy_telemetry_reader() -> None:
    """Tear down the singleton (tests only)."""
    global _reader_instance, _reader_init_failed
    with _reader_lock:
        if _reader_instance is not None:
            _reader_instance.shutdown()
            _reader_instance = None
        _reader_init_failed = False


class RclpyEclssTelemetryReader:
    """Subscribe once, cache latest storage topic values."""

    def __init__(self) -> None:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import Float64

        if not rclpy.ok():
            rclpy.init()
        self._rclpy = rclpy
        self._node: Node = rclpy.create_node("eclss_telemetry_reader")
        self._values: Dict[str, Optional[float]] = {topic: None for topic in _TELEMETRY_TOPICS}
        self._updated_at: Dict[str, Optional[float]] = {topic: None for topic in _TELEMETRY_TOPICS}
        self._values_lock = threading.Lock()
        self._stop = threading.Event()

        for topic in _TELEMETRY_TOPICS:
            self._node.create_subscription(
                Float64,
                topic,
                self._make_callback(topic),
                10,
            )

        self._spin_thread = threading.Thread(target=self._spin_loop, name="eclss-telemetry-spin", daemon=True)
        self._spin_thread.start()

    def _make_callback(self, topic: str):
        def _callback(msg) -> None:
            with self._values_lock:
                self._values[topic] = float(msg.data)
                self._updated_at[topic] = time.monotonic()

        return _callback

    def _spin_loop(self) -> None:
        while not self._stop.is_set() and self._rclpy.ok():
            self._rclpy.spin_once(self._node, timeout_sec=0.1)

    def read(self, wait_timeout_s: float) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Return (co2, o2, water), waiting up to ``wait_timeout_s`` for first samples."""
        return self._read_locked(wait_timeout_s=wait_timeout_s, max_age_s=None)

    def read_fresh(
        self,
        wait_timeout_s: float,
        *,
        max_age_s: float,
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Return samples only when all three topics updated within ``max_age_s``."""
        return self._read_locked(wait_timeout_s=wait_timeout_s, max_age_s=max_age_s)

    def _read_locked(
        self,
        *,
        wait_timeout_s: float,
        max_age_s: Optional[float],
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        deadline = time.monotonic() + max(0.0, wait_timeout_s)
        while time.monotonic() < deadline:
            with self._values_lock:
                co2, o2, water = self._snapshot_values(max_age_s)
            if co2 is not None and o2 is not None and water is not None:
                return co2, o2, water
            time.sleep(0.02)
        with self._values_lock:
            return self._snapshot_values(max_age_s)

    def _snapshot_values(
        self,
        max_age_s: Optional[float],
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        now = time.monotonic()
        values: list[Optional[float]] = []
        for topic in _TELEMETRY_TOPICS:
            value = self._values[topic]
            if value is None:
                values.append(None)
                continue
            if max_age_s is not None:
                updated = self._updated_at.get(topic)
                if updated is None or (now - updated) > max_age_s:
                    values.append(None)
                    continue
            values.append(value)
        return values[0], values[1], values[2]

    def shutdown(self) -> None:
        self._stop.set()
        if self._spin_thread.is_alive():
            self._spin_thread.join(timeout=2.0)
        self._node.destroy_node()
        if self._rclpy.ok():
            self._rclpy.shutdown()
