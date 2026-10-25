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
