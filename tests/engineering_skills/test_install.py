from pathlib import Path
import pytest
from tools.engineering_skills.install import install

REPO=Path(__file__).resolve().parents[2]


def test_skill_install_is_discoverable_idempotent_and_protects_edits(tmp_path):
    home=tmp_path/'hermes'
    first=install(REPO,home)
    assert len(first['skills'])==4
    assert install(REPO,home)==first
    f=next((home/'skills/engineering').glob('*/SKILL.md'))
    f.write_text('human edit')
    with pytest.raises(FileExistsError):install(REPO,home)
    assert f.read_text()=='human edit'


def test_installer_updates_only_unchanged_owned_copies(tmp_path):
    import shutil
    repo=tmp_path/'repo';repo.mkdir()
    shutil.copytree(REPO/'skills',repo/'skills')
    home=tmp_path/'profile'
    install(repo,home)
    path=next((repo/'skills/engineering').glob('*/SKILL.md'))
    path.write_text(path.read_text()+'\nA new reviewed procedure.\n')
    install(repo,home)
    assert (home/'skills/engineering'/path.relative_to(repo/'skills/engineering')).read_bytes()==path.read_bytes()
