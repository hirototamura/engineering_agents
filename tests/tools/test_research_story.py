"""The article keeps numerical evidence and experimental scope intact."""
import hashlib
import json
from pathlib import Path
import re

from tools.research_story.build import HERE, build
from tools.research_story.portable import export
from tools.research_story.serve_portable import allowed_page


def test_frozen_extract_preserves_candidates_failures_and_factorial_best():
    data = json.loads((HERE / 'evidence.json').read_text())
    assert data['historical']['candidate_count'] == 2048
    assert sorted(data['historical']['prior46'].values()) == [6, 9, 31]
    for run, total in zip(data['runs'], [13, 24]):
        assert len(run['candidates']) == run['candidate_count'] == total
        assert sum(c['passed'] for c in run['cases']) == 11
        assert run['selection_status'] == 'provisional'
        assert run['best']['physical_fidelity'] is None
        for r in run['rounds']:
            assert r['best_score'] == max(c['score'] for c in run['candidates'] if c['round'] <= r['round'])
    later = data['runs'][1]
    cell = next(c for c in later['candidates'] if c['round'] == 4 and c['matrix_cell'] == 'M0C1')
    assert later['rounds'][4]['best_score'] == cell['score'] == 0.9913819995897613
    assert later['validation']['gpu_state'] == 'completed'
    assert later['validation']['agreement_state'] == 'inconclusive'
    failed = next(c for c in later['cases'] if not c['passed'])
    assert failed['seed'] == 812 and failed['status'] == 'lost_balance'


def test_replay_is_recorded_pose_through_termination_without_continuation():
    data = json.loads((HERE / 'evidence.json').read_text())
    a, b = [r['replay'] for r in data['runs']]
    assert a['case'] == b['case'] == 'heavy-delay-prior-confirm / confirm-b / seed 812'
    assert a['status'] == 'completed' and b['status'] == 'lost_balance'
    assert abs(a['frames'][-1]['time_s'] - 6) < 1e-8
    assert abs(b['frames'][-1]['time_s'] - 4.725) < 1e-8
    for replay in (a, b):
        assert all(x['time_s'] < y['time_s'] for x, y in zip(replay['frames'], replay['frames'][1:]))
        assert all(len(f['quaternion_wxyz']) == 4 and len(f['position_m']) == 3 for f in replay['frames'])


def test_offline_language_pages_embed_identical_original_evidence(tmp_path):
    original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*') if p.is_file()}
    paths = build(tmp_path, tmp_path / 'article')
    payloads = []
    for language, path in zip(['en', 'ja'], paths):
        source = path.read_text()
        assert f'<html lang="{language}">' in source
        assert '@@' not in source
        assert not re.search(r'<script\b[^>]*\bsrc=', source)
        payloads.append(json.loads(re.search(r'<script id="research-evidence" type="application/json">(.*?)</script>', source, re.S)[1]))
    assert payloads[0] == payloads[1] == json.loads((HERE / 'evidence.json').read_text())
    assert original == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*') if p.is_file()}


def test_research_story_has_own_catalog_family():
    from tools.report_library.catalog import classify
    row = classify(Path('engineering_agents/src/experiments/results/balancing-cube-research-story-20261012/index.html'), 'Research')
    assert row['family'] == 'Balancing cube research story'
    assert row['category'] == 'Research' and row['scope'] == 'report'
    counterpart = classify(Path('engineering_agents/src/experiments/results/balancing-cube-research-story-20261012/index.ja.html'), '研究')
    assert counterpart['scope'] == 'source'


def test_phone_export_contains_only_self_contained_language_pages(tmp_path):
    paths = export(tmp_path, tmp_path / 'phone')
    assert {path.name for path in paths} == {'index.html', 'index.ja.html'}
    assert {path.name for path in (tmp_path / 'phone').iterdir()} == {'index.html', 'index.ja.html'}
    payloads = []
    for path in paths:
        page = path.read_text()
        assert 'id="download-evidence"' in page
        assert 'URL.createObjectURL' in page
        assert 'src="http' not in page and '<script src=' not in page
        assert not re.search(r'href="(?:\.\./|evidence\.json)', page)
        assert 'https://github.com/hirototamura/engineering_agents/releases/tag/reports-qwen-memory-20261012' in page
        payloads.append(json.loads(re.search(r'<script id="research-evidence" type="application/json">(.*?)</script>', page, re.S)[1]))
    assert payloads[0] == payloads[1] == json.loads((HERE / 'evidence.json').read_text())


def test_phone_server_routes_only_two_articles():
    assert allowed_page('/index.html') == 'index.html'
    assert allowed_page('/index.ja.html?language=ja') == 'index.ja.html'
    for route in ('/evidence.json', '/.git/config', '/../one-piece/records.json', '/other.html'):
        assert allowed_page(route) is None
