"""SSOS ECLSS backends for ``ssos_eclss_loop``.

Sibling packages under ``environment/``::

    scrubber/          scrubber_degradation — ppm mock, eclss_ops, eps mock
    ssos/eclss/        this package — storage-kg ECLSS (mock | ros2)
    ssos/eps/ros2/     EPS ROS 2 bridge (not wired into eclss loop yet)
    ssos/ros2/cli.py   shared ``ros2`` subprocess helpers

Layout::

    eclss/
      backend.py, types.py     — shared ``EclssBackend`` protocol and datatypes
      mock/backend.py          — in-memory mock (host dev / CI)
      ros2/                    — SSOS Docker / live ROS 2 graph
        bridge.py, telemetry.py, topics.py, graph_rewire.py
"""

from environment.ssos.eclss.backend import EclssBackend
from environment.ssos.eclss.mock.backend import MockEclssBackend
from environment.ssos.eclss.ros2.bridge import Ros2EclssBridge
from environment.ssos.eclss.types import (
    ActionResult,
    ArsGoal,
    ArsActionResult,
    EclssSmokeReport,
    EclssTelemetrySnapshot,
    OgsGoal,
    ServiceResult,
    WrsGoal,
)

__all__ = [
    "ActionResult",
    "ArsActionResult",
    "ArsGoal",
    "EclssBackend",
    "EclssSmokeReport",
    "EclssTelemetrySnapshot",
    "MockEclssBackend",
    "OgsGoal",
    "Ros2EclssBridge",
    "ServiceResult",
    "WrsGoal",
]
