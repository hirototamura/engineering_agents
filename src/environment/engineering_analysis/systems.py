"""Deterministic evidence eligibility and exact-revision threshold assessment."""
import operator
from .common import number

OPS = {'<=': operator.le, '>=': operator.ge, '<': operator.lt, '>': operator.gt, '==': operator.eq}


def analyze(data):
    if data.get('data_basis') not in ('derived', 'synthetic_validation'):
        raise ValueError('Systems assessment requires derived evidence or an explicit synthetic validation case')
    target = data['configuration_digest']
    if not isinstance(target, str) or len(target) != 64 or any(c not in '0123456789abcdef' for c in target):
        raise ValueError('A lowercase SHA-256 configuration digest is required')
    if not data.get('design_ref', {}).get('id') or not data['design_ref'].get('revision'):
        raise ValueError('Exact design revision is required')
    rows = []
    seen = set()
    for requirement in data['requirements']:
        reference = {'id': requirement['id'], 'revision': requirement['revision']}
        key = (reference['id'], reference['revision'])
        if key in seen:
            raise ValueError('Duplicate requirement revision')
        seen.add(key)
        body = requirement['data']
        criterion = body.get('acceptance_criteria', {})
        if criterion.get('applicability') == 'not_applicable':
            rows.append({'requirement_ref': reference, 'state': 'not_applicable', 'reason': criterion.get('reason')})
            continue
        matching = [e for e in data['evidence'] if e.get('requirement_ref') == reference]
        outcomes = []
        for evidence in matching:
            reasons = []
            if evidence.get('design_ref') != data['design_ref'] or evidence.get('configuration_digest') != target:
                reasons.append('stale_configuration_or_design')
            if not evidence.get('artifact_verified', False):
                reasons.append('missing_or_bad_artifact_hash')
            if evidence.get('domain') != criterion.get('domain'):
                reasons.append('verification_domain_mismatch')
            if evidence.get('unit') != criterion.get('unit'):
                reasons.append('unit_mismatch')
            if evidence.get('metric') != criterion.get('metric'):
                reasons.append('metric_mismatch')
            if not set(body.get('conditions', [])).issubset(set(evidence.get('conditions', []))):
                reasons.append('condition_coverage_missing')
            if body.get('unresolved_items'):
                reasons.append('open_requirement_conditions')
            if body.get('approval_state') != 'human_reviewed':
                reasons.append('requirement_not_human_reviewed')
            op = OPS.get(criterion.get('operator'))
            if not op or criterion.get('value') is None:
                reasons.append('criterion_not_machine_evaluable')
            status = evidence.get('status')
            if status != 'completed':
                reasons.append('execution_'+str(status or 'unknown'))
            if reasons:
                state = 'fail' if status == 'failed' else 'inconclusive'
            else:
                value = number(evidence['value'], 'evidence value')
                threshold = number(criterion['value'], 'requirement threshold')
                state = 'pass' if op(value, threshold) else 'fail'
            outcomes.append({'evidence_id': evidence.get('id'), 'state': state, 'reasons': reasons})
        # A failed relevant run cannot be hidden by a later success in this batch.
        states = {o['state'] for o in outcomes}
        state = 'fail' if 'fail' in states else 'inconclusive' if 'inconclusive' in states else 'pass' if states == {'pass'} else 'not_run'
        rows.append({'requirement_ref': reference, 'state': state, 'evidence': outcomes})
    return {'requirements': rows, 'all_evaluable_requirements_pass': bool(rows) and all(r['state'] in ('pass', 'not_applicable') for r in rows) and any(r['state'] == 'pass' for r in rows),
            'physical_verified': False, 'baseline_adopted': False,
            'limitations': ['Assessment checks supplied metrics and artifact integrity, not sensor calibration or physical truth.',
                            'Hardware requirements cannot be satisfied by simulation-domain evidence.',
                            'Requirement approval is distinct from verification status.', 'No canonical records or baselines are changed.']}
