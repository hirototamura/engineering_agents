#!/usr/bin/env python3
"""Local compatibility entry point; maintained code lives in Engineering Agents."""
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parent.parent
os.environ.setdefault("EA_REPORT_WORKSPACE", str(workspace))
sys.path.insert(0, str(workspace / "engineering_agents" / "src"))
from tools.report_library.catalog import *  # noqa: F403

if __name__ == "__main__":
    main()  # noqa: F405
