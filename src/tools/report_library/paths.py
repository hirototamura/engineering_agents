"""Keep generated reports outside the installed source package."""
from __future__ import annotations

import os
from pathlib import Path


def default_workspace() -> Path:
    directory = Path.cwd().resolve()
    if directory.name == "engineering_agents" and (directory.parent / "one-piece").is_dir():
        return directory.parent
    return directory


WORKSPACE = Path(os.environ.get("EA_REPORT_WORKSPACE", default_workspace())).expanduser().resolve()
HERE = WORKSPACE / "reports"
