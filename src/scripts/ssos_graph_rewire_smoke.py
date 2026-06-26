#!/usr/bin/env python3
"""graph_rewire runtime smoke — live SSOS ECLSS (Ros2EclssBridge topic_remap).

Prerequisites (container):

    # host terminal 1
    ~/dev/ssos/ssos-run.sh

    # inside container terminal 2
    bash /root/ssos-eclss-headless.sh

    # host terminal 3
    ./scripts/run_graph_rewire_e2e.sh
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from environment.ssos.eclss_topics import TOPIC_CO2_STORAGE
from environment.ssos.graph_rewire import build_topic_remap
from environment.ssos.ros2_eclss_bridge import Ros2EclssBridge
from scenario.ssos_eclss_loop.scenario_run import build_eclss_backend


@dataclass
class GraphRewireSmokeReport:
    ok: bool
    launch_hint: str
    baseline_co2_kg: Optional[float] = None
    identity_remap_co2_kg: Optional[float] = None
    broken_remap_co2_kg: Optional[float] = None
    backend_remap_public: Optional[str] = None
    backend_remap_backend: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_graph_rewire_smoke(*, topic_timeout_s: float = 15.0) -> GraphRewireSmokeReport:
    launch_hint = (
        "host: ~/dev/ssos/ssos-run.sh  |  container: bash /root/ssos-eclss-headless.sh"
    )
    report = GraphRewireSmokeReport(ok=False, launch_hint=launch_hint)

    if not Ros2EclssBridge.ros2_available():
        report.errors.append("ros2 CLI not found — run inside SSOS container")
        return report

    baseline = Ros2EclssBridge(topic_timeout_s=topic_timeout_s).poll_telemetry()
    report.baseline_co2_kg = baseline.co2_storage_kg
    if baseline.co2_storage_kg is None:
        report.errors.append(
            f"baseline poll missing {TOPIC_CO2_STORAGE} — is ECLSS headless running?"
        )

    identity = Ros2EclssBridge(
        topic_remap={TOPIC_CO2_STORAGE: TOPIC_CO2_STORAGE},
        topic_timeout_s=topic_timeout_s,
    ).poll_telemetry()
    report.identity_remap_co2_kg = identity.co2_storage_kg
    if baseline.co2_storage_kg is not None and identity.co2_storage_kg is None:
        report.errors.append("identity remap broke CO2 poll (expected same topic)")

    broken = Ros2EclssBridge(
        topic_remap={TOPIC_CO2_STORAGE: "/__ea_graph_rewire_missing__"},
        topic_timeout_s=topic_timeout_s,
    ).poll_telemetry()
    report.broken_remap_co2_kg = broken.co2_storage_kg
    if broken.co2_storage_kg is not None:
        report.errors.append("broken remap still returned CO2 (remap not applied?)")

    config_backend = build_eclss_backend(
        {
            "backend": {"kind": "ros2"},
            "ssos_graph": {
                "rewires": [{"public": TOPIC_CO2_STORAGE, "backend": "/alias/co2_storage"}],
            },
        }
    )
    report.backend_remap_public = TOPIC_CO2_STORAGE
    report.backend_remap_backend = config_backend._topic_remap.get(TOPIC_CO2_STORAGE)
    if report.backend_remap_backend != "/alias/co2_storage":
        report.errors.append("build_eclss_backend did not pass ssos_graph.rewires to bridge")

    report.ok = not report.errors
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SSOS graph_rewire runtime smoke")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    parser.add_argument("--topic-timeout", type=float, default=15.0)
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = run_graph_rewire_smoke(topic_timeout_s=args.topic_timeout)
    payload = report.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not report.ok:
        print(f"\ngraph_rewire smoke FAILED. Prerequisites: {report.launch_hint}", file=sys.stderr)
        for err in report.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\ngraph_rewire smoke PASSED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
