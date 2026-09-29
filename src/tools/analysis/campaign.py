"""The standard experiment battery behind the analysis report.

Each block answers one question and is sized so the whole battery runs in a few
minutes on a laptop-class machine (a ``plant_sim`` run costs about a second).

``seed_replicates``
    Is the plant stochastic? Everything downstream depends on the answer,
    because it decides whether uncertainty lives in replicates or in the design
    space. Run first, and reported whatever it says.
``response_surface``
    Full factorial over the two binding capacity axes. Supplies the phase
    diagram, the critical manifold and the susceptibility profile.
``one_at_a_time``
    Scale each actuation axis alone. Supplies the controllability vector that
    turns "the loop did not improve anything" into "the loop pushed on axes with
    zero gain".
``one_at_a_time_relieved``
    The same sweep from an operating point where the binding subsystem has been
    sized to its critical value. One-at-a-time sensitivity is local, and the
    difference between the two sweeps is the interaction between axes.
``crew_scaling``
    Hold the station and vary the load. An independent test of the coverage
    ratio: if ``rho`` is the right order parameter, sweeping the denominator
    must reproduce the curve obtained by sweeping the numerator.
``iso_ray``
    The numerator half of that same test: scale every capacity by a common
    factor along the ray the crew sweep traverses. Paired with ``crew_scaling``
    it is a falsification test of the coverage-ratio collapse.
``chains``
    The closed loop itself, at several lengths, for the design modes that run
    without an LLM provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from tools.analysis.artifacts import load_chain
from tools.analysis.experiments import (
    RunOutcome,
    RunSpec,
    chain_specs,
    collect_chain_rows,
    collect_rows,
    crew_scaling_specs,
    execute_all,
    iso_ray_specs,
    one_at_a_time_specs,
    response_surface_specs,
    save_rows,
    seed_replicate_specs,
)
from tools.analysis.loop_dynamics import analyse_chain

#: Nameplate ARS values. Dense below the transition, sparse in saturation.
ARS_GRID: Sequence[float] = (4.5, 8.0, 12.0, 16.0, 20.0, 26.0, 32.0, 40.0, 52.0, 65.0, 80.0)

#: Nameplate OGS values, chosen the same way (the transition sits near 36).
OGS_GRID: Sequence[float] = (9.25, 14.0, 18.0, 22.0, 26.0, 30.0, 34.0, 38.0, 42.0, 55.0, 80.0)

#: Multiplicative offsets for the one-at-a-time sweep. ``1.0`` is the shipped
#: value, and the upper end matches what six rule-designer iterations reach
#: (1.25 ** 6 = 3.8).
OAT_MULTIPLIERS: Sequence[float] = (0.5, 0.75, 1.0, 1.25, 1.5625, 1.953, 2.441, 3.052, 3.815, 6.0, 10.0)

CREW_SIZES: Sequence[int] = (4, 8, 12, 16, 20, 25, 30, 35, 40, 45, 50)

#: Common capacity factors matching :data:`CREW_SIZES` through ``50 / N``, so
#: the two sweeps land on the same coverage ratios from opposite directions.
ISO_RAY_SCALES: Sequence[float] = tuple(50.0 / size for size in CREW_SIZES)

#: Operating point for the second sensitivity sweep: OGS sized to the coverage
#: at which the crew first survives, so the other axes are no longer masked by
#: an O2 famine that kills everyone regardless.
RELIEVED_CAPACITY: Dict[str, float] = {"plant_sim.ogs.max_o2_kg_day": 42.0}

SEEDS: Sequence[int] = (1, 2, 3, 5, 8, 13)

CHAIN_LENGTHS: Sequence[int] = (3, 5, 8)


@dataclass
class CampaignResult:
    """Every dataset the report needs, already flattened into rows."""

    root: Path
    seed_rows: List[Dict]
    surface_rows: List[Dict]
    oat_rows: List[Dict]
    oat_relieved_rows: List[Dict]
    crew_rows: List[Dict]
    iso_ray_rows: List[Dict]
    chain_rows: List[Dict]
    chain_dynamics: List[Dict]
    failures: List[RunOutcome]

    def counts(self) -> Dict[str, int]:
        return {
            "seed_replicates": len(self.seed_rows),
            "response_surface": len(self.surface_rows),
            "one_at_a_time": len(self.oat_rows),
            "one_at_a_time_relieved": len(self.oat_relieved_rows),
            "crew_scaling": len(self.crew_rows),
            "iso_ray": len(self.iso_ray_rows),
            "chain_iterations": len(self.chain_rows),
            "failures": len(self.failures),
        }

    def total_runs(self) -> int:
        return sum(
            len(block) for block in (
                self.seed_rows, self.surface_rows, self.oat_rows,
                self.oat_relieved_rows, self.crew_rows, self.iso_ray_rows,
                self.chain_rows,
            )
        )

    def save(self) -> Dict[str, Path]:
        out = self.root / "datasets"
        blocks = {
            "seed_replicates": self.seed_rows,
            "response_surface": self.surface_rows,
            "one_at_a_time": self.oat_rows,
            "one_at_a_time_relieved": self.oat_relieved_rows,
            "crew_scaling": self.crew_rows,
            "iso_ray": self.iso_ray_rows,
            "chains": self.chain_rows,
        }
        written = {
            name: save_rows(rows, out / f"{name}.json") for name, rows in blocks.items()
        }
        if self.chain_dynamics:
            written["chain_dynamics"] = save_rows(
                self.chain_dynamics, out / "chain_dynamics.json"
            )
        return written


def build_specs(*, steps: int = 72, quick: bool = False) -> Dict[str, List[RunSpec]]:
    """All experiment specs, grouped by block.

    ``quick`` thins every grid to its endpoints and middle so the whole battery
    can be smoke-tested in well under a minute.
    """

    def thin(values: Sequence) -> Sequence:
        if not quick or len(values) <= 3:
            return values
        return (values[0], values[len(values) // 2], values[-1])

    return {
        "seed_replicates": seed_replicate_specs(thin(SEEDS), steps=steps),
        "response_surface": response_surface_specs(
            thin(ARS_GRID), thin(OGS_GRID), steps=steps
        ),
        "one_at_a_time": one_at_a_time_specs(thin(OAT_MULTIPLIERS), steps=steps),
        "one_at_a_time_relieved": one_at_a_time_specs(
            thin(OAT_MULTIPLIERS),
            steps=steps,
            base_capacity=RELIEVED_CAPACITY,
            operating_point="ogs_relieved",
        ),
        "crew_scaling": crew_scaling_specs(thin(CREW_SIZES), steps=steps),
        "iso_ray": iso_ray_specs(thin(ISO_RAY_SCALES), steps=steps),
        "chains": chain_specs(thin(CHAIN_LENGTHS), steps=steps),
    }


def run_campaign(
    root: Path | str,
    *,
    steps: int = 72,
    quick: bool = False,
    workers: int = 4,
    cache: bool = True,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> CampaignResult:
    """Execute the battery and return every dataset as flat rows."""

    root = Path(root)
    blocks = build_specs(steps=steps, quick=quick)
    collected: Dict[str, List[RunOutcome]] = {}
    failures: List[RunOutcome] = []

    for name, specs in blocks.items():
        def report(done: int, total: int, _outcome: RunOutcome, _name: str = name) -> None:
            if progress is not None:
                progress(_name, done, total)

        outcomes = execute_all(
            specs, root / name, cache=cache, workers=workers, progress=report
        )
        collected[name] = outcomes
        failures.extend(o for o in outcomes if not o.ok)

    chain_dynamics = []
    for outcome in collected["chains"]:
        if not outcome.ok:
            continue
        chain_dynamics.append(analyse_chain(load_chain(outcome.run_dir)).as_dict())

    return CampaignResult(
        root=root,
        seed_rows=collect_rows(collected["seed_replicates"]),
        surface_rows=collect_rows(collected["response_surface"]),
        oat_rows=collect_rows(collected["one_at_a_time"]),
        oat_relieved_rows=collect_rows(collected["one_at_a_time_relieved"]),
        crew_rows=collect_rows(collected["crew_scaling"]),
        iso_ray_rows=collect_rows(collected["iso_ray"]),
        chain_rows=collect_chain_rows(collected["chains"]),
        chain_dynamics=chain_dynamics,
        failures=failures,
    )


def chain_dirs(root: Path | str) -> List[Path]:
    """Chain directories produced by :func:`run_campaign`."""

    base = Path(root) / "chains"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "chain_summary.json").is_file())


__all__ = [
    "ARS_GRID",
    "CHAIN_LENGTHS",
    "CREW_SIZES",
    "CampaignResult",
    "ISO_RAY_SCALES",
    "OAT_MULTIPLIERS",
    "OGS_GRID",
    "RELIEVED_CAPACITY",
    "SEEDS",
    "build_specs",
    "chain_dirs",
    "run_campaign",
]
