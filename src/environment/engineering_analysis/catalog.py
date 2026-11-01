"""Versioned engineering analysis skill contracts and their executable dependency graph."""
from dataclasses import dataclass
import importlib


@dataclass(frozen=True)
class Skill:
    name: str
    output_type: str
    module: str
    function: str = 'analyze'
    requires: tuple = ()
    jobs: str | None = None
    project_specific: bool = False

    @property
    def kind(self):
        return 'composite' if self.requires else 'atomic'

    def contract(self):
        return {'schema_version':1, 'name':self.name, 'kind':self.kind,
                'project_scope':'balancing_cube' if self.project_specific else 'agnostic',
                'primary_output':{'file':'result.json','type':self.output_type,'version':1},
                'requires':list(self.requires),
                'validation':'composition_contracts' if self.requires else 'independent_numerical_oracles'}


SKILLS = {s.name:s for s in (
    Skill('transfer-function-derivation','transfer_function_model','linear','transfer_function'),
    Skill('frequency-response-calculation','frequency_response','linear','frequency_response'),
    Skill('state-feedback-gain-synthesis','state_feedback_gain','linear','feedback'),
    Skill('bode-diagram-analysis','frequency_response_assessment','control_composition','bode',
          ('transfer-function-derivation','frequency-response-calculation'),'bode_jobs'),
    Skill('pole-placement-design','pole_placement_design','control_composition','pole',
          ('transfer-function-derivation','state-feedback-gain-synthesis'),'pole_jobs'),
    Skill('rigid-body-mass-properties','rigid_body_mass_properties','mass_properties'),
    Skill('mass-property-uncertainty','mass_property_uncertainty_assessment','mechanical',
          requires=('rigid-body-mass-properties',), jobs='jobs'),
    Skill('motor-operating-point','motor_operating_point','motor'),
    Skill('first-order-thermal-response','thermal_interval_response','thermal'),
    Skill('actuator-duty-cycle-analysis','actuator_duty_cycle_assessment','electrical',
          requires=('motor-operating-point','first-order-thermal-response'),jobs='jobs'),
    Skill('requirement-evidence-assessment','requirement_evidence_assessment','systems'),
    Skill('cube-gnc-loop-analysis','cube_local_control_assessment','gnc',requires=(
        'transfer-function-derivation','bode-diagram-analysis','pole-placement-design'), jobs='jobs',project_specific=True),
)}

ALIASES = {'gnc':'cube-gnc-loop-analysis', 'mechanical':'mass-property-uncertainty',
           'electrical':'actuator-duty-cycle-analysis', 'systems':'requirement-evidence-assessment'}


def resolve(name):
    try:
        return SKILLS[ALIASES.get(name,name)]
    except KeyError:
        raise ValueError(f'Unknown engineering analysis skill: {name}') from None


def implementation(skill):
    return importlib.import_module('environment.engineering_analysis.'+skill.module)


def calculate(name, data, stack=()):
    """Pure in-process composition; the tool runner adds retained dependency receipts."""
    skill = resolve(name)
    if skill.name in stack:
        raise ValueError('Cyclic analysis composition')
    module = implementation(skill)
    if not skill.requires:
        return getattr(module,skill.function)(data)
    results = {}
    for role, child, value in getattr(module,skill.jobs)(data,results):
        if child not in skill.requires:
            raise ValueError('Undeclared analysis dependency')
        results[role] = calculate(child,value,(*stack,skill.name))
    return getattr(module,skill.function)(data,results)


def validate_graph():
    def visit(name, stack):
        if name in stack:
            raise ValueError('Skill dependency cycle: '+' -> '.join((*stack,name)))
        for dependency in SKILLS[name].requires:
            if dependency not in SKILLS:
                raise ValueError('Missing skill dependency: '+dependency)
            visit(dependency,(*stack,name))
    for name in SKILLS:
        visit(name,())
