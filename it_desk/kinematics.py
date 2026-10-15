"""URDF forward kinematics and bounded IK for the official OpenArm model."""
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares
JOINTS=[f'openarm_{side}_joint{i}' for side in ('left','right') for i in range(1,8)]
PALM_OFFSET=np.array([0.,0.,-.19])
def vector(s):return np.fromstring(s,sep=' ')
def origin(el):
    t=np.eye(4)
    if el is not None:
        t[:3,3]=vector(el.get('xyz','0 0 0'));t[:3,:3]=Rotation.from_euler('xyz',vector(el.get('rpy','0 0 0'))).as_matrix()
    return t
class Kinematics:
    def __init__(self,path):
        self.root=ET.parse(path).getroot();self.joints=self.root.findall('joint');self.bychild={j.find('child').get('link'):j for j in self.joints}
        limits={j.get('name'):j.find('limit') for j in self.joints if j.get('name') in JOINTS}
        self.low=np.array([float(limits[n].get('lower')) for n in JOINTS]);self.high=np.array([float(limits[n].get('upper')) for n in JOINTS])
        self.chains={}
        for side in ('left','right'):
            c=[];name=f'openarm_{side}_ee_base_link'
            while name in self.bychild:
                j=self.bychild[name];c.insert(0,j);name=j.find('parent').get('link')
            self.chains[side]=[(origin(j.find('origin')), JOINTS.index(j.get('name')) if j.get('name') in JOINTS else None, vector(j.find('axis').get('xyz')) if j.find('axis') is not None else None) for j in c]
    def frame(self,side,q):
        t=np.eye(4);t[2,3]=.4
        for base,index,axis in self.chains[side]:
            t=t@base
            if index is not None:
                a=np.eye(4);a[:3,:3]=Rotation.from_rotvec(axis*q[index]).as_matrix();t=t@a
        t[:3,3]+=t[:3,:3]@PALM_OFFSET
        return t
    def solve(self,left,right,previous=None):
        q=np.zeros(14) if previous is None else np.array(previous).copy()
        for k,(side,xyz) in enumerate(zip(('left','right'),(left,right))):
            sl=slice(k*7,(k+1)*7);lo=self.low[sl]+1e-6;hi=self.high[sl]-1e-6
            def fun(a):
                trial=q.copy();trial[sl]=a;t=self.frame(side,trial)
                return np.r_[t[:3,3]-xyz,.12*Rotation.from_matrix(Rotation.from_euler('y',-np.pi/2).as_matrix().T@t[:3,:3]).as_rotvec()]
            starts=[np.clip(q[sl],lo,hi),np.clip(np.array([-.8 if k==0 else .8,-.4 if k==0 else .4,0,1.2,0,0,0]),lo,hi)]
            best=None
            for start in starts:
                fit=least_squares(fun,start,bounds=(lo,hi),max_nfev=160,ftol=1e-8,xtol=1e-8,gtol=1e-8)
                if best is None or np.linalg.norm(fit.fun)<np.linalg.norm(best.fun):best=fit
                if np.linalg.norm(fit.fun)<.001:break
            if np.linalg.norm(best.fun)>.005:raise RuntimeError(f'IK infeasible: {side}, target={xyz}, residual={np.linalg.norm(best.fun):.4f}')
            q[sl]=best.x
        return q

TEACHER_GAIN=0.5
TEACHER_MAX_OFFSET=0.10

def teacher_command(q,goal):
    """Conservative position look-ahead with one common scale for both arms.

    The offset cap is radians, not a guaranteed physical velocity limit.
    Gazebo contact simulation still determines actual motion and slip.
    """
    error=np.asarray(goal)-np.asarray(q)
    return q+error*min(TEACHER_GAIN,TEACHER_MAX_OFFSET/max(float(np.max(abs(error))),1e-9))

