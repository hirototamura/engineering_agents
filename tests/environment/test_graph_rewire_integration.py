"""Optional integration test for graph_rewire against live SSOS ECLSS."""

import os

import pytest

from scripts.ssos_graph_rewire_smoke import run_graph_rewire_smoke


@pytest.mark.ssos_e2e
def test_graph_rewire_smoke_live_ssos():
    if os.environ.get("SSOS_E2E") != "1":
        pytest.skip("set SSOS_E2E=1 to run live SSOS container regression")

    report = run_graph_rewire_smoke(topic_timeout_s=10.0)
    if report.errors and "ros2 CLI not found" in report.errors[0]:
        pytest.skip("ros2 CLI not available (run inside SSOS container)")
    if report.baseline_co2_kg is None:
        pytest.skip(
            "ECLSS not running — start ~/dev/ssos/ssos-run.sh then "
            "bash /root/ssos-eclss-headless.sh inside container"
        )
    assert report.ok, report.errors
