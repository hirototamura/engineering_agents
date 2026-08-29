"""Read run and chain artifacts into flat records for analysis.

Everything here is read-only and tolerant: a run directory that predates a
field, or that was produced on the ``mock`` backend where the scorecard does not
apply, yields ``None`` for that field rather than raising. The analysis then
decides what it can compute.

Two conventions are inherited from the scorecard rather than reinvented, so an
analysis figure can never disagree with ``evaluation.json``:

* the canonical row for a step is the ``post_ops`` row when present, otherwise
  the last row (:func:`scenario.ssos_eclss_loop.evaluation.select_telemetry_rows`);
* a run whose crew never falls is *right censored* at the reference horizon, not
  a run with an infinite time to crew loss.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

import yaml

from scenario.ssos_eclss_loop.evaluation import select_telemetry_rows
from tools.analysis.design_space import (
    CAPACITY_AXES,
    CoverageRatios,
    actuation_vector,
    coverage_ratios,
    crew_demand,
    design_footprint,
    design_vector,
)

BAND_ORDER = ("safe", "warning", "critical", "unknown")


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    except OSError:
        return []
    return rows


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# --------------------------------------------------------------------------- #
# run record
# --------------------------------------------------------------------------- #
@dataclass
class RunRecord:
    """One simulation, reduced to the quantities the analysis needs."""

    run_dir: Path
    run_id: str
    summary: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    agents_config: Dict[str, Any] = field(default_factory=dict)
    proposals: Optional[Dict[str, Any]] = None

    # ---------------- identity ----------------
    @property
    def backend(self) -> Optional[str]:
        return self.summary.get("backend")

    @property
    def actor_mode(self) -> Optional[str]:
        return self.summary.get("actor_mode")

    @property
    def design_mode(self) -> Optional[str]:
        return self.summary.get("design_mode")

    @property
    def steps(self) -> Optional[int]:
        value = _finite(self.summary.get("steps"))
        return int(value) if value is not None else None

    @property
    def seed(self) -> Optional[int]:
        value = _finite(self.summary.get("seed"))
        return int(value) if value is not None else None

    @property
    def inject_failures(self) -> Optional[bool]:
        value = self.summary.get("inject_failures")
        return bool(value) if isinstance(value, bool) else None

    # ---------------- design ----------------
    @property
    def capacity(self) -> Dict[str, float]:
        from scenario.ssos_eclss_loop.design_variables import read_capacity_fields

        return dict(read_capacity_fields(self.config))

    @property
    def coverage(self) -> CoverageRatios:
        return coverage_ratios(self.config)

    @property
    def design_vector(self) -> Tuple[float, ...]:
        """Log-capacity coordinate only (the hardware the loop may resize)."""

        return design_vector(self.capacity)

    @property
    def actuation_vector(self) -> Dict[str, float]:
        """Log coordinate of every axis a designer may move, capacity included."""

        return actuation_vector(self.config, self.agents_config)

    @property
    def footprint(self) -> Dict[str, float]:
        return design_footprint(self.config)

    # ---------------- outcome ----------------
    @property
    def crew_initial(self) -> Optional[int]:
        value = _finite(self.summary.get("crew_initial"))
        return int(value) if value is not None else None

    @property
    def crew_remaining(self) -> Optional[int]:
        value = _finite(self.summary.get("crew_remaining"))
        return int(value) if value is not None else None

    @property
    def survival_fraction(self) -> Optional[float]:
        initial, remaining = self.crew_initial, self.crew_remaining
        if not initial or remaining is None:
            return None
        return remaining / initial

    @property
    def full_survival(self) -> Optional[bool]:
        fraction = self.survival_fraction
        return None if fraction is None else fraction >= 1.0

    @property
    def evaluation_score(self) -> Optional[float]:
        return _finite(self.summary.get("evaluation_score"))

    @property
    def evaluation_status(self) -> Optional[str]:
        return self.summary.get("evaluation_status")

    @property
    def physics_gate_passed(self) -> Optional[bool]:
        value = self.summary.get("physics_gate_passed")
        return bool(value) if isinstance(value, bool) else None

    @property
    def crew_lost_by_cause(self) -> Dict[str, int]:
        raw = self.summary.get("crew_lost_by_cause")
        if not isinstance(raw, Mapping):
            return {}
        return {str(k): int(v) for k, v in raw.items() if _finite(v) is not None}

    # ---------------- scorecard internals ----------------
    def axis(self, name: str) -> Dict[str, Any]:
        axes = (self.evaluation.get("scores") or {}).get("axes")
        if not isinstance(axes, Mapping):
            return {}
        block = axes.get(name)
        return dict(block) if isinstance(block, Mapping) else {}

    def axis_score(self, name: str) -> Optional[float]:
        return _finite(self.axis(name).get("score"))

    @property
    def mass_balance_residuals(self) -> Dict[str, float]:
        """Absolute ledger residuals from the physics gate, in kg / L."""

        gate = self.evaluation.get("physics_gate")
        if not isinstance(gate, Mapping):
            return {}
        for check in gate.get("checks") or []:
            if not isinstance(check, Mapping) or check.get("name") != "mass_balance_ledgers":
                continue
            residuals = check.get("residuals")
            if not isinstance(residuals, Mapping):
                return {}
            return {
                str(k): abs(v)
                for k, v in ((k, _finite(v)) for k, v in residuals.items())
                if v is not None
            }
        return {}

    @property
    def time_to_crew_loss(self) -> Tuple[Optional[float], bool]:
        """``(seconds, observed)``; censored runs return the reference horizon.

        ``observed`` is False when the crew never fell during the run, which the
        scorecard reports as ``right_censored``. Survival analysis needs that
        distinction; a summary statistic that drops those runs does not.
        """

        tcl = self.axis("tcl")
        metrics = tcl.get("metrics")
        metrics = metrics if isinstance(metrics, Mapping) else {}
        observed = bool(metrics.get("event_observed"))
        if observed:
            return _finite(metrics.get("tcl_seconds")), True
        horizon = _finite(metrics.get("survived_through_seconds"))
        if horizon is None:
            horizon = _finite(metrics.get("reference_seconds"))
        return horizon, False

    @property
    def severity_auc_seconds(self) -> Optional[float]:
        metrics = self.axis("environment_trajectory").get("metrics")
        if not isinstance(metrics, Mapping):
            return None
        return _finite(metrics.get("severity_auc_seconds"))

    @property
    def mean_normalized_severity(self) -> Optional[float]:
        metrics = self.axis("environment_trajectory").get("metrics")
        if not isinstance(metrics, Mapping):
            return None
        return _finite(metrics.get("mean_normalized_severity"))

    # ---------------- streams ----------------
    def telemetry(self) -> List[Dict[str, Any]]:
        """Canonical one-row-per-step telemetry, per the scorecard's rule."""

        canonical, _ = select_telemetry_rows(_read_jsonl(self.run_dir / "telemetry.jsonl"))
        return canonical

    def health(self) -> List[Dict[str, Any]]:
        rows = _read_jsonl(self.run_dir / "health_metrics.jsonl")
        by_step: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            step = row.get("step")
            if isinstance(step, bool) or not isinstance(step, int):
                continue
            if row.get("post_ops") is True or step not in by_step:
                by_step[step] = row
        return [by_step[step] for step in sorted(by_step)]

    def band_steps(self) -> Dict[str, int]:
        counts = {band: 0 for band in BAND_ORDER}
        for row in self.health():
            band = str(row.get("overall", "unknown"))
            counts[band] = counts.get(band, 0) + 1
        return counts

    def events(self) -> List[Dict[str, Any]]:
        return _read_jsonl(self.run_dir / "events.jsonl")

    def limiter_rates(self) -> Dict[str, float]:
        """Fraction of applied operations clipped by *installed capacity*.

        The plant names its limiter explicitly in ``details.limited_by``, and
        that is the field to read. ``fully_satisfied`` alone is not enough: an
        operation can fall short because the nameplate is too small (which more
        hardware fixes) or because the feedstock is not there yet (which it does
        not), and only ``limited_by`` distinguishes them.

        Keys are ``"<command>.<reason>"``, plus ``"<command>.any"`` for the
        share short of the request for any reason.
        """

        totals: Dict[str, int] = {}
        by_reason: Dict[str, int] = {}
        for event in self.events():
            if event.get("kind") != "/eclss/events/operational_applied":
                continue
            command = event.get("command")
            result = event.get("result")
            if not isinstance(command, Mapping) or not isinstance(result, Mapping):
                continue
            details = result.get("details")
            if not isinstance(details, Mapping) or "fully_satisfied" not in details:
                continue
            kind = str(command.get("kind"))
            totals[kind] = totals.get(kind, 0) + 1
            if details.get("fully_satisfied") is False:
                by_reason[f"{kind}.any"] = by_reason.get(f"{kind}.any", 0) + 1
            reasons = details.get("limited_by")
            for reason in reasons if isinstance(reasons, list) else []:
                key = f"{kind}.{reason}"
                by_reason[key] = by_reason.get(key, 0) + 1

        rates: Dict[str, float] = {}
        for key, count in by_reason.items():
            kind = key.split(".", 1)[0]
            total = totals.get(kind, 0)
            if total:
                rates[key] = count / total
        return rates

    # ---------------- proposals ----------------
    def proposal_changes(self) -> List[Dict[str, Any]]:
        doc = self.proposals or {}
        changes = doc.get("changes")
        return [dict(c) for c in changes if isinstance(c, Mapping)] if isinstance(changes, list) else []

    def change_kinds(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for change in self.proposal_changes():
            kind = str(change.get("change_kind", "unknown"))
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    # ---------------- flat row ----------------
    def as_row(self) -> Dict[str, Any]:
        coverage = self.coverage
        tcl_seconds, tcl_observed = self.time_to_crew_loss
        row: Dict[str, Any] = {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "backend": self.backend,
            "actor_mode": self.actor_mode,
            "design_mode": self.design_mode,
            "steps": self.steps,
            "seed": self.seed,
            "inject_failures": self.inject_failures,
            "crew_initial": self.crew_initial,
            "crew_remaining": self.crew_remaining,
            "survival_fraction": self.survival_fraction,
            "full_survival": self.full_survival,
            "evaluation_score": self.evaluation_score,
            "evaluation_status": self.evaluation_status,
            "physics_gate_passed": self.physics_gate_passed,
            "rho_ars": coverage.ars,
            "rho_ogs": coverage.ogs,
            "rho_wrs": coverage.wrs,
            "rho_min": coverage.minimum,
            "binding_subsystem": coverage.binding_subsystem,
            "tcl_seconds": tcl_seconds,
            "tcl_observed": tcl_observed,
            "severity_auc_seconds": self.severity_auc_seconds,
            "mean_normalized_severity": self.mean_normalized_severity,
            "proposal_count": len(self.proposal_changes()),
        }
        row.update({f"capacity_{axis.split('.')[1]}": self.capacity[axis] for axis in CAPACITY_AXES})
        row.update(self.footprint)
        row.update({f"band_{band}": count for band, count in self.band_steps().items()})
        row.update({f"lost_{cause}": count for cause, count in self.crew_lost_by_cause.items()})
        row.update({f"axis_{name}": self.axis_score(name) for name in (
            "actor_survival", "tcl", "environment_trajectory",
            "resource_recovery", "actor_decision", "physical_response",
        )})
        row.update({f"residual_{k}": v for k, v in self.mass_balance_residuals.items()})
        row.update({f"limited_{k}": v for k, v in self.limiter_rates().items()})
        demand = crew_demand(self.config)
        row.update({f"demand_{k}": v for k, v in demand.as_dict().items()})
        return row


def load_run(run_dir: Path | str) -> RunRecord:
    """Read one run directory. Missing artifacts leave the field empty."""

    path = Path(run_dir)
    return RunRecord(
        run_dir=path,
        run_id=path.name,
        summary=_read_json(path / "summary.json") or {},
        evaluation=_read_json(path / "evaluation.json") or {},
        config=_read_yaml(path / "scenario_config.yaml"),
        agents_config=_read_yaml(path / "agents_config.yaml"),
        proposals=_read_json(path / "design_proposals.json"),
    )


def is_run_dir(path: Path) -> bool:
    return (path / "summary.json").is_file() and (path / "telemetry.jsonl").is_file()


# --------------------------------------------------------------------------- #
# chain record
# --------------------------------------------------------------------------- #
@dataclass
class ChainRecord:
    """One ``--iterate`` campaign: the ordered iterations plus its replays."""

    chain_dir: Path
    chain_id: str
    chain_summary: Dict[str, Any] = field(default_factory=dict)
    iterations: List[RunRecord] = field(default_factory=list)
    replays: Dict[str, RunRecord] = field(default_factory=dict)

    @property
    def verdict(self) -> Optional[str]:
        return self.chain_summary.get("verdict")

    @property
    def requirements_hash(self) -> Optional[str]:
        return self.chain_summary.get("requirements_hash")

    def applied_changes(self, iteration_index: int) -> List[Dict[str, Any]]:
        """Changes actually merged into the *next* simulation.

        ``applied_proposals.json`` is the filtered document: the chain strips
        every ``set_parameter`` entry to keep the verification requirements
        frozen, so a proposal counted here is one that could move the plant.
        """

        if not 0 <= iteration_index < len(self.iterations):
            return []
        doc = _read_json(self.iterations[iteration_index].run_dir / "applied_proposals.json")
        if not isinstance(doc, Mapping):
            return []
        changes = doc.get("changes")
        return [dict(c) for c in changes if isinstance(c, Mapping)] if isinstance(changes, list) else []

    def as_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for index, run in enumerate(self.iterations):
            row = run.as_row()
            row.update({
                "chain_id": self.chain_id,
                "iteration": index + 1,
                "chain_verdict": self.verdict,
                "applied_change_count": len(self.applied_changes(index)),
            })
            rows.append(row)
        return rows


def load_chain(chain_dir: Path | str) -> ChainRecord:
    """Read an ``--iterate`` directory: numbered iterations plus replays."""

    path = Path(chain_dir)
    iterations: List[Tuple[int, RunRecord]] = []
    replays: Dict[str, RunRecord] = {}
    for child in sorted(path.iterdir()) if path.is_dir() else []:
        if not child.is_dir() or not is_run_dir(child):
            continue
        if child.name.isdigit():
            iterations.append((int(child.name), load_run(child)))
        else:
            replays[child.name] = load_run(child)
    iterations.sort(key=lambda item: item[0])
    return ChainRecord(
        chain_dir=path,
        chain_id=path.name,
        chain_summary=_read_json(path / "chain_summary.json") or {},
        iterations=[run for _, run in iterations],
        replays=replays,
    )


def is_chain_dir(path: Path) -> bool:
    return (path / "chain_summary.json").is_file()


def discover(results_root: Path | str) -> Iterator[Path]:
    """Yield every run or chain directory directly under ``results_root``."""

    root = Path(results_root)
    if not root.is_dir():
        return
    for child in sorted(root.iterdir()):
        if child.is_dir() and (is_chain_dir(child) or is_run_dir(child)):
            yield child


def rows_from_runs(runs: Sequence[RunRecord]) -> List[Dict[str, Any]]:
    return [run.as_row() for run in runs]


__all__ = [
    "BAND_ORDER",
    "ChainRecord",
    "RunRecord",
    "discover",
    "is_chain_dir",
    "is_run_dir",
    "load_chain",
    "load_run",
    "rows_from_runs",
]
