"""Optional offline mesh-path regression check (numpy, scipy, python-fcl).

Checks every robot collision mesh against both fixture tops and columns.
Uses discrete nominal joint paths, not Gazebo dynamics or continuous collision
checking. Does not certify robot self-collision or laptop contact stability.
Usage: python mesh_path_check.py --world world.sdf --layout layout.json --out check.json
"""
from pathlib import Path
import argparse,json,xml.etree.ElementTree as E
import numpy as np
from scipy.spatial.transform import Rotation
from collision_mesh import read_triangles
from kinematics import JOINTS,vector

def pose(text):
    a=vector(text);t=np.eye(4);t[:3,3]=a[:3];t[:3,:3]=Rotation.from_euler('xyz',a[3:]).as_matrix();return t

def validate(sdf,layout):
    import fcl
    root=E.fromstring(sdf);robot=root.find('.//model[@name="openarm_it"]')
    zero={'world':np.eye(4)};zero.update({l.get('name'):pose(l.findtext('pose')) for l in robot.findall('link')})
    joints=[]
    for j in robot.findall('joint'):
        parent=j.findtext('parent');child=j.findtext('child');name=j.get('name')
        joints.append((parent,child,np.linalg.inv(zero[parent])@zero[child],JOINTS.index(name) if name in JOINTS else None,vector(j.findtext('axis/xyz','0 0 1'))))
    geometry=[]
    for link in robot.findall('link'):
        for c in link.findall('collision'):
            mesh=c.find('geometry/mesh')
            if mesh is not None:
                tri=read_triangles(Path(mesh.findtext('uri').removeprefix('file://')).read_bytes())*vector(mesh.findtext('scale','1 1 1'))
                verts=tri.reshape(-1,3);faces=np.arange(len(verts)).reshape(-1,3)
                shape=fcl.BVHModel();shape.beginModel(len(verts),len(faces));shape.addSubModel(verts,faces);shape.endModel()
            else:shape=fcl.Box(*vector(c.findtext('geometry/box/size')))
            geometry.append((link.get('name'),c.get('name'),shape,pose(c.findtext('pose'))))
    obstacles=[]
    for model in root.findall('.//world/model'):
        if model.findtext('static')!='true':continue
        name=model.get('name');mt=pose(model.findtext('pose','0 0 0 0 0 0'))
        for link in model.findall('link'):
            lt=mt@pose(link.findtext('pose','0 0 0 0 0 0'))
            for c in link.findall('collision'):
                t=lt@pose(c.findtext('pose'));shape=fcl.Box(*vector(c.findtext('geometry/box/size')))
                obstacles.append((name+'/'+c.get('name'),fcl.CollisionObject(shape,fcl.Transform(t[:3,:3],t[:3,3]))))
    initial_case=root.find('.//model[@name="laptop_case"]')
    case_tf=pose(initial_case.findtext('pose'))
    case_shape=fcl.Box(*vector(initial_case.findtext('link/collision/geometry/box/size')))
    case_obstacle=('initial_laptop_case',fcl.CollisionObject(case_shape,fcl.Transform(case_tf[:3,:3],case_tf[:3,3])))
    offsets=np.array(layout.get("initial_joint_positions",np.zeros(14)))
    samples=0
    for schedule in ('linear','synchronized_rate_limited'):
        previous=offsets.copy()
        for stage in layout['joint_plan']:
            goal=np.array(stage['q'])
            if schedule=='linear':
                n=max(1,int(np.ceil(np.max(abs(goal-previous))/.02)))
                path=[previous+(goal-previous)*a for a in np.linspace(0,1,n+1)]
            else:
                path=[previous.copy()];q=previous.copy()
                for _ in range(3000):
                    error=goal-q;q=q+error*min(1.,.20/max(float(np.max(abs(error))),1e-9))*.05
                    if np.max(abs(q-path[-1]))>=.01:path.append(q.copy())
                    if np.max(abs(q-goal))<.001:break
                path.append(goal)
            for q in path:
                samples+=1;frames={'world':pose(robot.findtext('pose'))}
                for parent,child,base,index,axis in joints:
                    t=frames[parent]@base
                    if index is not None:
                        a=np.eye(4);a[:3,:3]=Rotation.from_rotvec(axis*(q[index]-offsets[index])).as_matrix();t=t@a
                    frames[child]=t
                for link,name,shape,local in geometry:
                    t=frames[link]@local;obj=fcl.CollisionObject(shape,fcl.Transform(t[:3,:3],t[:3,3]))
                    for label,other in obstacles+([case_obstacle] if stage['phase'] in ('actuator_probe','align_shoulders','raise_elbows','approach','insert') else []):
                        if link=='openarm_body_link0' and label.startswith('pedestal/'):continue  # intended fixed mounting interface
                        if fcl.collide(obj,other,fcl.CollisionRequest(),fcl.CollisionResult()):
                            raise RuntimeError(f"Mesh intersection: {stage['phase']} {link}/{name} vs {label} ({schedule})")
            previous=goal
    return {'mesh_vs_fixtures':'passed','samples':samples,'schedules':['linear','synchronized_rate_limited'],
            'gazebo_physics_tested':False,'scope':'robot collision shapes vs all static collision boxes, except intended base mounting contact; initial case checked through insertion; discrete nominal paths only'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--world',type=Path,required=True);p.add_argument('--layout',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=validate(a.world.read_text(),json.loads(a.layout.read_text()));a.out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
