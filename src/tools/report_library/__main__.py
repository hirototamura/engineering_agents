"""Command entry point for the workspace report collection."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, help="workspace containing project folders; output goes to reports/")
    parser.add_argument("action", choices=["build", "serve", "translate", "capture", "verify"])
    args, remainder = parser.parse_known_args(argv)
    if args.workspace:
        os.environ["EA_REPORT_WORKSPACE"] = str(args.workspace.expanduser().resolve())
    if args.action in {"build", "serve"}:
        from . import catalog as command
        forwarded = [args.action, *remainder]
    elif args.action == "verify":
        from .verify_translations import verify
        if remainder:
            parser.error("verify takes no additional arguments")
        verify()
        return
    else:
        if args.action == "translate":
            from . import translate_reports as command
        else:
            from . import capture_thumbnails as command
        forwarded = remainder
    original = sys.argv
    try:
        sys.argv = [original[0], *forwarded]
        command.main()
    finally:
        sys.argv = original


if __name__ == "__main__":
    main()
