"""Run a Python module with an explicitly selected shared, read-only site path.

This bootstraps project dependencies after the active virtual environment's
packages, so its pinned JAX/MuJoCo versions keep precedence.
"""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import site
import sys


def main():
    extra = os.environ.get("EA_SHARED_SITE_PACKAGES", "").strip()
    if extra:
        path = Path(extra).resolve(strict=True)
        if not path.is_dir():
            raise SystemExit("EA_SHARED_SITE_PACKAGES must name an existing directory")
        site.addsitedir(str(path))
    if len(sys.argv) < 3 or sys.argv[1] != "-m":
        raise SystemExit("Usage: run_with_site_packages.py -m MODULE [ARGS ...]")
    module = sys.argv[2]
    sys.argv = [module, *sys.argv[3:]]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
