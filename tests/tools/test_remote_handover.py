"""The handover importer must not overwrite work or trust unsafe ZIP paths."""
import importlib.util
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
