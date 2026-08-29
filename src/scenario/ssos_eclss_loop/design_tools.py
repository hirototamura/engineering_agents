"""Deterministic tools the ECLSS design agent calls (design doc §5.2).

The point of the redesign is that the LLM is *not* handed a pre-digested
summary. It gets a tool catalog and has to fetch what it needs: run artifacts,
time series, features, theoretical sizing, constraint labels, candidate
re-simulations, comparisons. Everything numeric happens here, deterministically,
so a small model cannot hallucinate the arithmetic that decides the design.

Every tool returns a JSON-serialisable dict and never raises: failures come back
as ``{"error": ...}`` so the loop can show the model what went wrong and let it
recover. Results are deliberately compact — they are re-injected into a prompt
with a limited context window.
"""

from __future__ import annotations

import copy
import json
import math
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from environment.ssos.eclss.plant_sim.stoichiometry import WATER_PER_O2
from scenario.ssos_eclss_loop.design_constraints import DesignConstraints
from scenario.ssos_eclss_loop.design_eval import (
    band_counts,
    evaluate_run_outcome,
    mark_final_eligibility,
    rank_candidates,
    rank_rationale,
    select_final_candidate,
)
from scenario.ssos_eclss_loop.design_variables import (
    CAPACITY_KEYS,
    apply_capacity_fields,
    expected_urine_l_per_step,
    read_capacity_fields,
    required_ogs_input_water_mass,
    required_wrs_urine_volume,
    sync_action_payloads,
    validate_capacity_fields,
)

SECONDS_PER_DAY = 86400.0

ARTIFACT_FILES = {
    "summary": "summary.json",
    "scenario_config": "scenario_config.yaml",
    "agents_config": "agents_config.yaml",
    "telemetry": "telemetry.jsonl",
    "health_metrics": "health_metrics.jsonl",
    "events": "events.jsonl",
    "messages": "messages.jsonl",
    "design_state": "design_state.jsonl",
}

TIMESERIES_SOURCES = ("telemetry", "health_metrics")

DEFAULT_TIMESERIES_COLUMNS = (
    "co2_storage_kg",
    "o2_storage_kg",
    "product_water_reserve_l",
    "plant_sim.crew_alive",
)


