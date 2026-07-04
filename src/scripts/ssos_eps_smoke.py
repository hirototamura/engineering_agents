#!/usr/bin/env python3
"""Phase 3: SSOS EPS smoke via Ros2EpsBridge.

Verifies solar + BCDU topic reads from a live SSOS EPS stack.

Run inside SSOS Docker after headless station is up:

    bash /root/ssos-headless.sh   # terminal 1 (solar + EPS + ECLSS)

    PYTHONPATH=src python3 -m scripts.ssos_eps_smoke   # terminal 2 (container)

From host Mac: ./scripts/run_ssos_eps_smoke.sh
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from environment.ssos.eps.ros2.bridge import Ros2EpsBridge
from environment.ssos.eps.ros2.topic_map import LAUNCH_HEADLESS_STATION


@dataclass
class EpsSmokeReport:
    ok: bool
    launch_hint: str
    topics: Optional[Dict[str, Any]] = None
    discharge_armed: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_eps_smoke(
    *,
    topic_timeout_s: float = 15.0,
    arm_discharge_w: float = 0.0,
    arm_duration_steps: int = 0,
) -> EpsSmokeReport:
    launch_hint = f"ros2 launch {LAUNCH_HEADLESS_STATION}"
    report = EpsSmokeReport(ok=False, launch_hint=launch_hint)

    if not Ros2EpsBridge.ros2_available():
        report.errors.append("ros2 CLI not found — run inside SSOS container")
        return report

    bridge = Ros2EpsBridge(topic_timeout_s=topic_timeout_s)
    report.topics = bridge.poll_topics()

    solar_v = report.topics.get("solar_voltage_v")
    if solar_v is None:
        report.errors.append("missing solar voltage from /solar_controller/ssu_voltage_v")
    bcdu_mode = report.topics.get("bcdu_mode")
    if bcdu_mode is None:
        report.errors.append("missing BCDU status from /bcdu/status")

    if arm_discharge_w > 0 and arm_duration_steps > 0:
        discharge = bridge.request_discharge(arm_discharge_w, arm_duration_steps)
        report.discharge_armed = discharge.to_dict()
        if not discharge.success:
            report.errors.append(f"request_discharge failed: {discharge.message}")

    report.ok = not report.errors
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SSOS EPS Phase 3 smoke (ROS2 bridge)")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument("--topic-timeout", type=float, default=15.0)
    parser.add_argument("--arm-discharge-w", type=float, default=0.0)
    parser.add_argument("--arm-duration-steps", type=int, default=0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = run_eps_smoke(
        topic_timeout_s=args.topic_timeout,
        arm_discharge_w=args.arm_discharge_w,
        arm_duration_steps=args.arm_duration_steps,
    )
    payload = report.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not report.ok:
        print(f"\nPhase 3 EPS smoke FAILED. Start SSOS with: {report.launch_hint}", file=sys.stderr)
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nPhase 3 EPS smoke PASSED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
