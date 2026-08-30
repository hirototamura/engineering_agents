"""Batch harness that drives ``tools.cli`` to build analysis datasets.

Every experiment here is a set of simulations that differ in a controlled way,
executed through the documented CLI rather than by calling the scenario in
process. Going through the CLI costs a subprocess per run (~1 s) and buys the
guarantee that the analysed runs are the same runs a reader reproduces from the
command line.

A design is imposed on a single run by writing a one-change ``capacity_profile``
proposal document and passing it to ``--apply-proposals``. That is the same
path the tool-use designer uses to adopt a candidate, so the experiment grid and
the agent's own proposals move through identical code. ``--iterate`` chains
cannot take ``--apply-proposals`` (the CLI rejects the combination), so a
starting capacity on a chain is baked in as ``--set`` overrides instead.

Results are cached by run directory: an experiment re-run skips any point whose
``summary.json`` already exists, so a report can be regenerated without
recomputing the grid.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from tools.analysis.artifacts import RunRecord, load_chain, load_run
from tools.analysis.design_space import CAPACITY_AXES

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STEPS = 72
DEFAULT_SCENARIO = "ssos_eclss_loop"


@dataclass(frozen=True)
class RunSpec:
    """One simulation to execute."""

    run_id: str
    capacity: Optional[Dict[str, float]] = None
    overrides: Dict[str, str] = field(default_factory=dict)
    steps: int = DEFAULT_STEPS
    seed: int = 1
    backend: str = "plant_sim"
    actor_mode: str = "labeled_rule_base"
    design_mode: str = "none"
    inject_failures: Optional[bool] = None
    iterate: Optional[int] = None
    labels: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunOutcome:
    spec: RunSpec
    run_dir: Path
    returncode: int
    cached: bool
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def capacity_proposal(capacity: Mapping[str, float], *, note: str = "experiment grid") -> Dict[str, Any]:
    """A minimal, schema-valid ``capacity_profile`` proposal document."""

    unknown = [key for key in capacity if key not in CAPACITY_AXES]
    if unknown:
        raise ValueError(f"not design variables: {', '.join(sorted(unknown))}")
    return {
        "design_domain": "ssos_graph",
        "proposed_by": "tools.analysis.experiments",
        "decision_source": "rule",
        "message": note,
        "changes": [
            {
                "change_kind": "capacity_profile",
                "payload": {
                    "backend": "plant_sim",
                    "fields": {key: float(value) for key, value in capacity.items()},
                },
                "why": "sweep the design space to map the response surface",
                "what": "set installed subsystem capacity",
                "how": ", ".join(f"{k}={v:g}" for k, v in sorted(capacity.items())),
            }
        ],
    }


def capacity_set_flags(capacity: Mapping[str, float]) -> List[str]:
    """``--set`` flags that bake starting capacity without ``--apply-proposals``.

    Used by ``--iterate`` chains: the CLI rejects combining a chain with a
    proposal file, but the same nameplate numbers can land in the first
    iteration's config as ordinary overrides.
    """

    unknown = [key for key in capacity if key not in CAPACITY_AXES]
    if unknown:
        raise ValueError(f"not design variables: {', '.join(sorted(unknown))}")
    flags: List[str] = []
    for key in CAPACITY_AXES:
        if key in capacity:
            flags += ["--set", f"{key}={float(capacity[key])}"]
    return flags


def _command(spec: RunSpec, run_dir: Path, proposal_path: Optional[Path]) -> List[str]:
    cmd = [
        sys.executable, "-m", "tools.cli", "run", DEFAULT_SCENARIO,
        "--backend", spec.backend,
        "--actor-mode", spec.actor_mode,
        "--design-mode", spec.design_mode,
        "--steps", str(spec.steps),
        "--seed", str(spec.seed),
        "--quiet",
    ]
    if spec.iterate:
        cmd += ["--iterate", str(spec.iterate), "--run-id", run_dir.name,
                "--results-root", str(run_dir.parent)]
        if spec.capacity:
            cmd += capacity_set_flags(spec.capacity)
    else:
        cmd += ["--set", "iteration.enabled=false", "--output-dir", str(run_dir)]
        if proposal_path is not None:
            cmd += ["--apply-proposals", str(proposal_path)]
    if spec.inject_failures is not None:
        cmd.append("--inject-failures" if spec.inject_failures else "--no-inject-failures")
    for key, value in sorted(spec.overrides.items()):
        cmd += ["--set", f"{key}={value}"]
    return cmd


def execute(
    spec: RunSpec,
    root: Path,
    *,
    cache: bool = True,
    timeout_s: float = 600.0,
) -> RunOutcome:
    """Run one simulation into ``root / spec.run_id``."""

    run_dir = Path(root) / spec.run_id
    marker = run_dir / ("chain_summary.json" if spec.iterate else "summary.json")
    if cache and marker.is_file():
        return RunOutcome(spec, run_dir, 0, cached=True)

    proposal_path: Optional[Path] = None
    if spec.capacity and not spec.iterate:
        proposal_dir = Path(root) / "_proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = proposal_dir / f"{spec.run_id}.json"
        proposal_path.write_text(json.dumps(capacity_proposal(spec.capacity), indent=2))

    run_dir.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("MPLBACKEND", "Agg")
    try:
        result = subprocess.run(
            _command(spec, run_dir, proposal_path),
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return RunOutcome(spec, run_dir, 124, cached=False, stderr="timeout")
    return RunOutcome(spec, run_dir, result.returncode, cached=False, stderr=result.stderr[-2000:])


def execute_all(
    specs: Sequence[RunSpec],
    root: Path,
    *,
    cache: bool = True,
    workers: int = 4,
    progress: Optional[Callable[[int, int, RunOutcome], None]] = None,
) -> List[RunOutcome]:
    """Execute a batch, in parallel. Order of the returned list matches ``specs``."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    outcomes: List[Optional[RunOutcome]] = [None] * len(specs)
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(execute, spec, root, cache=cache): index
            for index, spec in enumerate(specs)
        }
        for future in as_completed(futures):
            index = futures[future]
            outcome = future.result()
            outcomes[index] = outcome
            done += 1
            if progress is not None:
                progress(done, len(specs), outcome)
    return [o for o in outcomes if o is not None]