def _read_jsonl(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _column(row: Mapping[str, Any], name: str) -> Any:
    """Read a plain or dotted column (``plant_sim.urine_buffer_l``)."""
    if name in row:
        return row[name]
    if "." not in name:
        return None
    head, _, tail = name.partition(".")
    topics = row.get("raw_topics")
    if isinstance(topics, Mapping):
        block = topics.get(head)
        if isinstance(block, Mapping):
            return _column(block, tail) if "." in tail else block.get(tail)
    block = row.get(head)
    if isinstance(block, Mapping):
        return _column(block, tail) if "." in tail else block.get(tail)
    return None


def _numeric_series(
    rows: Sequence[Mapping[str, Any]],
    name: str,
    *,
    skip_post_ops: bool = True,
) -> List[Tuple[int, float]]:
    series: List[Tuple[int, float]] = []
    for row in rows:
        if skip_post_ops and row.get("post_ops"):
            continue
        value = _column(row, name)
        if value is None:
            continue
        try:
            # Failure flags are booleans; plot / summarise them as 0 and 1.
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        step = row.get("step")
        series.append((int(step) if isinstance(step, int) else len(series), number))
    return series


def _name_list(value: Any, *, argument: str) -> Optional[List[str]]:
    """Normalise a "list of names" argument coming from model-written JSON.

    A model that means one column often writes the bare string, and ``list("co2")``
    would silently become three one-character column names. A single string is
    therefore read as a one-element list; anything that is not a string or a
    sequence of them is an error the model can see and correct. ``None`` means
    "not given" so the caller can apply its own default.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else None
    if isinstance(value, (list, tuple)):
        names = [str(item).strip() for item in value]
        names = [name for name in names if name]
        return names or None
    raise ValueError(
        f"{argument} must be a list of names or a single name, "
        f"got {type(value).__name__}"
    )


def _round(value: Any, digits: int = 4) -> Any:
    if isinstance(value, float) and math.isfinite(value):
        return round(value, digits)
    return value


def _bound_note(need: float, clamped: float) -> str:
    """Say so when the engineering bounds, not demand, decided the size."""
    if abs(need - clamped) <= 1e-9:
        return ""
    direction = "raised to the smallest" if clamped > need else "capped at the largest"
    return f", {direction} buildable machine ({round(clamped, 3)})"


@dataclass
class ToolSpec:
    name: str
    description: str
    arguments: Dict[str, str]
    evidence: Optional[str] = None


@dataclass
class DesignToolContext:
    """Everything the tools may read about the baseline run."""

    run_dir: Path
    scenario_config: Dict[str, Any]
    summary: Dict[str, Any]
    agents_config: Optional[Dict[str, Any]] = None
    constraints: DesignConstraints = field(default_factory=DesignConstraints)
    max_candidate_runs: int = 4
    candidate_actor_mode: str = "inherit"
    candidate_steps: Optional[int] = None
    plots_enabled: bool = True


class DesignToolkit:
    """Tool registry + evidence ledger for the tool-use design agent."""

    def __init__(self, ctx: DesignToolContext):
        self.ctx = ctx
        self.run_dir = Path(ctx.run_dir)
        self.constraints = ctx.constraints
        self.evidence: Dict[str, bool] = {}
        self.candidates: List[Dict[str, Any]] = []
        self.baseline_outcome: Dict[str, Any] = evaluate_run_outcome(self.run_dir)
        self._plot_paths: List[str] = []
        self._specs: Dict[str, ToolSpec] = {spec.name: spec for spec in self._build_specs()}
        self._handlers: Dict[str, Callable[..., Dict[str, Any]]] = {
            "load_run_artifacts": self.load_run_artifacts,
            "summarize_timeseries": self.summarize_timeseries,
            "compute_eclss_features": self.compute_eclss_features,
            "compute_theoretical_capacity": self.compute_theoretical_capacity,
            "plot_eclss_timeseries": self.plot_eclss_timeseries,
            "propose_capacity_candidate": self.propose_capacity_candidate,
            "evaluate_design_constraints": self.evaluate_design_constraints,
            "run_design_candidate": self.run_design_candidate,
            "compare_design_runs": self.compare_design_runs,
        }

    # ------------------------------------------------------------------ #
    # catalog / dispatch
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_specs() -> List[ToolSpec]:
        return [
            ToolSpec(
                "load_run_artifacts",
                "Read the baseline run's artifacts (summary, configs, and the head/tail "
                "of the JSONL streams).",
                {"files": f"optional list of {sorted(ARTIFACT_FILES)}; default all"},
                evidence="read_baseline_artifacts",
            ),
            ToolSpec(
                "summarize_timeseries",
                "Per-column min / max / final / first warning / first critical / steps in "
                "band / trend for one JSONL stream.",
                {
                    "source": "telemetry | health_metrics (default telemetry)",
                    "columns": "optional list of column names, dotted for plant_sim topics",
                },
                evidence="inspected_timeseries",
            ),
            ToolSpec(
                "compute_eclss_features",
                "Subsystem stress indicators: command / rejection counts by reason, crew "
                "loss causes, failure windows, resource margins, shortfall ledgers.",
                {},
                evidence="computed_features",
            ),
            ToolSpec(
                "compute_theoretical_capacity",
                "Crew demand vs installed nameplate for ARS / OGS / WRS, including the "
                "operation cadence and the busy guard. Returns shortfall ratios.",
                {"crew_size": "optional occupant count override (default: scenario)"},
                evidence="computed_theoretical_capacity",
            ),
            ToolSpec(
                "plot_eclss_timeseries",
                "Render a PNG of the requested columns and return its path plus the same "
                "features as text (image understanding is never required).",
                {"columns": "optional list of column names"},
            ),
            ToolSpec(
                "propose_capacity_candidate",
                "Deterministic sizing helper: turn crew demand and a margin into a "
                "capacity field set. Sizes down as well as up — spare capacity is "
                "mass, volume and cost. Does not simulate.",
                {
                    "margin": "safety factor over theoretical demand (default 1.15)",
                    "subsystems": "optional subset of [ars, ogs, wrs] to resize",
                },
                evidence="proposed_candidate",
            ),
            ToolSpec(
                "evaluate_design_constraints",
                "Mass / volume / cost / bounds / budget labels for a capacity field set. "
                "Does not simulate.",
                {"fields": f"object with keys from {list(CAPACITY_KEYS)}"},
                evidence="evaluated_constraints",
            ),
            ToolSpec(
                "run_design_candidate",
                "Re-simulate the scenario with a capacity field set (post-run design "
                "disabled inside the candidate) and return its outcome.",
                {
                    "fields": f"object with keys from {list(CAPACITY_KEYS)}",
                    "label": "optional short candidate label",
                },
                evidence="ran_candidate",
            ),
            ToolSpec(
                "compare_design_runs",
                "Rank baseline and every simulated candidate — full survival clears, "
                "then less CRITICAL dwell, then the smallest mass / volume / cost — "
                "and report the selected candidate.",
                {},
                evidence="compared_runs",
            ),
        ]

    def catalog(self) -> List[Dict[str, Any]]:
        return [
            {"name": spec.name, "description": spec.description, "arguments": spec.arguments}
            for spec in self._specs.values()
        ]

    def catalog_text(self) -> str:
        lines: List[str] = []
        for spec in self._specs.values():
            args = (
                "; ".join(f"{k}: {v}" for k, v in spec.arguments.items())
                if spec.arguments
                else "no arguments"
            )
            lines.append(f"- {spec.name}: {spec.description} Arguments: {args}.")
        return "\n".join(lines)

    def tool_names(self) -> List[str]:
        return list(self._specs)

    def call(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        record_evidence: bool = True,
    ) -> Dict[str, Any]:
        """Dispatch one tool call.

        ``record_evidence=False`` runs the tool without crediting the evidence
        ledger, which stays a record of what the *designer* did. Report assembly
        re-runs ``compare_design_runs`` as housekeeping and must not make the
        audit trail claim the designer compared anything.
        """
        handler = self._handlers.get(name)
        if handler is None:
            return {
                "error": f"unknown tool {name!r}",
                "available_tools": self.tool_names(),
            }
        args = dict(arguments or {})
        try:
            result = handler(**args)
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # tools must never break the loop
            return {
                "error": f"{name} failed: {type(exc).__name__}: {exc}",
                "traceback_excerpt": traceback.format_exc(limit=3)[-600:],
            }
        spec = self._specs[name]
        if record_evidence and spec.evidence and not result.get("error"):
            self.evidence[spec.evidence] = True
        return result

    # ------------------------------------------------------------------ #
    # 1. artifacts
    # ------------------------------------------------------------------ #
    def load_run_artifacts(
        self,
        files: Optional[Sequence[str]] = None,
        head: int = 3,
        tail: int = 3,
    ) -> Dict[str, Any]:
        try:
            wanted = _name_list(files, argument="files") or list(ARTIFACT_FILES)
        except ValueError as exc:
            return {"error": str(exc), "available": sorted(ARTIFACT_FILES)}
        unknown = [name for name in wanted if name not in ARTIFACT_FILES]
        if unknown:
            return {
                "error": f"unknown artifact(s): {unknown}",
                "available": sorted(ARTIFACT_FILES),
            }
        head = max(0, min(int(head), 10))
        tail = max(0, min(int(tail), 10))
        out: Dict[str, Any] = {"run_dir": str(self.run_dir)}
        for name in wanted:
            path = self.run_dir / ARTIFACT_FILES[name]
            if not path.exists():
                out[name] = {"present": False}
                continue
            if name == "summary":
                out[name] = self.ctx.summary or evaluate_run_outcome(self.run_dir)
            elif name == "scenario_config":
                out[name] = {
                    "plant_sim": self.ctx.scenario_config.get("plant_sim"),
                    "thresholds": self.ctx.scenario_config.get("thresholds"),
                    "simulation": self.ctx.scenario_config.get("simulation"),
                    "backend": self.ctx.scenario_config.get("backend"),
                    "design_constraints": self.constraints.describe(),
                }
            elif name == "agents_config":
                agents = self.ctx.agents_config or {}
                actor = agents.get("actor") or {}
                out[name] = {
                    "actor_mode": actor.get("mode"),
                    "actor_team_count": (actor.get("team") or {}).get("count"),
                    "max_actions_per_step": actor.get("max_actions_per_step"),
                    "policy": actor.get("policy"),
                }
            else:
                rows = _read_jsonl(path)
                out[name] = {
                    "present": True,
                    "row_count": len(rows),
                    "head": rows[:head],
                    "tail": rows[-tail:] if tail else [],
                }
        return out

    # ------------------------------------------------------------------ #
    # 2. time series
    # ------------------------------------------------------------------ #
    def summarize_timeseries(
        self,
        source: str = "telemetry",
        columns: Optional[Sequence[str]] = None,
        run_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        if source not in TIMESERIES_SOURCES:
            return {"error": f"source must be one of {list(TIMESERIES_SOURCES)}"}
        target = Path(run_dir) if run_dir else self.run_dir
        rows = _read_jsonl(target / ARTIFACT_FILES[source])
        if not rows:
            return {"error": f"{source}.jsonl is empty or missing under {target}"}

        thresholds = self.ctx.scenario_config.get("thresholds") or {}
        if source == "health_metrics":
            counts = band_counts(rows)
            per_step = [
                {"step": row.get("step"), "overall": row.get("overall")}
                for row in rows
                if not row.get("post_ops")
            ]
            return {
                "source": source,
                "row_count": len(rows),
                **counts,
                "overall_by_step_excerpt": per_step[:12] + (["…"] if len(per_step) > 12 else []),
            }

        try:
            names = _name_list(columns, argument="columns") or list(DEFAULT_TIMESERIES_COLUMNS)
        except ValueError as exc:
            return {"error": str(exc)}
        out: Dict[str, Any] = {"source": source, "row_count": len(rows), "columns": {}}
        for name in names:
            series = _numeric_series(rows, name)
            if not series:
                out["columns"][name] = {"error": "column not present or non-numeric"}
                continue
            values = [value for _, value in series]
            first, last = values[0], values[-1]
            summary: Dict[str, Any] = {
                "n": len(values),
                "min": _round(min(values)),
                "max": _round(max(values)),
                "first": _round(first),
                "final": _round(last),
                "mean": _round(sum(values) / len(values)),
                "net_change": _round(last - first),
                "slope_per_step": _round(
                    (last - first) / max(len(values) - 1, 1), 6
                ),
            }
            summary.update(self._band_crossings(name, series, thresholds))
            out["columns"][name] = summary
        return out

    @staticmethod
    def _band_crossings(
        name: str,
        series: Sequence[Tuple[int, float]],
        thresholds: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Threshold crossings for the three health-bearing columns."""
        specs = {
            "co2_storage_kg": ("co2_storage_high_kg", "co2_storage_critical_kg", "above"),
            "o2_storage_kg": ("o2_storage_low_kg", "o2_storage_critical_kg", "below"),
            "product_water_reserve_l": (
                "product_water_low_l",
                "product_water_critical_l",
                "below",
            ),
        }
        spec = specs.get(name)
        if spec is None:
            return {}
        warn_key, crit_key, direction = spec
        try:
            warn = float(thresholds[warn_key])
        except (KeyError, TypeError, ValueError):
            return {}
        crit_raw = thresholds.get(crit_key)
        try:
            crit = float(crit_raw) if crit_raw is not None else None
        except (TypeError, ValueError):
            crit = None

        def hit(value: float, limit: float) -> bool:
            return value >= limit if direction == "above" else value <= limit

        warning_steps = critical_steps = 0
        first_warning: Optional[int] = None
        first_critical: Optional[int] = None
        shortfall = 0.0
        for step, value in series:
            if crit is not None and hit(value, crit):
                critical_steps += 1
                if first_critical is None:
                    first_critical = step
            elif hit(value, warn):
                warning_steps += 1
                if first_warning is None:
                    first_warning = step
            if direction == "below" and value < warn:
                shortfall += warn - value
            elif direction == "above" and value > warn:
                shortfall += value - warn
        return {
            "warning_threshold": warn,
            "critical_threshold": crit,
            "steps_in_warning": warning_steps,
            "steps_in_critical": critical_steps,
            "first_warning_step": first_warning,
            "first_critical_step": first_critical,
            "cumulative_shortfall_beyond_warning": _round(shortfall, 3),
        }

    # ------------------------------------------------------------------ #
    # 3. features
    # ------------------------------------------------------------------ #
    def compute_eclss_features(self, run_dir: Optional[str] = None) -> Dict[str, Any]:
        target = Path(run_dir) if run_dir else self.run_dir
        events = _read_jsonl(target / ARTIFACT_FILES["events"])
        telemetry = _read_jsonl(target / ARTIFACT_FILES["telemetry"])
        outcome = evaluate_run_outcome(target)

        applied: Dict[str, int] = {}
        rejected_by_reason: Dict[str, int] = {}
        rejected_by_kind: Dict[str, int] = {}
        failure_windows: List[Dict[str, Any]] = []
        crew_lost_events: List[Dict[str, Any]] = []
        for event in events:
            kind = str(event.get("kind", ""))
            command = event.get("command") or {}
            command_kind = str(command.get("kind", "unknown"))
            if kind.endswith("operational_applied"):
                applied[command_kind] = applied.get(command_kind, 0) + 1
            elif kind.endswith("operational_rejected"):
                reason = event.get("reason")
                if not reason:
                    details = (event.get("result") or {}).get("details") or {}
                    reason = details.get("reason") or "other"
                rejected_by_reason[str(reason)] = rejected_by_reason.get(str(reason), 0) + 1
                rejected_by_kind[command_kind] = rejected_by_kind.get(command_kind, 0) + 1
            elif "subsystem_failure" in kind:
                failure_windows.append(
                    {k: event.get(k) for k in ("step", "kind", "subsystem", "enabled")}
                )
            elif kind.endswith("crew_lost"):
                crew_lost_events.append(
                    {
                        "step": event.get("step"),
                        "lost": event.get("lost"),
                        "remaining": event.get("remaining"),
                        "limiting": event.get("limiting"),
                    }
                )

        last_plant: Dict[str, Any] = {}
        for row in reversed(telemetry):
            topics = row.get("raw_topics")
            if isinstance(topics, Mapping) and isinstance(topics.get("plant_sim"), Mapping):
                last_plant = dict(topics["plant_sim"])
                break

        stress = self._subsystem_stress(telemetry, applied, rejected_by_reason)
        return {
            "run_dir": str(target),
            "outcome": outcome,
            "commands_applied": applied,
            "commands_rejected_by_reason": rejected_by_reason,
            "commands_rejected_by_kind": rejected_by_kind,
            "subsystem_stress": stress,
            "crew_loss_events": crew_lost_events[:10],
            "crew_lost_by_cause": outcome.get("crew_lost_by_cause"),
            "subsystem_failure_events": failure_windows[:10],
            "final_plant_state": {
                key: _round(last_plant.get(key))
                for key in (
                    "captured_co2_kg",
                    "urine_buffer_l",
                    "total_o2_shortfall_kg",
                    "total_water_shortfall_l",
                    "total_co2_vented_kg",
                    "crew_alive",
                    "crew_lost_total",
                )
                if key in last_plant
            },
        }

    def _subsystem_stress(
        self,
        telemetry: Sequence[Mapping[str, Any]],
        applied: Mapping[str, int],
        rejected_by_reason: Mapping[str, int],
    ) -> Dict[str, Any]:
        thresholds = self.ctx.scenario_config.get("thresholds") or {}
        co2 = _numeric_series(telemetry, "co2_storage_kg")
        o2 = _numeric_series(telemetry, "o2_storage_kg")
        water = _numeric_series(telemetry, "product_water_reserve_l")
        urine = _numeric_series(telemetry, "plant_sim.urine_buffer_l")

        def trend(series: Sequence[Tuple[int, float]]) -> Optional[float]:
            if len(series) < 2:
                return None
            return _round((series[-1][1] - series[0][1]) / max(len(series) - 1, 1), 6)

        return {
            "ars": {
                "actions_applied": applied.get("air_revitalisation", 0),
                "co2_trend_per_step": trend(co2),
                "co2_peak": _round(max((v for _, v in co2), default=None)),
                "co2_high_threshold": thresholds.get("co2_storage_high_kg"),
                "busy_rejections": rejected_by_reason.get("subsystem_busy", 0),
            },
            "ogs": {
                "actions_applied": applied.get("oxygen_generation", 0),
                "o2_trend_per_step": trend(o2),
                "o2_min": _round(min((v for _, v in o2), default=None)),
                "o2_low_threshold": thresholds.get("o2_storage_low_kg"),
            },
            "wrs": {
                "actions_applied": applied.get("water_recovery", 0),
                "water_trend_per_step": trend(water),
                "water_min": _round(min((v for _, v in water), default=None)),
                "urine_buffer_final": _round(urine[-1][1]) if urine else None,
                "water_low_threshold": thresholds.get("product_water_low_l"),
            },
            "duplicate_command_rejections": rejected_by_reason.get(
                "duplicate_command_this_step", 0
            ),
        }

    # ------------------------------------------------------------------ #
    # 4. theoretical sizing
    # ------------------------------------------------------------------ #
    def compute_theoretical_capacity(
        self,
        crew_size: Optional[int] = None,
        fields: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = copy.deepcopy(self.ctx.scenario_config)
        if fields:
            errors = validate_capacity_fields(fields)
            if errors:
                return {"error": "; ".join(errors)}
            apply_capacity_fields(config, fields)
        plant = config.get("plant_sim") or {}
        crew = plant.get("crew") or {}
        time_cfg = plant.get("time") or {}
        size = int(crew_size if crew_size is not None else crew.get("size", 0))
        activity = float(crew.get("activity_factor", 1.0))
        step_seconds = float(time_cfg.get("step_seconds", 1200.0))
        steps_per_day = SECONDS_PER_DAY / max(step_seconds, 1e-9)

        demand = {
            "co2_generated_kg_day": size * float(crew.get("co2_kg_day_person", 1.04)) * activity,
            "o2_demand_kg_day": size * float(crew.get("o2_kg_day_person", 0.84)) * activity,
            "potable_water_demand_l_day": size
            * float(crew.get("potable_water_kg_day_person", 2.28))
            * activity,
            "wrs_feed_l_day": size
            * (
                float(crew.get("urine_kg_day_person", 1.50))
                + float(crew.get("condensate_kg_day_person", 0.75))
            )
            * activity,
        }

        capacity = read_capacity_fields(config)
        policy = self._actor_policy()
        ars_goal = float((policy.get("ars_goal") or {}).get("initial_co2_mass", 1.8))
        ars_reference = float((plant.get("ars") or {}).get("reference_goal_co2_kg", 1.8))
        ars_scale = ars_goal / max(ars_reference, 1e-9)
        ogs_water = float((policy.get("ogs_goal") or {}).get("input_water_mass", 0.0))
        urine_request = float((policy.get("wrs_goal") or {}).get("urine_volume", 0.0))

        subsystems: Dict[str, Any] = {}
        for name, op_key, default_seconds in (
            ("ars", "ars_operation_seconds", 4800.0),
            ("ogs", "ogs_operation_seconds", 1200.0),
            ("wrs", "wrs_operation_seconds", 1200.0),
        ):
            op_seconds = float(time_cfg.get(op_key, default_seconds))
            busy_steps = max(1, math.ceil(op_seconds / max(step_seconds, 1e-9)))
            max_actions_per_day = math.floor(steps_per_day / busy_steps)
            subsystems[name] = {
                "operation_seconds": op_seconds,
                "busy_steps": busy_steps,
                "max_actions_per_day": max_actions_per_day,
            }

        ars_nameplate = capacity["plant_sim.ars.capacity_kg_day"]
        ars_per_action = (
            ars_nameplate * subsystems["ars"]["operation_seconds"] / SECONDS_PER_DAY * ars_scale
        )
        ars_effective = ars_per_action * subsystems["ars"]["max_actions_per_day"]
        subsystems["ars"].update(
            {
                "nameplate_kg_day": ars_nameplate,
                "goal_scale": _round(ars_scale),
                "removal_per_action_kg": _round(ars_per_action),
                "effective_capacity_kg_day": _round(ars_effective),
                "required_kg_day": _round(demand["co2_generated_kg_day"]),
                "shortfall_kg_day": _round(demand["co2_generated_kg_day"] - ars_effective),
                "coverage_ratio": _round(
                    ars_effective / max(demand["co2_generated_kg_day"], 1e-9)
                ),
                "required_nameplate_kg_day": _round(
                    demand["co2_generated_kg_day"]
                    / max(
                        subsystems["ars"]["operation_seconds"]
                        / SECONDS_PER_DAY
                        * ars_scale
                        * subsystems["ars"]["max_actions_per_day"],
                        1e-9,
                    )
                ),
            }
        )

        ogs_nameplate = capacity["plant_sim.ogs.max_o2_kg_day"]
        ogs_cap_per_action = (
            ogs_nameplate * subsystems["ogs"]["operation_seconds"] / SECONDS_PER_DAY
        )
        ogs_request_per_action = ogs_water / max(WATER_PER_O2, 1e-9)
        ogs_per_action = min(ogs_cap_per_action, ogs_request_per_action)
        ogs_effective = ogs_per_action * subsystems["ogs"]["max_actions_per_day"]
        subsystems["ogs"].update(
            {
                "nameplate_kg_day": ogs_nameplate,
                "o2_per_action_capacity_kg": _round(ogs_cap_per_action),
                "o2_per_action_requested_kg": _round(ogs_request_per_action),
                "o2_per_action_kg": _round(ogs_per_action),
                "effective_capacity_kg_day": _round(ogs_effective),
                "required_kg_day": _round(demand["o2_demand_kg_day"]),
                "shortfall_kg_day": _round(demand["o2_demand_kg_day"] - ogs_effective),
                "coverage_ratio": _round(ogs_effective / max(demand["o2_demand_kg_day"], 1e-9)),
                "required_nameplate_kg_day": _round(
                    demand["o2_demand_kg_day"]
                    / max(
                        subsystems["ogs"]["operation_seconds"]
                        / SECONDS_PER_DAY
                        * subsystems["ogs"]["max_actions_per_day"],
                        1e-9,
                    )
                ),
                "input_water_mass_now_kg": ogs_water,
                "input_water_mass_for_nameplate_kg": _round(
                    required_ogs_input_water_mass(config)
                ),
                "request_limited": ogs_request_per_action < ogs_cap_per_action - 1e-12,
            }
        )

        wrs_batch = capacity["plant_sim.wrs.max_feed_l_per_operation"]
        wrs_effective = wrs_batch * subsystems["wrs"]["max_actions_per_day"]
        urine_per_step = expected_urine_l_per_step(config)
        feed_per_step = demand["wrs_feed_l_day"] / max(steps_per_day, 1e-9)
        trigger_l = float(policy.get("wrs_feed_trigger_l", 0.0) or 0.0)
        subsystems["wrs"].update(
            {
                "batch_capacity_l": wrs_batch,
                "effective_capacity_l_day": _round(wrs_effective),
                "required_l_day": _round(demand["wrs_feed_l_day"]),
                "shortfall_l_day": _round(demand["wrs_feed_l_day"] - wrs_effective),
                "coverage_ratio": _round(wrs_effective / max(demand["wrs_feed_l_day"], 1e-9)),
                "expected_urine_l_per_step": _round(urine_per_step),
                "expected_feed_l_per_step": _round(feed_per_step),
                # The crew only starts WRS once the buffer reaches this trigger,
                # so a batch smaller than the trigger leaves feed behind and the
                # potable reserve drifts down even though "capacity" looks ample.
                "wrs_feed_trigger_l": trigger_l,
                "batch_smaller_than_trigger": bool(trigger_l > 0 and wrs_batch < trigger_l),
                "urine_volume_now_l": urine_request,
                "urine_volume_recommended_l": _round(required_wrs_urine_volume(config)),
                "request_limited": urine_request < urine_per_step - 1e-12,
            }
        )

        return {
            "crew_size": size,
            "step_seconds": step_seconds,
            "steps_per_day": _round(steps_per_day),
            "crew_demand_per_day": {k: _round(v) for k, v in demand.items()},
            "installed_capacity": capacity,
            "subsystems": subsystems,
            "note": (
                "effective capacity accounts for the busy guard: a subsystem accepted at "
                "step t is unavailable for ceil(operation_seconds / step_seconds) steps."
            ),
        }

    def _actor_policy(self) -> Dict[str, Any]:
        agents = self.ctx.agents_config or {}
        actor = agents.get("actor") or {}
        policy = actor.get("policy")
        if isinstance(policy, Mapping) and policy:
            return dict(policy)
        scenario_agents = (self.ctx.scenario_config.get("agents") or {}).get("actor") or {}
        return dict(scenario_agents.get("policy") or {})

    # ------------------------------------------------------------------ #
    # 5. plot
    # ------------------------------------------------------------------ #
    def plot_eclss_timeseries(
        self,
        columns: Optional[Sequence[str]] = None,
        run_dir: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            names = _name_list(columns, argument="columns") or list(DEFAULT_TIMESERIES_COLUMNS)
        except ValueError as exc:
            return {"error": str(exc)}
        summary = self.summarize_timeseries(source="telemetry", columns=names, run_dir=run_dir)
        if summary.get("error"):
            return summary
        if not self.ctx.plots_enabled:
            return {**summary, "plot_path": None, "plot_skipped": "plots disabled"}

        target = Path(run_dir) if run_dir else self.run_dir
        rows = _read_jsonl(target / ARTIFACT_FILES["telemetry"])
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception as exc:
            return {**summary, "plot_path": None, "plot_error": f"matplotlib unavailable: {exc}"}

        plots_dir = self.run_dir / "design_plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        name = filename or f"timeseries_{len(self._plot_paths) + 1:02d}.png"
        path = plots_dir / name

        drawn: List[str] = []
        fig, axes = plt.subplots(len(names), 1, figsize=(9, 2.2 * len(names)), sharex=True)
        if len(names) == 1:
            axes = [axes]
        thresholds = self.ctx.scenario_config.get("thresholds") or {}
        threshold_lines = {
            "co2_storage_kg": ("co2_storage_high_kg", "co2_storage_critical_kg"),
            "o2_storage_kg": ("o2_storage_low_kg", "o2_storage_critical_kg"),
            "product_water_reserve_l": ("product_water_low_l", "product_water_critical_l"),
        }
        # Operation-applied markers: which subsystem drives which series.
        marker_command = {
            "co2_storage_kg": "air_revitalisation",
            "o2_storage_kg": "oxygen_generation",
            "product_water_reserve_l": "water_recovery",
        }
        applied_steps = self._applied_command_steps(target)
        for axis, column in zip(axes, names):
            series = _numeric_series(rows, column)
            if not series:
                axis.set_title(f"{column} (no data)")
                continue
            axis.plot([s for s, _ in series], [v for _, v in series], linewidth=1.2)
            for key in threshold_lines.get(column, ()):
                value = thresholds.get(key)
                if value is None:
                    continue
                try:
                    axis.axhline(float(value), linestyle="--", linewidth=0.8)
                except (TypeError, ValueError):
                    continue
            steps = applied_steps.get(marker_command.get(column, ""), [])
            if steps:
                by_step = dict(series)
                marks = [(s, by_step[s]) for s in steps if s in by_step]
                if marks:
                    axis.scatter(
                        [s for s, _ in marks],
                        [v for _, v in marks],
                        s=12,
                        marker="v",
                        zorder=3,
                    )
            axis.set_ylabel(column, fontsize=8)
            axis.grid(True, alpha=0.3)
            drawn.append(column)
        axes[-1].set_xlabel("step")
        fig.suptitle(f"ECLSS timeseries — {target.name}", fontsize=10)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        self._plot_paths.append(str(path))
        return {**summary, "plot_path": str(path), "plotted_columns": drawn}

    def _applied_command_steps(self, run_dir: Path) -> Dict[str, List[int]]:
        """Steps where each operational command was actually applied."""
        out: Dict[str, List[int]] = {}
        for event in _read_jsonl(run_dir / ARTIFACT_FILES["events"]):
            if not str(event.get("kind", "")).endswith("operational_applied"):
                continue
            kind = str((event.get("command") or {}).get("kind", ""))
            step = event.get("step")
            if kind and isinstance(step, int):
                out.setdefault(kind, []).append(step)
        return out

    @property
    def plot_paths(self) -> List[str]:
        return list(self._plot_paths)

    # ------------------------------------------------------------------ #
    # 6. candidate sizing helper
    # ------------------------------------------------------------------ #
    def propose_capacity_candidate(
        self,
        margin: float = 1.15,
        subsystems: Optional[Sequence[str]] = None,
        crew_size: Optional[int] = None,
        target_survival: Optional[Any] = None,
    ) -> Dict[str, Any]:
        try:
            margin_value = float(margin)
        except (TypeError, ValueError):
            return {"error": "margin must be numeric"}
        if not math.isfinite(margin_value) or margin_value <= 0:
            return {"error": "margin must be finite and > 0"}
        try:
            requested = _name_list(subsystems, argument="subsystems")
        except ValueError as exc:
            return {"error": str(exc)}
        wanted = [s.lower() for s in (requested or ("ars", "ogs", "wrs"))]
        unknown = [s for s in wanted if s not in ("ars", "ogs", "wrs")]
        if unknown:
            return {"error": f"unknown subsystem(s): {unknown}"}

        theory = self.compute_theoretical_capacity(crew_size=crew_size)
        if theory.get("error"):
            return theory
        subs = theory["subsystems"]
        current = theory["installed_capacity"]
        fields: Dict[str, float] = {}
        rationale: Dict[str, str] = {}

        # Sizing follows demand in both directions. Capacity that nobody needs is
        # mass, volume and cost the design is paying for, and every candidate is
        # re-simulated before it can be adopted, so an undersized guess is caught
        # by the survival requirement rather than by a floor here. The only floor
        # is the smallest machine that can actually be built.
        if "ars" in wanted:
            need = float(subs["ars"]["required_nameplate_kg_day"]) * margin_value
            value = self.constraints.clamp_to_bounds("ars", need)
            fields["plant_sim.ars.capacity_kg_day"] = round(value, 3)
            rationale["ars"] = (
                f"{subs['ars']['required_kg_day']} kg/day CO2 at "
                f"{subs['ars']['max_actions_per_day']} actions/day and goal scale "
                f"{subs['ars']['goal_scale']} → nameplate "
                f"{subs['ars']['required_nameplate_kg_day']} kg/day × margin {margin_value}"
                f"{_bound_note(need, value)} (installed "
                f"{current['plant_sim.ars.capacity_kg_day']})"
            )
        if "ogs" in wanted:
            need = float(subs["ogs"]["required_nameplate_kg_day"]) * margin_value
            value = self.constraints.clamp_to_bounds("ogs", need)
            fields["plant_sim.ogs.max_o2_kg_day"] = round(value, 3)
            rationale["ogs"] = (
                f"{subs['ogs']['required_kg_day']} kg/day O2 at "
                f"{subs['ogs']['max_actions_per_day']} actions/day → nameplate "
                f"{subs['ogs']['required_nameplate_kg_day']} kg/day × margin {margin_value}"
                f"{_bound_note(need, value)} (installed "
                f"{current['plant_sim.ogs.max_o2_kg_day']}); "
                "ogs_goal.input_water_mass is synced on apply"
            )
        if "wrs" in wanted:
            feed_per_step = float(subs["wrs"]["expected_feed_l_per_step"])
            trigger = float(subs["wrs"]["wrs_feed_trigger_l"])
            # One action must absorb the buffer that triggered it, otherwise the
            # untreated remainder keeps growing and the potable reserve drifts
            # down while nameplate capacity still looks sufficient.
            need = max(feed_per_step * margin_value, trigger)
            value = self.constraints.clamp_to_bounds("wrs", need)
            fields["plant_sim.wrs.max_feed_l_per_operation"] = round(value, 3)
            rationale["wrs"] = (
                f"{subs['wrs']['required_l_day']} L/day feed = {feed_per_step} L/step; the "
                f"crew starts WRS at a {trigger} L buffer, so one batch must absorb that "
                f"much → {round(value, 3)} L (margin {margin_value})"
                f"{_bound_note(need, value)} (installed "
                f"{current['plant_sim.wrs.max_feed_l_per_operation']}); oversizing beyond "
                "this only adds mass"
            )

        evaluation = self.constraints.evaluate(fields)
        return {
            "fields": fields,
            "margin": margin_value,
            "rationale": rationale,
            "constraint_preview": {
                key: evaluation.get(key)
                for key in (
                    "constraint_status",
                    "total_mass_kg",
                    "total_volume_m3",
                    "total_cost_musd",
                    "violations",
                )
            },
            "target_survival": target_survival,
            "note": "sizing helper only — this candidate is not simulated yet",
        }

    # ------------------------------------------------------------------ #
    # 7. constraints
    # ------------------------------------------------------------------ #
    def evaluate_design_constraints(
        self,
        fields: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if fields is None:
            return {"error": "fields is required", "allowed_keys": list(CAPACITY_KEYS)}
        if not isinstance(fields, Mapping):
            return {"error": "fields must be an object", "allowed_keys": list(CAPACITY_KEYS)}
        evaluation = self.constraints.evaluate(fields)
        evaluation.pop("by_subsystem", None)
        return evaluation

    # ------------------------------------------------------------------ #
    # 8. candidate re-simulation
    # ------------------------------------------------------------------ #
    def run_design_candidate(
        self,
        fields: Optional[Mapping[str, Any]] = None,
        label: Optional[str] = None,
        steps: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not isinstance(fields, Mapping) or not fields:
            return {"error": "fields is required", "allowed_keys": list(CAPACITY_KEYS)}
        if len(self.candidates) >= self.ctx.max_candidate_runs:
            return {
                "error": (
                    f"candidate budget exhausted "
                    f"({self.ctx.max_candidate_runs} runs); compare what you have"
                ),
                "candidates_run": len(self.candidates),
            }

        evaluation = self.constraints.evaluate(fields)
        candidate_id = f"candidate_{len(self.candidates) + 1:03d}"
        record: Dict[str, Any] = {
            "candidate_id": candidate_id,
            "label": str(label) if label else candidate_id,
            "fields": {k: v for k, v in fields.items()},
            "constraint_evaluation": evaluation,
            "simulated": False,
        }

        if not evaluation.get("simulate_allowed", False):
            record["error"] = (
                f"candidate not simulated: constraint_status="
                f"{evaluation.get('constraint_status')} and simulation_policy forbids it"
            )
            self.candidates.append(record)
            return {**record, "candidates_run": len(self.candidates)}

        try:
            run_dir, applied = self._simulate_candidate(candidate_id, fields, steps)
        except Exception as exc:
            record["error"] = f"candidate run failed: {type(exc).__name__}: {exc}"
            record["traceback_excerpt"] = traceback.format_exc(limit=4)[-800:]
            self.candidates.append(record)
            return {**record, "candidates_run": len(self.candidates)}

        outcome = evaluate_run_outcome(run_dir)
        record.update(
            {
                "simulated": True,
                "run_dir": str(run_dir),
                "synced_action_payloads": applied,
                "outcome": outcome,
            }
        )
        self.candidates.append(record)
        return {
            **record,
            "baseline_outcome": {
                key: self.baseline_outcome.get(key)
                for key in (
                    "crew_remaining",
                    "crew_initial",
                    "critical_step_count",
                    "warning_step_count",
                    "peak_co2_storage_kg",
                    "min_o2_storage_kg",
                )
            },
            "candidates_run": len(self.candidates),
        }

    def _simulate_candidate(
        self,
        candidate_id: str,
        fields: Mapping[str, Any],
        steps: Optional[int],
    ) -> Tuple[Path, Dict[str, Any]]:
        # Deliberately function-local. The cycle is inherent to the feature, not
        # an accident of layering: scenario_run -> ssos_post_run_design ->
        # ssos_tool_use_design -> design_tools, and this tool re-enters the
        # runner because "verify a design by re-simulating it" *is* the runner.
        # One of the two edges has to be deferred; deferring it here keeps the
        # runner's import graph honest and costs one lookup per candidate run.
        from scenario.ssos_eclss_loop.scenario_run import SsosEclssLoopScenario

        config = copy.deepcopy(self.ctx.scenario_config)
        apply_capacity_fields(config, fields)
        synced = sync_action_payloads(config, policy_hint=self._actor_policy())
        agents = config.setdefault("agents", {})
        # Candidate runs never trigger another post-run design pass (design doc §12).
        agents.setdefault("design", {})["mode"] = "none"
        if self.ctx.candidate_actor_mode != "inherit":
            agents.setdefault("actor", {})["mode"] = self.ctx.candidate_actor_mode
        elif self.ctx.agents_config:
            actor_mode = (self.ctx.agents_config.get("actor") or {}).get("mode")
            if actor_mode:
                agents.setdefault("actor", {})["mode"] = actor_mode
        candidate_steps = steps if steps is not None else self.ctx.candidate_steps
        if candidate_steps is not None:
            config.setdefault("simulation", {})["steps"] = int(candidate_steps)

        out_dir = self.run_dir / "candidate_runs" / candidate_id
        SsosEclssLoopScenario().run(
            output_dir=out_dir,
            overrides=config,
            recreate_output=True,
        )
        return out_dir, synced

    # ------------------------------------------------------------------ #
    # 9. comparison / ranking
    # ------------------------------------------------------------------ #
    def compare_design_runs(self) -> Dict[str, Any]:
        """Rank every simulated candidate. Takes no arguments — by design.

        Evidence completeness is read from the ledger, never from a caller: an
        argument here would let the model declare its own homework done and be
        shown a ranking that says ``final_eligible`` before it had looked at
        anything.
        """
        simulated = [dict(record) for record in self.candidates if record.get("simulated")]
        if not simulated:
            return {
                "error": "no simulated candidate to compare; call run_design_candidate first",
                "candidates_run": len(self.candidates),
            }
        # ``compared_runs`` is credited only after this call returns, so judging
        # it as missing here would make the first comparison report every
        # candidate ineligible.
        complete = not [key for key in self.missing_evidence() if key != "compared_runs"]
        for record in simulated:
            mark_final_eligibility(
                record,
                baseline_outcome=self.baseline_outcome,
                require_in_bounds=self.constraints.require_in_bounds_final,
                require_within_budget=self.constraints.require_feasible_final,
                evidence_complete=complete,
            )
        ranked = rank_candidates(simulated)
        selection = select_final_candidate(ranked, baseline_outcome=self.baseline_outcome)
        # Say which criterion settled it. The objective is lexicographic, so
        # the criteria below the deciding one were never consulted, and a
        # reader should not have to work that out from the numbers.
        selection["rank_rationale"] = rank_rationale(
            ranked[0], ranked[1] if len(ranked) > 1 else None
        )
        self._ranked = ranked
        self._selection = selection
        return {
            "baseline": {
                key: self.baseline_outcome.get(key)
                for key in (
                    "crew_initial",
                    "crew_remaining",
                    "critical_step_count",
                    "warning_step_count",
                    "peak_co2_storage_kg",
                    "min_o2_storage_kg",
                    "final_product_water_reserve_l",
                )
            },
            "ranking": [self._ranking_row(record) for record in ranked],
            "selection": selection,
            "evidence_complete": complete,
            "require_in_bounds_final": self.constraints.require_in_bounds_final,
            "require_feasible_final": self.constraints.require_feasible_final,
        }

    @staticmethod
    def _ranking_row(record: Mapping[str, Any]) -> Dict[str, Any]:
        outcome = record.get("outcome") or {}
        constraints = record.get("constraint_evaluation") or {}
        return {
            "rank": record.get("rank"),
            "candidate_id": record.get("candidate_id"),
            "label": record.get("label"),
            "fields": record.get("fields"),
            "crew_remaining": outcome.get("crew_remaining"),
            "crew_initial": outcome.get("crew_initial"),
            "critical_step_count": outcome.get("critical_step_count"),
            "warning_step_count": outcome.get("warning_step_count"),
            "peak_co2_storage_kg": outcome.get("peak_co2_storage_kg"),
            "min_o2_storage_kg": outcome.get("min_o2_storage_kg"),
            "final_product_water_reserve_l": outcome.get("final_product_water_reserve_l"),
            "physics_gate_passed": outcome.get("physics_gate_passed"),
            "evaluation_compact": outcome.get("evaluation_compact"),
            "constraint_status": constraints.get("constraint_status"),
            "total_mass_kg": _round(constraints.get("total_mass_kg"), 2),
            "total_volume_m3": _round(constraints.get("total_volume_m3"), 3),
            "total_cost_musd": _round(constraints.get("total_cost_musd"), 2),
            "design_penalty": _round(constraints.get("design_penalty"), 4),
            "final_eligible": record.get("final_eligible"),
            "final_ineligible_reasons": record.get("final_ineligible_reasons"),
        }

    # ------------------------------------------------------------------ #
    # evidence ledger
    # ------------------------------------------------------------------ #
    REQUIRED_EVIDENCE = (
        "read_baseline_artifacts",
        "inspected_timeseries",
        "computed_theoretical_capacity",
        "proposed_candidate",
        "evaluated_constraints",
        "ran_candidate",
        "compared_runs",
    )

    def missing_evidence(self) -> List[str]:
        missing = [key for key in self.REQUIRED_EVIDENCE if not self.evidence.get(key)]
        # "proposed a candidate" is satisfied by any candidate record, however it
        # was produced (the sizing helper is optional, the candidate is not).
        if "proposed_candidate" in missing and self.candidates:
            missing.remove("proposed_candidate")
        return missing

    def evidence_complete(self) -> bool:
        return not self.missing_evidence()

    def evidence_report(self) -> Dict[str, Any]:
        return {
            "required": list(self.REQUIRED_EVIDENCE),
            "collected": sorted(k for k, v in self.evidence.items() if v),
            "missing": self.missing_evidence(),
            "candidates_run": len([c for c in self.candidates if c.get("simulated")]),
        }

    @property
    def ranked_candidates(self) -> List[Dict[str, Any]]:
        return list(getattr(self, "_ranked", []))

    @property
    def selection(self) -> Dict[str, Any]:
        return dict(getattr(self, "_selection", {}))


__all__ = [
    "ARTIFACT_FILES",
    "DesignToolContext",
    "DesignToolkit",
    "ToolSpec",
]
