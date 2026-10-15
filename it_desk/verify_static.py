"""Honest preflight: Python, URDF, SDF and Cartesian waypoint IK; no physics claim."""
from pathlib import Path
import json,xml.etree.ElementTree as E
import numpy as np
import world
from check_joint_offsets import check
from kinematics import Kinematics,JOINTS
ROOT=Path(__file__).resolve().parent

def verify(root=ROOT):
    root=Path(root);world.ROOT=root;k=Kinematics(root/'openarm.urdf');residuals=[];coordinate_checks={}
    for p in ROOT.glob('*.py'):compile(p.read_text(),str(p),'exec')
    for seed in (10,11,900):
        sdf,layout=world.world(seed,'developer' if seed%2==0 else 'standard');xml=E.fromstring(sdf)
        assert len(xml.findall('.//joint[@type="revolute"]'))==14
        coordinate_checks[str(seed)]=check(sdf,k,np.array(layout['initial_joint_positions']))
        for mesh in xml.findall('.//collision/geometry/mesh'):
            assert np.all(np.fromstring(mesh.findtext('scale','1 1 1'),sep=' ')>0), 'DART collision scale must be positive'
        assert len(xml.findall('.//sensor[@type="camera"]'))==2
        for uri in xml.findall('.//mesh/uri'):assert Path(uri.text.removeprefix('file://')).exists(),uri.text
        for stage in layout['joint_plan']:
            q=np.array(stage['q']);assert np.all(q>=k.low) and np.all(q<=k.high)
            for side in ('left','right'):
                err=float(np.linalg.norm(k.frame(side,q)[:3,3]-stage[side]));residuals.append(err);assert err<.005
        (root/f'check_seed_{seed}.sdf').write_text(sdf)
    result={'python_syntax':'passed','sdf_xml':'passed','official_arm_joints':14,'mesh_paths':'passed','collision_scales':'strictly_positive','ik_max_position_error_m':max(residuals),'gazebo_contact_test':'not_run','task_training':'not_run','mobile_base':'not_implemented'}
    result['joint_coordinate_checks']=coordinate_checks
    (root/'static_validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':verify()