# --------------------------------------------------------------------------- #
# experiment builders
# --------------------------------------------------------------------------- #
def response_surface_specs(
    ars_values: Sequence[float],
    ogs_values: Sequence[float],
    *,
    wrs: float = 10.0,
    prefix: str = "grid",
    steps: int = DEFAULT_STEPS,
    seed: int = 1,
    inject_failures: bool = False,
) -> List[RunSpec]:
    """Full factorial over the two binding capacity axes.

    WRS is held fixed: its baseline coverage already exceeds one, so it is not
    a bottleneck and varying it would spend the budget on a flat direction.
    :func:`one_at_a_time_specs` still checks that claim.
    """

    specs: List[RunSpec] = []
    for i, ars in enumerate(ars_values):
        for j, ogs in enumerate(ogs_values):
            specs.append(
                RunSpec(
                    run_id=f"{prefix}-a{i:02d}-o{j:02d}",
                    capacity={
                        "plant_sim.ars.capacity_kg_day": float(ars),
                        "plant_sim.ogs.max_o2_kg_day": float(ogs),
                        "plant_sim.wrs.max_feed_l_per_operation": float(wrs),
                    },
                    steps=steps,
                    seed=seed,
                    inject_failures=inject_failures,
                    labels={"experiment": "response_surface", "ars": float(ars),
                            "ogs": float(ogs), "wrs": float(wrs)},
                )
            )
    return specs


#: Actuation axes available to a designer, grouped by the subspace they live in.
#: ``capacity`` resizes installed hardware; ``action`` changes the payload the
#: crew sends to hardware it already has; ``policy`` moves the band edges that
#: decide when the crew acts at all.
OAT_AXES: Dict[str, Tuple[str, str, float]] = {
    # name: (subspace, cli override key or capacity axis, baseline value)
    "ars_capacity_kg_day": ("capacity", "plant_sim.ars.capacity_kg_day", 4.5),
    "ogs_max_o2_kg_day": ("capacity", "plant_sim.ogs.max_o2_kg_day", 9.25),
    "wrs_max_feed_l": ("capacity", "plant_sim.wrs.max_feed_l_per_operation", 10.0),
    "ars_action_co2_mass": ("action", "agents.actor.policy.ars_goal.initial_co2_mass", 4.5),
    "ogs_action_water_mass": ("action", "agents.actor.policy.ogs_goal.input_water_mass", 0.15),
    "request_co2_amount": ("action", "agents.actor.policy.request_co2_amount", 0.025),
    "co2_threshold_high": ("policy", "thresholds.co2_storage_high_kg", 2.0),
    "o2_threshold_low": ("policy", "thresholds.o2_storage_low_kg", 6.0),
}


