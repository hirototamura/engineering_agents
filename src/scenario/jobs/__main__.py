"""Run a RunSpec JSON inside SSOS (no typer/rich — host CLI deps not required)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scenario.jobs.executor import execute_run
from scenario.jobs.spec import RunSpec


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python3 -m scenario.jobs SPEC.json", file=sys.stderr)
        return 2

    spec_path = Path(args[0])
    if not spec_path.exists():
        print(f"RunSpec not found: {spec_path}", file=sys.stderr)
        return 2

    spec = RunSpec.read_json(spec_path)
    result = execute_run(spec)
    if result.error:
        print(result.error, file=sys.stderr)
    print(json.dumps({"run_dir": str(result.run_dir), "exit_code": result.exit_code}))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
