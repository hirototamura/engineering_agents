"""Convert an exported cube MJCF to USD using the installed Isaac importer."""
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('input', type=Path)
args = parser.parse_args()
if not os.environ.get('CUDA_VISIBLE_DEVICES', '').startswith('GPU-'):
    raise RuntimeError('Select one allocated GPU by UUID')
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'active_cuda_gpus': [0], 'multi_gpu': False, 'physics_gpu': 0})
try:
    from isaaclab.sim.converters import MjcfConverter, MjcfConverterCfg
    converter = MjcfConverter(MjcfConverterCfg(asset_path=str(args.input.resolve()/'cube.xml'),
        usd_dir=str(args.input.resolve()/'usd'), fix_base=False,
        collision_from_visuals=False, self_collision=False, force_usd_conversion=True))
    from pxr import Usd, UsdPhysics
    stage = Usd.Stage.Open(converter.usd_path)
    masses = []
    joints = []
    for prim in stage.Traverse():
        if prim.HasAPI(UsdPhysics.RigidBodyAPI) and prim.HasAPI(UsdPhysics.MassAPI):
            m = UsdPhysics.MassAPI(prim)
            masses.append({'path': str(prim.GetPath()), 'mass': m.GetMassAttr().Get(),
                           'inertia': list(m.GetDiagonalInertiaAttr().Get()),
                           'com': list(m.GetCenterOfMassAttr().Get())})
        if prim.IsA(UsdPhysics.RevoluteJoint):
            joints.append(str(prim.GetPath()))
    receipt = {'usd_path': converter.usd_path, 'mass_properties': masses, 'revolute_joints': joints,
               'status': 'converted_pending_physics_audit', 'physical_verified': False}
    (args.input/'conversion.json').write_text(json.dumps(receipt, indent=2, allow_nan=False)+'\n')
    print(json.dumps(receipt), flush=True)
finally:
    app.close()