def one_at_a_time_specs(
    multipliers: Sequence[float],
    *,
    prefix: str = "oat",
    steps: int = DEFAULT_STEPS,
    seed: int = 1,
    inject_failures: bool = False,
    axes: Optional[Mapping[str, Tuple[str, str, float]]] = None,
    base_capacity: Optional[Mapping[str, float]] = None,
    operating_point: str = "shipped",
) -> List[RunSpec]:
    """Scale one actuation axis at a time away from an operating point.

    This measures *controllability*: how much the outcome moves per unit of
    movement on each axis. Combined with what a designer actually proposes it
    decides whether that designer can steer the system at all.

    One-at-a-time sensitivity is local by construction. When one subsystem is
    starved the whole crew dies regardless of the others, so every other axis
    measures zero gain at that point and the sweep understates what those axes
    could do elsewhere. ``base_capacity`` re-runs the sweep from a relieved
    point; comparing the two separates "this axis does nothing" from "this axis
    does nothing *here*".
    """

    table = dict(axes or OAT_AXES)
    base = dict(base_capacity or {})
    specs: List[RunSpec] = []
    for name, (subspace, key, baseline) in sorted(table.items()):
        for index, mult in enumerate(multipliers):
            value = float(baseline) * float(mult)
            capacity = dict(base)
            overrides: Dict[str, str] = {}
            if subspace == "capacity":
                capacity[key] = value
            else:
                overrides[key] = f"{value:g}"
            specs.append(
                RunSpec(
                    run_id=f"{prefix}-{name}-{index:02d}",
                    capacity=capacity or None,
                    overrides=overrides,
                    steps=steps,
                    seed=seed,
                    inject_failures=inject_failures,
                    labels={
                        "experiment": "one_at_a_time",
                        "axis": name,
                        "subspace": subspace,
                        "multiplier": float(mult),
                        "value": value,
                        "operating_point": operating_point,
                    },
                )
            )
    return specs


def iso_ray_specs(
    scales: Sequence[float],
    *,
    prefix: str = "ray",
    steps: int = DEFAULT_STEPS,
    seed: int = 1,
    inject_failures: bool = False,
    baseline: Optional[Mapping[str, float]] = None,
) -> List[RunSpec]:
    """Scale every capacity axis by a common factor.

    Crew demand is linear in crew size, so holding the station fixed and
    shrinking the crew by ``1/lambda`` multiplies every coverage ratio by
    ``lambda`` -- exactly what multiplying every capacity by ``lambda`` does.
    The two manipulations are physically unrelated (one adds hardware, the other
    removes people) and the coverage-ratio model says they must produce the same
    curve. Running both is a falsification test, not a fit.
    """

    base = dict(baseline or {
        "plant_sim.ars.capacity_kg_day": 4.5,
        "plant_sim.ogs.max_o2_kg_day": 9.25,
        "plant_sim.wrs.max_feed_l_per_operation": 10.0,
    })
    specs = []
    for index, scale in enumerate(scales):
        specs.append(
            RunSpec(
                run_id=f"{prefix}-{index:02d}",
                capacity={key: float(value) * float(scale) for key, value in base.items()},
                steps=steps,
                seed=seed,
                inject_failures=inject_failures,
                labels={"experiment": "iso_ray", "scale": float(scale)},
            )
        )
    return specs


