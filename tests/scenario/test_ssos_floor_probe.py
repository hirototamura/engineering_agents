"""Measuring where each subsystem stops keeping the crew alive.

The chain used to be handed a calculated minimum and told not to go below it.
The calculation was wrong for one of the three subsystems, and being stated as
a rule, no round ever tested any of them. These tests are about replacing that
assertion with an experiment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

import pytest
import yaml

from scenario.ssos_eclss_loop.floor_probe import (
    MEASURED_LIMITS_FILENAME,
    STATUS_BRACKETED,
    STATUS_NO_CLIFF_FOUND,
    STATUS_NO_SAFE_ANCHOR,
    measure_survival_limits,
    scenario_runner,
    write_measured_limits,
)

ARS = "plant_sim.ars.capacity_kg_day"
OGS = "plant_sim.ogs.max_o2_kg_day"
WRS = "plant_sim.wrs.max_feed_l_per_operation"

# A station with three independent cliffs, so a probe that finds one by luck
# still has to find the other two.
CLIFFS = {ARS: 20.0, OGS: 42.0, WRS: 2.0}


def _fake_station(cliffs: Mapping[str, float] = CLIFFS, *, crew: int = 50):
    """A runner where survival is exactly 'every subsystem above its cliff'."""
    tried: List[Dict[str, float]] = []

    def run(fields: Dict[str, float], label: str) -> Dict[str, Any]:
        tried.append(dict(fields))
        short = [key for key, cliff in cliffs.items() if fields.get(key, 0.0) < cliff]
        lost = 4 * len(short)
        return {
            "crew_initial": crew,
            "crew_remaining": crew - lost,
            "crew_lost_by_cause": {f"{key.split('.')[1]}_warning": 4 for key in short},
        }

    run.tried = tried  # type: ignore[attr-defined]
    return run


def test_the_cliff_is_found_from_a_starting_sizing_that_does_not_work():
    """No calculated minimum is supplied — the search grows until it survives."""
    run = _fake_station()
    result = measure_survival_limits(
        start={ARS: 4.5, OGS: 9.25, WRS: 10.0},
        runner=run,
        bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0},
    )
    assert result["status"] == STATUS_BRACKETED
    for key, cliff in CLIFFS.items():
        found = result["limits"][key]
        assert found["status"] == STATUS_BRACKETED
        assert found["lowest_survivable"] >= cliff
        assert found["highest_fatal"] < cliff
        # Inside a few percent of the real edge, on both sides.
        assert found["lowest_survivable"] / cliff < 1.1
        assert found["highest_fatal"] / cliff > 0.7


def test_what_it_reports_is_two_runs_that_happened_not_a_rule():
    run = _fake_station()
    result = measure_survival_limits(
        start={ARS: 30.0, OGS: 60.0, WRS: 5.0}, runner=run, bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0}
    )
    found = result["limits"][OGS]
    assert found["lowest_survivable_crew"] == "all"
    assert found["highest_fatal_crew"] == "46/50"
    assert found["highest_fatal_causes"] == {"ogs_warning": 4}
    # No threshold, no floor, no instruction.
    text = json.dumps(result)
    for word in ("floor", "must", "do_not", "forbid", "minimum_required"):
        assert word not in text


def test_the_smallest_machine_that_survived_is_reported_whole():
    run = _fake_station()
    result = measure_survival_limits(
        start={ARS: 4.5, OGS: 9.25, WRS: 10.0},
        runner=run,
        bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0},
    )
    smallest = result["smallest_surviving_machine"]
    assert set(smallest) == {ARS, OGS, WRS}
    for key, cliff in CLIFFS.items():
        assert smallest[key] >= cliff
    # And it is a machine that was actually run, not an assembly of separate bests.
    assert smallest in run.tried  # type: ignore[attr-defined]


def test_a_subsystem_with_no_cliff_says_so_rather_than_naming_one():
    """Below the smallest buildable size there is nothing left to test."""
    run = _fake_station({ARS: 20.0, OGS: 42.0, WRS: 0.0})
    result = measure_survival_limits(
        start={ARS: 25.0, OGS: 50.0, WRS: 5.0},
        runner=run,
        bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0},
    )
    water = result["limits"][WRS]
    assert water["status"] == STATUS_NO_CLIFF_FOUND
    assert water["lowest_survivable"] == pytest.approx(1.0)
    assert "highest_fatal" not in water


def test_a_station_nothing_can_save_is_reported_as_such():
    def never(fields: Dict[str, float], label: str) -> Dict[str, Any]:
        return {"crew_initial": 50, "crew_remaining": 0}

    result = measure_survival_limits(start={ARS: 4.5, OGS: 9.25, WRS: 10.0}, runner=never)
    assert result["status"] == STATUS_NO_SAFE_ANCHOR
    assert result["limits"] == {}


def test_measuring_one_subsystem_holds_the_others_where_they_last_worked():
    """Otherwise slack elsewhere quietly covers for the subsystem under test."""
    run = _fake_station()
    measure_survival_limits(
        start={ARS: 4.5, OGS: 9.25, WRS: 10.0},
        runner=run,
        bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0},
    )
    tried: List[Dict[str, float]] = run.tried  # type: ignore[attr-defined]
    # By the time the water recycler is being measured, the gas pair has already
    # been brought down to what it needs, not left at the grown anchor.
    water_probes = [row for row in tried if row[WRS] < 2.0]
    assert water_probes
    assert all(row[ARS] < 25.0 for row in water_probes)


def test_the_same_sizing_is_never_simulated_twice():
    run = _fake_station()
    result = measure_survival_limits(
        start={ARS: 25.0, OGS: 50.0, WRS: 5.0}, runner=run, bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0}
    )
    tried: List[Dict[str, float]] = run.tried  # type: ignore[attr-defined]
    unique = {json.dumps(row, sort_keys=True) for row in tried}
    assert len(unique) == len(tried) == result["simulations"]


def test_the_sweep_is_written_where_a_person_can_read_it(tmp_path: Path):
    run = _fake_station()
    result = measure_survival_limits(
        start={ARS: 25.0, OGS: 50.0, WRS: 5.0}, runner=run, bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0}
    )
    path = write_measured_limits(tmp_path, result)
    assert path.name == MEASURED_LIMITS_FILENAME
    assert json.loads(path.read_text(encoding="utf-8"))["limits"][ARS]["status"]


# --------------------------------------------------------------------------- #
# against the real station
# --------------------------------------------------------------------------- #
def test_the_real_water_recycler_stops_working_well_above_its_calculated_minimum():
    """The measurement's whole reason for existing, on the station it shipped for.

    Crew demand divided by operations per day says the water recycler needs a
    1.5625 L batch. It does not: the crew only starts it once five litres have
    collected, so a smaller batch leaves feed behind every cycle. Three separate
    rounds of an observed chain proposed the calculated value and each lost four
    occupants finding this out.
    """
    from scenario.runner import scenario_config_path
    from scenario.ssos_eclss_loop.design_variables import read_capacity_fields

    config = yaml.safe_load(
        scenario_config_path("ssos_eclss_loop").read_text(encoding="utf-8")
    )
    config.setdefault("backend", {})["kind"] = "plant_sim"
    config.setdefault("simulation", {})["steps"] = 72

    import tempfile

    result = measure_survival_limits(
        start=read_capacity_fields(config),
        bounds={ARS: 4.5, OGS: 9.25, WRS: 1.0},
        runner=scenario_runner(
            scenario_config=config,
            output_root=Path(tempfile.mkdtemp(prefix="limits_")),
            actor_mode="labeled_rule_base",
        ),
    )
    assert result["status"] == STATUS_BRACKETED
    water = result["limits"][WRS]
    assert water["status"] == STATUS_BRACKETED
    # Well above the 1.5625 the calculation asserted.
    assert water["lowest_survivable"] > 1.8
    assert water["highest_fatal_causes"]

    # The gas pair, by contrast, is where the calculation said -- which is only
    # knowable because it was checked.
    assert 20.0 < result["limits"][ARS]["lowest_survivable"] < 22.0
    assert 41.0 < result["limits"][OGS]["lowest_survivable"] < 44.0
