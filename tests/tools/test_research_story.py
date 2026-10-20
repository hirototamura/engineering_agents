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
        assert 'id="download-evidence"' not in page
        assert 'URL.createObjectURL' not in page
        assert 'src="http' not in page and '<script src=' not in page
        assert not re.search(r'href="(?:\.\./|evidence\.json)', page)
        assert 'https://pub.sakana.ai/mass/' in page
        assert 'id="source-hashes"' not in page and 'id="run-sources"' not in page
        assert 'Full source campaign archive' not in page
        assert 'Inspect original result JSON' not in page
        payloads.append(json.loads(re.search(r'<script id="research-evidence" type="application/json">(.*?)</script>', page, re.S)[1]))
    assert payloads[0] == payloads[1] == json.loads((HERE / 'evidence.json').read_text())


def test_reviewed_system_model_does_not_replace_archived_run_requirements():
    data = json.loads((HERE / 'evidence.json').read_text())
    model = data['system_model']
    assert model['revision'] == 'reviewed-20261019-1'
    assert len(model['parameters']) == 37
    assert sum(r['data']['record_role'] == 'requirement' for r in model['requirements']) == 22
    assert sum(r['data']['record_role'] == 'requirement_group' for r in model['requirements']) == 7
    hold = next(r for r in model['requirements'] if r['id'] == 'R-HOLD')
    assert 'shall' in hold['data']['statement']
    assert hold['data']['acceptance_criteria']['value'] == 30
    assert hold['data']['acceptance_criteria']['domain'] == 'hardware'
    assert hold['data']['approval_state'] == 'human_reviewed'
    assert hold['data']['physical_verified'] is None
    assert hold['data']['verification_status'] == 'not_run'
    for run in data['runs']:
        ref = next(r for r in run['frozen_requirement_refs'] if r['id'] == 'R-HOLD')
        assert ref['revision'] == 'trace-20261010-2'
        assert run['screening']['required_duration_s'] == 6


def test_reviewed_model_allocations_are_complete_and_do_not_imply_hardware_success():
    model = json.loads((HERE / 'evidence.json').read_text())['system_model']
    assert len(model['functions']) == 8
    assert len([r for r in model['products'] if r['data'].get('record_role') == 'component']) == 10
    nodes = {r['id']: r for field in ['requirements', 'parameters', 'functions', 'products', 'verification_cases'] for r in model[field]}
    for field in ['requirements', 'parameters', 'functions']:
        for r in model[field]:
            for link in r['links']:
                if link['type'] == 'allocate':
                    target = nodes[link['target']['id']]
                    assert target['revision'] == link['target']['revision'] == model['revision']
                    assert target['kind'] in {'function', 'product'}
    hold = nodes['R-HOLD']
    assert {e['target']['id'] for e in hold['links'] if e['type'] == 'allocate'} == {'cube.function.control-balance', 'cube.function.maintain-contact'}
    assert model['baseline']['data']['adopted_design_baseline'] is False
    assert model['baseline']['data']['physical_verified'] is False
    assert model['review_decision']['data']['reviewer']['id'] == 'hirototamura'
    assert all(r['data']['execution_status'] == 'not_run' and not r['data']['evidence_refs'] for r in model['verification_cases'])


def test_round_changes_resolve_reference_alias_and_keep_retrieved_evidence():
    data = json.loads((HERE / 'evidence.json').read_text())
    later = data['runs'][1]
    first = later['experiments'][0]
    assert first['changes_from_prompt_best'] == [
        {'parameter': 'momentum_q_scale', 'before': 1.0, 'after': 1.25}]
    twelfth = later['experiments'][11]
    assert twelfth['changes_from_prompt_best'] == [
        {'parameter': 'rate_q_scale', 'before': 1.0, 'after': 1.05}]
    for run in data['runs']:
        assert len(run['experiments']) == run['rounds_completed']
        for experiment in run['experiments']:
            assert experiment['memory_selected_count'] == len(experiment['retrieved_evidence'])
            assert all('measured_feedback' in e and 'episode_id' in e
                       for e in experiment['retrieved_evidence'])
    sweep = [c for c in later['candidates'] if c['round'] >= 12]
    assert len(sweep) == 9 and all(c['all_screening_passed'] for c in sweep)
    assert all(c['proposal']['parameters'] == later['comparison_design']['parameters'] for c in sweep)
    assert {c['proposal']['control']['momentum_q_scale'] for c in sweep} == {0.85}