def crew_scaling_specs(
    crew_sizes: Sequence[int],
    *,
    capacity: Optional[Mapping[str, float]] = None,
    prefix: str = "crew",
    steps: int = DEFAULT_STEPS,
    seed: int = 1,
    inject_failures: bool = False,
) -> List[RunSpec]:
    """Hold the station fixed and vary the load it must service.

    Demand is linear in crew size, so this traverses the same ``rho`` axis as
    the capacity sweep from the opposite direction. Agreement between the two is
    a falsifiable prediction of the coverage-ratio model, not a fit.
    """

    specs = []
    for size in crew_sizes:
        specs.append(
            RunSpec(
                run_id=f"{prefix}-{int(size):03d}",
                capacity=dict(capacity) if capacity else None,
                overrides={"plant_sim.crew.size": str(int(size)),
                           "agents.actor.team.count": str(int(size))},
                steps=steps,
                seed=seed,
                inject_failures=inject_failures,
                labels={"experiment": "crew_scaling", "crew_size": int(size)},
            )
        )
    return specs


def seed_replicate_specs(
    seeds: Sequence[int],
    *,
    capacity: Optional[Mapping[str, float]] = None,
    prefix: str = "seed",
    steps: int = DEFAULT_STEPS,
    inject_failures: bool = False,
) -> List[RunSpec]:
    """Identical configuration under different seeds, to test determinism."""

    return [
        RunSpec(
            run_id=f"{prefix}-{int(seed):03d}",
            capacity=dict(capacity) if capacity else None,
            steps=steps,
            seed=int(seed),
            inject_failures=inject_failures,
            labels={"experiment": "seed_replicates", "seed": int(seed)},
        )
        for seed in seeds
    ]


def chain_specs(
    lengths: Sequence[int],
    *,
    design_mode: str = "labeled_rule_base",
    prefix: str = "chain",
    steps: int = DEFAULT_STEPS,
    seed: int = 1,
    start_capacity: Optional[Mapping[str, float]] = None,
) -> List[RunSpec]:
    """``--iterate`` campaigns: the closed loop actually running."""

    return [
        RunSpec(
            run_id=f"{prefix}-{design_mode}-n{int(n):02d}",
            capacity=dict(start_capacity) if start_capacity else None,
            steps=steps,
            seed=seed,
            design_mode=design_mode,
            iterate=int(n),
            labels={"experiment": "chain", "length": int(n), "design_mode": design_mode},
        )
        for n in lengths
    ]


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #
def collect_rows(
    outcomes: Iterable[RunOutcome],
) -> List[Dict[str, Any]]:
    """Flat rows for every successful non-chain run, with its spec labels."""

    rows: List[Dict[str, Any]] = []
    for outcome in outcomes:
        if not outcome.ok or outcome.spec.iterate:
            continue
        record = load_run(outcome.run_dir)
        if not record.summary:
            continue
        row = record.as_row()
        row.update(outcome.spec.labels)
        rows.append(row)
    return rows


def collect_chain_rows(outcomes: Iterable[RunOutcome]) -> List[Dict[str, Any]]:
    """Per-iteration rows for every successful chain."""

    rows: List[Dict[str, Any]] = []
    for outcome in outcomes:
        if not outcome.ok or not outcome.spec.iterate:
            continue
        chain = load_chain(outcome.run_dir)
        for row in chain.as_rows():
            row.update(outcome.spec.labels)
            rows.append(row)
    return rows


def seed_replicates(rows: Sequence[Mapping[str, Any]], key: str = "evaluation_score") -> Dict[str, Any]:
    """Spread of ``key`` across seed replicates -- the determinism check."""

    values = [row.get(key) for row in rows if isinstance(row.get(key), (int, float))]
    if not values:
        return {"n": 0, "deterministic": None}
    spread = max(values) - min(values)
    return {
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "spread": spread,
        "deterministic": spread == 0.0,
    }


def load_rows(path: Path | str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data) if isinstance(data, list) else list(data.get("rows", []))


def save_rows(rows: Sequence[Mapping[str, Any]], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(list(rows), indent=1, default=str), encoding="utf-8")
    return out


__all__ = [
    "OAT_AXES",
    "RunOutcome",
    "RunSpec",
    "capacity_proposal",
    "capacity_set_flags",
    "chain_specs",
    "collect_chain_rows",
    "collect_rows",
    "crew_scaling_specs",
    "execute",
    "execute_all",
    "iso_ray_specs",
    "load_rows",
    "one_at_a_time_specs",
    "response_surface_specs",
    "save_rows",
    "seed_replicate_specs",
    "seed_replicates",
]
