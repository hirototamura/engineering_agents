"""Deterministic evidence eligibility and exact-revision threshold assessment."""
import operator
from .common import number

OPS = {'<=': operator.le, '>=': operator.ge, '<': operator.lt, '>': operator.gt, '==': operator.eq}
METRIC_SCHEMA = 'engineering_metric_evidence/v1'
BOUND_FIELDS = ('id', 'requirement_ref', 'design_ref', 'configuration_digest',
                'domain', 'metric', 'unit', 'conditions', 'status')


def numeric(value):
    try:
        return number(value, 'numeric value')
    except (TypeError, ValueError, OverflowError):
        return None


def same_value(a, b):
    if type(a) is type(b):
        return a == b
    return numeric(a) is not None and numeric(b) is not None and a == b


def analyze(data, verified_artifacts=None):
    # Only the caller that reads and hashes artifacts supplies this separate map.
    # Flags or metric records embedded in the input JSON are never trusted.
    verified_artifacts = verified_artifacts or {}
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
        matching = [(i,e) for i,e in enumerate(data['evidence']) if e.get('requirement_ref') == reference]
        outcomes = []
        for index,evidence in matching:
            reasons = []
            if evidence.get('design_ref') != data['design_ref'] or evidence.get('configuration_digest') != target:
                reasons.append('stale_configuration_or_design')
            artifact = verified_artifacts.get(index, {})
            if not artifact.get('hash_verified', False):
                reasons.append('missing_or_bad_artifact_hash')
            record = artifact.get('record')
            bound = (isinstance(record, dict) and record.get('schema') == METRIC_SCHEMA
                     and all(field in record and field in evidence and record[field] == evidence[field]
                             for field in BOUND_FIELDS)
                     and 'value' in record and 'value' in evidence
                     and same_value(record['value'], evidence['value']))
            if artifact.get('hash_verified', False) and not bound:
                reasons.append('metric_not_bound_to_artifact')
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
            threshold = numeric(criterion.get('value'))
            if not op or threshold is None:
                reasons.append('criterion_not_machine_evaluable')
            status = evidence.get('status')
            value = numeric(record['value']) if bound else None
            if status == 'completed' and bound and value is None:
                reasons.append('metric_not_machine_evaluable')
            eligible = not reasons
            if status != 'completed':
                reasons.append('execution_'+str(status or 'unknown'))
            if not eligible:
                state = 'inconclusive'
            elif status == 'failed':
                state = 'fail'
            elif status != 'completed':
                state = 'inconclusive'
            else:
                state = 'pass' if op(value, threshold) else 'fail'
            outcomes.append({'evidence_id': evidence.get('id'), 'state': state, 'eligible': eligible, 'reasons': reasons})
        # A failed relevant run cannot be hidden by a later success in this batch.
        states = {o['state'] for o in outcomes if o['eligible']}
        state = ('fail' if 'fail' in states else 'inconclusive' if 'inconclusive' in states
                 else 'pass' if 'pass' in states else 'inconclusive' if outcomes else 'not_run')
        rows.append({'requirement_ref': reference, 'state': state, 'evidence': outcomes})
    return {'requirements': rows, 'all_evaluable_requirements_pass': bool(rows) and all(r['state'] in ('pass', 'not_applicable') for r in rows) and any(r['state'] == 'pass' for r in rows),
            'physical_verified': False, 'baseline_adopted': False,
            'limitations': ['Assessment binds metrics and metadata to hashed artifacts; it does not authenticate the producer or establish physical truth.',
                            'Hardware requirements cannot be satisfied by simulation-domain evidence.',
                            'Requirement approval is distinct from verification status.', 'No canonical records or baselines are changed.']}
