"""Record GPU allocation and utilization without inspecting process arguments."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


def sample():
    fields = ["index", "name", "memory.used", "memory.total", "utilization.gpu", "temperature.gpu", "power.draw"]
    result = subprocess.run(["nvidia-smi", "--query-gpu=" + ",".join(fields),
        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10, check=True)
    devices = []
    for line in result.stdout.splitlines():
        cells = [value.strip() for value in line.split(",")]
        row = dict(zip(fields, cells))
        devices.append({"id": int(row["index"]), "name": row["name"],
            "memory_used_mib": float(row["memory.used"]), "memory_total_mib": float(row["memory.total"]),
            "utilization_percent": float(row["utilization.gpu"]),
            "temperature_c": float(row["temperature.gpu"]), "power_w": float(row["power.draw"])})
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "devices": devices}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8", buffering=1) as handle:
        while True:
            try:
                item = sample()
            except Exception as error:
                item = {"timestamp": datetime.now(timezone.utc).isoformat(), "error": str(error)}
            handle.write(json.dumps(item) + "\n")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
