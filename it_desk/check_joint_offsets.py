"""Verify posed SDF joints round-trip to the official URDF joint coordinates."""
import xml.etree.ElementTree as E
import numpy as np
from scipy.spatial.transform import Rotation
from kinematics import JOINTS,PALM_OFFSET,vector

# SDF Euler serialization near gimbal lock can lose ~1e-7 rad.
# Keep translation (metres) and orientation (radians) separate: these
# tolerances are far below the 5 mm waypoint and 25 mm task tolerances.
POSITION_TOLERANCE_M=1e-6
ROTATION_TOLERANCE_RAD=1e-6

def frame_errors(got,expected):
    if not (np.isfinite(got).all() and np.isfinite(expected).all()):
        raise RuntimeError('Non-finite SDF/URDF transform')
    position=float(np.linalg.norm(got[:3,3]-expected[:3,3]))
    rotation=float(Rotation.from_matrix(got[:3,:3]@expected[:3,:3].T).magnitude())
    if position>POSITION_TOLERANCE_M or rotation>ROTATION_TOLERANCE_RAD:
        raise RuntimeError(f'SDF/URDF joint offset mismatch: position={position:.9g} m '
                           f'(limit {POSITION_TOLERANCE_M} m), rotation={rotation:.9g} rad '
                           f'(limit {ROTATION_TOLERANCE_RAD} rad)')
    return position,rotation

def transform(text):
    a=vector(text);t=np.eye(4);t[:3,3]=a[:3];t[:3,:3]=Rotation.from_euler('xyz',a[3:]).as_matrix();return t

def check(sdf,kin,initial):
    model=E.fromstring(sdf).find('.//model[@name="openarm_it"]')
    poses={'world':np.eye(4)}
    poses.update({l.get('name'):transform(l.findtext('pose')) for l in model.findall('link')})
    joints=model.findall('joint');max_position=0.;max_rotation=0.
    for j in joints:
        if j.get('name') in JOINTS:
            i=JOINTS.index(j.get('name'));lim=j.find('axis/limit')
            assert abs(float(lim.findtext('lower'))+initial[i]-kin.low[i])<1e-9
            assert abs(float(lim.findtext('upper'))+initial[i]-kin.high[i])<1e-9
    for delta in (np.zeros(14),np.linspace(-.01,.01,14),np.linspace(.02,-.02,14)):
        q=np.clip(initial+delta,kin.low,kin.high);relative=q-initial
        frames={'world':transform(model.findtext('pose'))}
        for j in joints:
            parent=j.findtext('parent');child=j.findtext('child')
            t=frames[parent]@np.linalg.inv(poses[parent])@poses[child]
            if j.get('name') in JOINTS:
                r=np.eye(4);r[:3,:3]=Rotation.from_rotvec(vector(j.findtext('axis/xyz'))*relative[JOINTS.index(j.get('name'))]).as_matrix();t=t@r
            frames[child]=t
        for side in ('left','right'):
            got=frames[f'openarm_{side}_ee_base_link'].copy();got[:3,3]+=got[:3,:3]@PALM_OFFSET
            position,rotation=frame_errors(got,kin.frame(side,q))
            max_position=max(max_position,position);max_rotation=max(max_rotation,rotation)
    return {'max_position_error_m':max_position,'max_rotation_error_rad':max_rotation,
            'position_tolerance_m':POSITION_TOLERANCE_M,'rotation_tolerance_rad':ROTATION_TOLERANCE_RAD}
