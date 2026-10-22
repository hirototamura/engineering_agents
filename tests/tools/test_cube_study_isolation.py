from pathlib import Path

import pytest

from tools.run_cube_workflow_pair import clone_store, commit_names


def test_store_clones_share_only_immutable_objects_and_isolate_new_records(tmp_path):
    pytest.importorskip('onepiece')
    from onepiece import Store, make_record
    source=Store(tmp_path/'initial')
    first=make_record(project_id='cube',id='initial',kind='specification',data={'value':'initial'})
    source.import_records([first])
    clone_store(source.path,tmp_path/'a')
    clone_store(source.path,tmp_path/'b')
    a,b=Store(tmp_path/'a'),Store(tmp_path/'b')
    a.import_records([make_record(project_id='cube',id='a-only',kind='specification',data={'value':'a'})])
    assert len(a.records('cube'))==2
    assert len(b.records('cube'))==len(source.records('cube'))==1
    assert a.index_path.stat().st_ino!=source.index_path.stat().st_ino
    assert b.index_path.stat().st_ino!=source.index_path.stat().st_ino
    assert len(commit_names(a.path))==2
    assert a.check()['ok'] and b.check()['ok']
