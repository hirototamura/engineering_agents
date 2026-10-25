from pathlib import Path
import pytest
from tools.engineering_skills.install import install
from environment.engineering_analysis.catalog import SKILLS

REPO=Path(__file__).resolve().parents[2]


def test_skill_install_is_discoverable_idempotent_and_protects_edits(tmp_path):
    home=tmp_path/'hermes'
    first=install(REPO,home)
    assert set(first['skills']) == set(SKILLS)
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


def test_stable_launchers_quote_paths_and_protect_human_edits(tmp_path):
    import subprocess
    from tools.engineering_skills.launchers import install as launchers
    repo=tmp_path/'repo with spaces';workspace=tmp_path/'workspace with spaces'
    target=repo/'deploy/eng-agents-008/bin/ea-engineering';target.parent.mkdir(parents=True)
    target.write_text('#!/bin/sh\nprintf "%s" "$EA_WORKSPACE"\n')
    binary=tmp_path/'bin'
    launchers(repo,workspace,binary)
    assert subprocess.check_output(['bash',str(binary/'ea-engineering')],text=True)==str(workspace)
    launchers(repo,workspace,binary)
    (binary/'ea-engineering').write_text('human launcher')
    with pytest.raises(FileExistsError):launchers(repo,workspace,binary)


@pytest.mark.parametrize('human_edit',[False,True])
def test_owned_renamed_skills_migrate_but_human_edits_are_preserved(tmp_path,human_edit):
    import hashlib,json
    home=tmp_path/'profile';old=home/'skills/engineering/old-cube-name/SKILL.md'
    old.parent.mkdir(parents=True);old.write_text('original version')
    receipt={'skill_files':{'old-cube-name/SKILL.md':hashlib.sha256(old.read_bytes()).hexdigest()}}
    (home/'engineering-skills-install.json').write_text(json.dumps(receipt))
    note=old.parent/'human-note.txt';note.write_text('preserve this')
    if human_edit:
        old.write_text('human changes')
        with pytest.raises(FileExistsError,match='human edits'):install(REPO,home)
        assert old.read_text()=='human changes'
    else:
        install(REPO,home)
        assert not old.exists()
    assert note.read_text()=='preserve this'