def trajectory(kin,source,dest):
    """Support both side overhangs, lift, transfer, lower, withdraw."""
    x,y,z=source;dx,dy,dz=dest
    waypoints=[('approach',(x,y,z-.045),.20),('insert',(x,y,z-.045),.125),('lift',(x,y,z+.095),.125),('transfer',(dx,dy,max(z,dz)+.095),.125),('place',(dx,dy,dz-.045),.125),('lower_support',(dx,dy,dz-.085),.125),('withdraw',(dx,dy,dz-.085),.25)]
    q=None;plan=[];last_left=None;last_right=None
    for name,p,span in waypoints:
        center=np.array(p);left=center+[0,span,0];right=center+[0,-span,0]
        samples=[1.] if q is None else np.linspace(0,1,9)[1:]
        for alpha in samples:
            l=left if last_left is None else last_left*(1-alpha)+left*alpha
            r=right if last_right is None else last_right*(1-alpha)+right*alpha
            q=kin.solve(l,r,q);plan.append({'phase':name,'q':q.tolist(),'left':l.tolist(),'right':r.tolist(),'dwell':(2.0 if name in ('lift','transfer','place') else 1.0) if alpha==1 else 0.0})
        last_left=left;last_right=right
    return plan



def validate_support_clearance(plan,source,destination):
    """Conservative AABB clearance at planned support poses (not full-arm CCD)."""
    half=np.array([.17,.0375,.0075]);margin=float('inf')
    for stage in plan:
        if stage['phase'] in ('actuator_probe','align_shoulders','raise_elbows'):continue
        for side in ('left','right'):
            center=np.array(stage[side])
            for name,p in [('shelf',source),('counter',destination)]:
                table=np.array(p)+[0,0,-.04];table_half=np.array([.16,.04,.02])
                overlap=np.minimum(center+half,table+table_half)-np.maximum(center-half,table-table_half)
                if np.all(overlap>0):raise RuntimeError(f"Support intersects {name}: {stage['phase']} {side}")
                margin=min(margin,float(np.max(-overlap)))
    return margin


def workstation_boxes(position):
    """Cantilevered top; front support column stays outside the hand workspace."""
    x,y,z=position
    return [('top',np.array([x+.15,y,z-.04]),np.array([.42,.08,.04])),
            ('stand',np.array([x+.30,y,(z-.06)/2]),np.array([.06,.06,z-.06]))]

def validate_support_sweep(kin,plan,source,destination,initial_q=None):
    """Sample oriented hand boxes for two nominal joint schedules, including startup.

    Checks all fixture boxes. This is not a full-link collision checker or a
    Gazebo physics test; actual contacts and tracking can change the trajectory.
    """
    minimum=float('inf');samples=0
    fixtures=[(label+'_'+name,c,size/2) for label,p in
              [('shelf',source),('counter',destination)]
              for name,c,size in workstation_boxes(p)]
    for schedule in ('linear','synchronized_rate_limited'):
        previous=np.zeros(14) if initial_q is None else np.array(initial_q).copy()
        for stage in plan:
            goal=np.array(stage['q'])
            if schedule=='linear':
                n=max(1,int(np.ceil(np.max(abs(goal-previous))/.005)))
                poses=[previous+(goal-previous)*a for a in np.linspace(0,1,n+1)]
            else:
                poses=[previous.copy()];q=previous.copy()
                for _ in range(5000):
                    # Nominal unit-gain actuator response; sample shared teacher command at 20 ms.
                    q=q+(teacher_command(q,goal)-q)*.02;poses.append(q.copy())
                    if np.max(abs(goal-q))<.001:break
                poses.append(goal)
            for q in poses:
                samples+=1
                for side in ('left','right'):
                    t=kin.frame(side,q);c=t[:3,3]
                    rot=t[:3,:3];local_half=np.array([.0075,.0375,.17])
                    axes=np.vstack((np.eye(3),rot.T,np.cross(np.eye(3)[:,None,:],rot.T[None,:,:]).reshape(-1,3)))
                    lengths=np.linalg.norm(axes,axis=1);axes=axes[lengths>1e-9]/lengths[lengths>1e-9,None]
                    radius=np.abs(axes@rot)@local_half
                    for name,center,h in fixtures:
                        gaps=np.abs(axes@(c-center))-radius-np.abs(axes)@h
                        gap=float(np.max(gaps));minimum=min(minimum,gap)
                        if gap<0:raise RuntimeError(f"Sampled hand path intersects {name}: {stage['phase']} {side} ({schedule})")
            previous=goal
    return {'minimum_separating_gap_m':minimum,'samples':samples,
            'scope':'oriented support boxes vs tops and columns; nominal joint paths only; not full-robot physics validation'}
