"""Export the frozen One-Piece reference for Isaac import; no canonical writes."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--snapshot-revision', default='bottom-corner-000-20261017-3')
    parser.add_argument('--physics-only', action='store_true', help='Remove noncolliding decorative meshes for large batches')
    parser.add_argument('--proposal', type=Path)
    args = parser.parse_args(argv)
    from integrations.one_piece.mechanical_bridge import MechanicalBridge
    from scenario.balancing_cube.adapter import BalancingCubeAdapter
    from environment.mujoco.contact import build_contact_xml

    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = MechanicalBridge(args.store, snapshot_revision=args.snapshot_revision).load_snapshot()
    adapter = BalancingCubeAdapter(snapshot)
    proposal = json.loads(args.proposal.read_text()) if args.proposal else {
        'id': 'isaac-reference', 'family': 'reference',
        'hypothesis': 'Measure the frozen reference in PhysX before design exploration'}
    compiled = adapter.compile(proposal)
    xml = ET.fromstring(build_contact_xml(compiled['config']))
    world = xml.find('worldbody')
    for node in list(world):
        if node.tag != 'body':
            world.remove(node)
    body = world.find('body')
    body.set('pos', '0 0 0')
    body.set('quat', '1 0 0 0')
    if args.physics_only:
        for link in body.iter('body'):
            kept_rotor_visual = False
            for geom in list(link.findall('geom')):
                if geom.get('name', '').startswith('corner_'):
                    continue
                if link.get('name', '').startswith('wheel_') and geom.get('type')=='cylinder' and not kept_rotor_visual:
                    kept_rotor_visual = True
                    continue
                link.remove(geom)
    # Ground and initial pose belong to each rollout, not the reusable robot.
    path = args.output / 'cube.xml'
    path.write_text(ET.tostring(xml, encoding='unicode'))
    payload = {'compiled': compiled, 'snapshot': snapshot,
               'physics_only_visuals': args.physics_only,
               'mjcf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'source': adapter.reset(), 'physical_verified': False,
               'note': 'Numerical geometry; not the 152 mm reference CAD. Ground/pose are external.'}
    (args.output / 'input.json').write_text(json.dumps(payload, indent=2)+'\n')
    print(path)


if __name__ == '__main__':
    main()
