"""Command line entry point for the design-loop analysis.

    python3 -m tools.analysis run      # execute the experiment battery
    python3 -m tools.analysis report   # analyse the datasets and write the HTML
    python3 -m tools.analysis all      # both, in order

``run`` caches by run directory, so re-running it after an interrupted campaign
resumes rather than restarting, and ``report`` can be re-run as often as needed
without touching the simulator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_ROOT = Path("src/experiments/analysis")
DEFAULT_REPORT = DEFAULT_ROOT / "design_loop_analysis.html"


def _scenario_config() -> Dict[str, Any]:
    """The shipped scenario config, for budgets and sizing constants."""

    import yaml

    from scenario.runner import scenario_config_path

    path = Path(scenario_config_path("ssos_eclss_loop"))
    if not path.is_file():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def cmd_run(args: argparse.Namespace) -> int:
    from tools.analysis.campaign import run_campaign

    seen: Dict[str, int] = {}

    def progress(block: str, done: int, total: int) -> None:
        if seen.get(block) == done:
            return
        seen[block] = done
        if done == total or done == 1 or done % 20 == 0:
            print(f"  {block}: {done}/{total}", file=sys.stderr, flush=True)

    print(f"running experiment battery into {args.root}", file=sys.stderr)
    result = run_campaign(
        args.root,
        steps=args.steps,
        quick=args.quick,
        workers=args.workers,
        cache=not args.no_cache,
        progress=progress,
    )
    for name, path in result.save().items():
        print(f"  wrote {name}: {path}", file=sys.stderr)
    print(json.dumps(result.counts(), indent=2))
    for failure in result.failures[:10]:
        print(f"FAILED {failure.spec.run_id}: {failure.stderr[-300:]}", file=sys.stderr)
    return 1 if result.failures else 0


def cmd_report(args: argparse.Namespace) -> int:
    from tools.analysis.report import build

    findings, document = build(
        args.root,
        config=_scenario_config(),
        title=args.title,
        subtitle=args.subtitle,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")

    findings_path = out.with_suffix(".findings.json")
    serialisable = {k: v for k, v in findings.items() if not k.startswith("_")}
    findings_path.write_text(json.dumps(serialisable, indent=2, default=str), encoding="utf-8")

    print(f"report:   {out}", file=sys.stderr)
    print(f"findings: {findings_path}", file=sys.stderr)
    surface = findings.get("surface", {})
    loop = findings.get("loop", {})
    print(json.dumps({
        "runs_analysed": sum(findings.get("dataset_sizes", {}).values()),
        "designs_with_full_survival": surface.get("n_full_survival"),
        "of_those_within_budget": surface.get("n_full_survival_within_budget"),
        "zero_gain_axes": findings.get("controllability", {}).get("zero_gain_axes"),
        "archetypes": loop.get("archetypes"),
    }, indent=2))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    code = cmd_run(args)
    if code and not args.keep_going:
        return code
    return cmd_report(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.analysis",
        description="Academic analysis of the ECLSS design->verify loop.",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="directory holding runs and datasets")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute the experiment battery")
    report = sub.add_parser("report", help="analyse datasets and write the HTML report")
    every = sub.add_parser("all", help="run the battery then write the report")

    for p in (run, every):
        p.add_argument("--steps", type=int, default=72, help="simulation steps per run")
        p.add_argument("--quick", action="store_true",
                       help="thin every grid to three points (smoke test)")
        p.add_argument("--workers", type=int, default=4, help="parallel simulations")
        p.add_argument("--no-cache", action="store_true",
                       help="re-simulate points that already have results")
    for p in (report, every):
        p.add_argument("--out", type=Path, default=DEFAULT_REPORT, help="HTML output path")
        p.add_argument("--title", default="Physics of a design agent")
        p.add_argument("--subtitle",
                       default="Order parameters, criticality and controllability of the "
                               "ECLSS design-verify loop")
    every.add_argument("--keep-going", action="store_true",
                       help="write the report even if some simulations failed")

    run.set_defaults(func=cmd_run)
    report.set_defaults(func=cmd_report)
    every.set_defaults(func=cmd_all)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