def test_replay_keeps_both_failure_modes_and_nominal_observations():
    data = json.loads((HERE / 'evidence.json').read_text())
    early, later = data['runs']
    assert len(early['replays']) == len(later['replays']) == 3
    speed_failure = early['replays'][1]
    assert speed_failure['case'].endswith('seed 811')
    assert speed_failure['status'] == 'completed'
    assert speed_failure['summary']['speed_governor_fraction'] > 0.01
    balance_failure = later['replays'][0]
    assert balance_failure['status'] == 'lost_balance'
    assert abs(balance_failure['frames'][-1]['time_s'] - 4.725) < 1e-8
    for run in (early, later):
        nominal = run['replays'][2]
        assert nominal['status'] == 'completed'
        assert nominal['summary']['speed_governor_fraction'] == 0
        for replay in run['replays']:
            for frame in replay['frames']:
                assert all(key in frame for key in ('motor_x_nm', 'wheel_x_rpm', 'speed_governor_active'))
                assert frame['time_s'] <= replay['summary']['simulated_duration_s'] + 1e-8


def test_phone_server_routes_only_two_articles():
    assert allowed_page('/index.html') == 'index.html'
    assert allowed_page('/index.ja.html?language=ja') == 'index.ja.html'
    for route in ('/evidence.json', '/.git/config', '/../one-piece/records.json', '/other.html'):
        assert allowed_page(route) is None


def test_mjx_projection_preserves_historical_selection_and_missing_means_missing():
    from tools.research_story.recent import measured_score
    import pytest
    data = json.loads((HERE / 'evidence.json').read_text())
    later = data['runs'][1]
    observed = max(later['mjx']['candidates'], key=lambda c: c['score'])
    archived = max(later['candidates'], key=lambda c: c['score'])
    assert observed['round'] == 15 and archived['round'] == 19
    assert observed['score'] == pytest.approx(0.9914083900706222)
    assert later['best']['score'] == archived['score']  # no rewrite of history
    snapshot = {'contract': {'screening': later['screening']},
                'plan': {'objective': {'rms_penalty': .05, 'torque_proxy_penalty': .2}}}
    records = [{'domain_id': 'd', 'condition_id': 'c', 'seed': n,
                'summary': {'status': 'completed'}} for n in range(12)]
    with pytest.raises(KeyError, match='gpu_summary'):
        measured_score({'records': records}, snapshot)


def test_new_studies_distinguish_attempts_measurements_and_mounting_score_source():
    data = json.loads((HERE / 'evidence.json').read_text())
    study = data['multi_agent_study']
    assert study['original_dispatch_state'] == 'inconclusive'
    for a in study['arms'].values():
        assert (a['attempted'], a['completed'], len(a['rejected'])) == (10, 8, 2)
        assert a['fresh_mjx']['passed'] == 12
        assert a['workflow_usage']['model_weights_updated'] is False
    assert study['starting_fresh_mjx']['passed'] == 12
    mount = data['mounting']
    assert mount['full_matrix_mjx'] == 'not_run'
    assert mount['cells']['M1C1']['score'] < mount['cells']['M0C1']['score']
    assert mount['cells']['M1C1']['controller_digest'] == mount['cells']['M0C1']['controller_digest']
    upper, lower = mount['replays']
    assert upper['summary']['speed_governor_fraction'] > .01 > lower['summary']['speed_governor_fraction']
    assert lower['physics']['wheel_mount_side'] == 'near_corner_000'
    assert upper['frames'][0]['time_s'] == lower['frames'][0]['time_s']
    assert mount['other_seven_corners_verified'] is False


def test_public_article_has_new_experiments_without_backend_agreement_narrative(tmp_path):
    for p in export(tmp_path, tmp_path / 'phone'):
        page = p.read_text()
        body = page.split('<script id="research-evidence"')[0]
        assert 'id="multi"' in body and 'id="mount"' in body
        assert 'id="mount-upper"' in body and 'id="mount-time"' in body
        assert 'CPU/GPU' not in body and '数値整合' not in body
        assert '0.991408' in body and '0.4%' in body
