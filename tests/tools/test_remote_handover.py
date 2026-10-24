"""The handover importer must not overwrite work or trust unsafe ZIP paths."""
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "deploy/eng-agents-008/restore_workspace.py"
SPEC = importlib.util.spec_from_file_location("restore_workspace", SOURCE)
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


def test_restore_is_idempotent_and_preserves_changed_files(tmp_path):
    archive = tmp_path / "evidence.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("results/new.txt", "new")
        z.writestr("results/existing.txt", "original")
    root = tmp_path / "workspace"
    root.mkdir()
    restore.restore_archive(archive, root)
    restore.restore_archive(archive, root)
    (root / "results/existing.txt").write_text("human edit")
    (root / "results/new.txt").unlink()
    with pytest.raises(FileExistsError):
        restore.restore_archive(archive, root)
    assert not (root / "results/new.txt").exists()  # Validate all entries before writes.
    assert (root / "results/existing.txt").read_text() == "human edit"


@pytest.mark.parametrize("filename", ["../escape", "/absolute", "results/../../escape", "results\\escape"])
def test_restore_rejects_traversal(tmp_path, filename):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(filename, "bad")
    with pytest.raises(ValueError):
        restore.restore_archive(archive, tmp_path / "workspace")


def test_restore_rejects_archive_and_existing_symlinks(tmp_path):
    archive = tmp_path / "bad.zip"
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(info, "elsewhere")
    with pytest.raises(ValueError):
        restore.restore_archive(archive, tmp_path / "workspace")
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "results").symlink_to(tmp_path, target_is_directory=True)
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("results/new", "bad")
    with pytest.raises(ValueError):
        restore.restore_archive(archive, root)


def test_legacy_experiments_use_recorded_scenario_instead_of_run_name(tmp_path):
    archive = tmp_path / "historical.zip"
    prefix = "engineering_agents/src/experiments/results/"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(prefix + "memory-gpu-smoke/summary.json", json.dumps({"scenario": "ssos_eclss_loop"}))
        z.writestr(prefix + "cube-run/summary.json", json.dumps({"scenario": "balancing_cube"}))
        z.writestr(prefix + "evaluation.html", "historical ECLSS catalogue")
        z.writestr("engineering_agents/src/experiments/analysis/datasets/sample.json", "{}")
    root = tmp_path / "workspace"
    receipt = restore.restore_archive(archive, root)
    assert receipt["migrated_paths"] == 4
    assert (root / "engineering_agents/experiments/eclss/results/memory-gpu-smoke/summary.json").is_file()
    assert (root / "engineering_agents/experiments/balancing_cube/results/cube-run/summary.json").is_file()
    assert (root / "engineering_agents/experiments/eclss/analysis/datasets/sample.json").is_file()
    assert not (root / "engineering_agents/src/experiments").exists()
    assert restore.restore_archive(archive, root) == receipt


def test_legacy_unknown_track_or_mapped_collision_fails_before_writes(tmp_path):
    root = tmp_path / "workspace"
    archive = tmp_path / "unknown.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("new.txt", "must not be installed")
        z.writestr("engineering_agents/src/experiments/results/unknown/output.json", "{}")
    with pytest.raises(ValueError, match="Cannot classify"):
        restore.restore_archive(archive, root)
    assert not root.exists()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("engineering_agents/src/experiments/results/cube-run/summary.json", '{"scenario":"balancing_cube"}')
        z.writestr("engineering_agents/experiments/balancing_cube/results/cube-run/summary.json", "different")
    with pytest.raises(ValueError, match="Duplicate destination"):
        restore.restore_archive(archive, root)
    assert not root.exists()
