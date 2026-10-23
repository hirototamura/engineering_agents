"""Audit imported USD bodies, inertias, and corner collision geometry against frozen MJCF."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from pxr import Usd, UsdPhysics, UsdGeom

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path);args=parser.parse_args()
receipt=json.loads((args.input/'conversion.json').read_text())
stage=Usd.Stage.Open(receipt['usd_path'])
stage.GetDefaultPrim().GetVariantSet('Physics').SetVariantSelection('physx')
xml=ET.fromstring((args.input/'cube.xml').read_text())
bodies={b.attrib['name']:b for b in xml.iter('body')};checked=[];corners=[];joints=[]
for prim in stage.Traverse():
    if prim.HasAPI(UsdPhysics.RigidBodyAPI):
        source=bodies[prim.GetName()].find('inertial');api=UsdPhysics.MassAPI(prim)
        mass=float(api.GetMassAttr().Get());inertia=np.array(api.GetDiagonalInertiaAttr().Get());com=np.array(api.GetCenterOfMassAttr().Get())
        if not np.isclose(mass,float(source.get('mass')),rtol=1e-6):raise ValueError('Body mass mismatch')
        if not np.allclose(np.sort(inertia),np.sort(np.fromstring(source.get('diaginertia'),sep=' ')),rtol=1e-6,atol=1e-11):raise ValueError('Principal inertia mismatch')
        if not np.allclose(com,np.fromstring(source.get('pos'),sep=' '),atol=1e-7):raise ValueError('COM mismatch')
        checked.append({'name':prim.GetName(),'mass_kg':mass,'principal_inertia_kg_m2':inertia.tolist(),'com_m':com.tolist()})
    if prim.GetName().startswith('corner_') and prim.HasAPI(UsdPhysics.CollisionAPI):
        sphere=UsdGeom.Sphere(prim);name=prim.GetName();geom=xml.find(f".//geom[@name='{name}']")
        if not sphere or not np.isclose(sphere.GetRadiusAttr().Get(),float(geom.get('size')),rtol=1e-6):raise ValueError('Corner sphere mismatch')
        corners.append(name)
    if prim.IsA(UsdPhysics.RevoluteJoint):joints.append(prim.GetName())
if len(checked)!=4 or len(set(corners))!=8 or sorted(joints)!=['rotor_0','rotor_1','rotor_2']:
    raise ValueError('Imported body/collider/joint topology differs')
out={'status':'authored_mass_inertia_com_and_topology_match','bodies':checked,'corners':corners,'joints':joints,
     'physical_verified':False,'scope':'Authored USD values. Contact-solver equivalence and hardware fidelity require separate evidence.'}
with (args.input/'usd-audit.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
print(json.dumps(out,indent=2))
