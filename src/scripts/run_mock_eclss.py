"""Run scrubber_degradation baseline (delegates to scenario runner)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scenario.jobs.executor import execute_run
from scenario.jobs.spec import RunSpec


def run_mock_simulation(
    steps: int = 50,
    output_dir: Path | None = None,
    inject_scrubber_anomaly: bool = True,
    anomaly_start_step: int = 20,
) -> Path:
    """Backward-compatible wrapper for tests and scripts."""
    overrides: dict = {"simulation": {"steps": steps}}
    if not inject_scrubber_anomaly:
        overrides["anomalies"] = []
    elif anomaly_start_step != 20:
        overrides["anomalies"] = [
            {
                "name": "scrubber_degradation",
                "start_step": anomaly_start_step,
                "scrubber_efficiency_decay_per_step": 0.02,
                "power_margin_decay_per_step": 3.0,
                "co2_production_multiplier": 1.4,
            }
        ]
    result = execute_run(
        RunSpec(
            scenario="scrubber_degradation",
            output_dir=output_dir,
            overrides=overrides,
            recreate_output=output_dir is None,
        )
    )
    if result.exit_code != 0:
        raise RuntimeError(result.error or "scrubber_degradation run failed")
    return result.run_dir


def main():
    parser = argparse.ArgumentParser(description="Run scrubber_degradation baseline scenario")
    parser.add_argument("--steps", type=int, default=None, help="Override step count")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-anomaly", action="store_true")
    args = parser.parse_args()

    overrides = {}
    if args.steps is not None:
        overrides["simulation"] = {"steps": args.steps}
    if args.no_anomaly:
        overrides["anomalies"] = []

    result = execute_run(
        RunSpec(
            scenario="scrubber_degradation",
            output_dir=args.output,
            overrides=overrides or None,
            recreate_output=args.output is None,
        )
    )
    if result.exit_code != 0:
        raise SystemExit(result.error or "run failed")
    print(f"Wrote scenario output to {result.run_dir}")


if __name__ == "__main__":
    main()
