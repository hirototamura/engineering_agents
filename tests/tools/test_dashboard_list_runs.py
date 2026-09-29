"""Dashboard run listing includes iterate chain children."""

from pathlib import Path

from tools.dashboard.app import _list_runs, _run_label


def _touch_summary(path: Path, *, telemetry: bool = False) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "summary.json").write_text("{}\n", encoding="utf-8")
    if telemetry:
        (path / "telemetry.jsonl").write_text("{}\n", encoding="utf-8")


def test_list_runs_keeps_top_level_summary_dirs(tmp_path: Path):
    _touch_summary(tmp_path / "plain-run", telemetry=True)
    labels = [_run_label(p, tmp_path) for p in _list_runs(tmp_path)]
    assert labels == ["plain-run"]


def test_list_runs_expands_iterate_children_and_skips_parent_wrapper(tmp_path: Path):
    chain = tmp_path / "design-iter-3"
    _touch_summary(chain)
    _touch_summary(chain / "01", telemetry=True)
    _touch_summary(chain / "02", telemetry=True)
    _touch_summary(chain / "baseline-replay", telemetry=True)
    _touch_summary(chain / "final-replay", telemetry=True)
    labels = [_run_label(p, tmp_path) for p in _list_runs(tmp_path)]
    assert labels == [
        "design-iter-3/01",
        "design-iter-3/02",
        "design-iter-3/baseline-replay",
        "design-iter-3/final-replay",
    ]


def test_list_runs_keeps_parent_when_it_also_has_telemetry(tmp_path: Path):
    parent = tmp_path / "nested-sim"
    _touch_summary(parent, telemetry=True)
    _touch_summary(parent / "child", telemetry=True)
    labels = [_run_label(p, tmp_path) for p in _list_runs(tmp_path)]
    assert labels == ["nested-sim", "nested-sim/child"]
