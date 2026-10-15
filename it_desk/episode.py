"""IT desk closed-loop rollout and auditable simulated inventory transaction."""
from pathlib import Path
import argparse,json,time,threading,io,urllib.request,subprocess,re,os
from cooperative import projected_command
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image as ImageMsg,JointState
from std_msgs.msg import Float64
from tf2_msgs.msg import TFMessage
from rosgraph_msgs.msg import Clock
from ros_gz_interfaces.srv import ControlWorld
from kinematics import JOINTS,Kinematics,teacher_command,TEACHER_GAIN,TEACHER_MAX_OFFSET
ROOT=Path(__file__).resolve().parent

def image_array(msg):
    if msg.encoding not in ('rgb8','bgr8','rgba8','bgra8'):raise ValueError('Unexpected image encoding '+msg.encoding)
    ch=4 if 'a8' in msg.encoding else 3
    a=np.frombuffer(msg.data,dtype=np.uint8).reshape(msg.height,msg.step)[:,:msg.width*ch].reshape(msg.height,msg.width,ch)[:,:,:3].copy()
    return a[:,:,::-1].copy() if msg.encoding.startswith('bgr') else a
class Robot(Node):
    def __init__(self,out,mode,target,joint_offsets=None):
        super().__init__('it_desk_controller');self.joint_offsets=np.zeros(14) if joint_offsets is None else np.asarray(joint_offsets,dtype=float);self.out=out;self.mode=mode;self.target=target;self.phase='startup'
        self.q=None;self.images={};self.part=None;self.quat=None;self.t=None;self.lock=threading.Lock();self.times={};self.frames=[];self.last_frame=-1.;self.record=False;self.fatal=None
        self.control_service='/world/'+ET.parse(out/'world.sdf').getroot().find('world').attrib['name']+'/control'
        self.control_client=self.create_client(ControlWorld,self.control_service)
        self.pubs=[self.create_publisher(Float64,'/it/cmd/'+n,10) for n in JOINTS]
        self.create_subscription(JointState,'/it/joints',self.joints,qos_profile_sensor_data)
        self.create_subscription(Clock,'/clock',self.clock,qos_profile_sensor_data)
        self.create_subscription(TFMessage,'/model/laptop_case/pose',self.pose,qos_profile_sensor_data)
        for name in ('front','overhead'):self.create_subscription(ImageMsg,'/it/'+name,lambda m,k=name:self.camera(m,k),qos_profile_sensor_data)
    def clock(self,m):self.t=m.clock.sec+m.clock.nanosec*1e-9
    def joints(self,m):
        d={n.split('::')[-1]:v for n,v in zip(m.name,m.position)}
        if all(n in d for n in JOINTS):
            with self.lock:self.q=np.array([d[n] for n in JOINTS],np.float64)+self.joint_offsets;self.times['q']=time.monotonic()
    def pose(self,m):
        for tf in m.transforms:
            if tf.child_frame_id.split('::')[-1]=='laptop_case':
                p=tf.transform.translation;r=tf.transform.rotation
                with self.lock:self.part=np.array([p.x,p.y,p.z]);self.quat=np.array([r.x,r.y,r.z,r.w]);self.times['case']=time.monotonic()
    def camera(self,m,name):
        try:
            a=image_array(m);stamp=m.header.stamp.sec+m.header.stamp.nanosec*1e-9
            with self.lock:self.images[name]=a;self.times[name]=time.monotonic()
            if name=='front' and self.record and stamp>self.last_frame+.15:
                self.last_frame=stamp;index=len(self.frames);im=Image.fromarray(a);d=ImageDraw.Draw(im)
                d.rectangle((0,0,640,49),fill=(15,20,30));d.text((10,6),f'IT DESK | {self.mode.upper()} | {self.target} laptop',fill='white');d.text((10,26),f'{self.phase} | sim t={stamp:.1f}s | fixed dual-arm cell',fill='white')
                im.save(self.out/'frames'/f'{index:05d}.jpg',quality=90);self.frames.append([stamp,index])
        except Exception as e:self.fatal=str(e)
    def ready(self):return self.q is not None and self.part is not None and len(self.images)==2 and self.t is not None
    def snapshot(self):
        with self.lock:
            if max(time.monotonic()-t for t in self.times.values())>12:raise RuntimeError('ROS stream stalled')
            images=[np.array(Image.fromarray(self.images[k]).resize((224,224))) for k in ('front','overhead')]
            return self.q.copy(),images,self.part.copy(),self.quat.copy(),self.t
    def command(self,cmd,low,high):
        if not np.isfinite(cmd).all():raise RuntimeError('Nonfinite action')
        cmd=np.clip(cmd,low,high)
        for pub,v in zip(self.pubs,cmd-self.joint_offsets):pub.publish(Float64(data=float(v)))
        return cmd

def infer(q,ims,target,noise_seed):
    b=io.BytesIO();np.savez(b,q=q,top=ims[0],side=ims[1],target=np.array(target),noise_seed=np.array(noise_seed))
    req=urllib.request.Request('http://127.0.0.1:8765/act',data=b.getvalue(),headers={'Content-Type':'application/octet-stream'})
    with urllib.request.urlopen(req,timeout=90) as f:r=json.load(f)
    actions=np.asarray(r['actions'],np.float32)
    if actions.ndim!=2 or actions.shape[1]!=14 or not np.isfinite(actions).all():raise RuntimeError('Invalid 14-joint policy response')
    return [np.median(actions[:3],axis=0)]*3,r.get('seconds')

def set_sim_paused(node, paused):
    """Persistent ROS service client; never infer success from a missing reply."""
    started=time.monotonic();event={'pause':bool(paused),'sim_t_before':node.t,'phase':node.phase,'transport':'persistent_ros_controlworld'}
    try:
        if not node.control_client.wait_for_service(timeout_sec=15):
            raise RuntimeError('ControlWorld service unavailable: '+node.control_service)
        req=ControlWorld.Request();req.world_control.pause=bool(paused)
        future=node.control_client.call_async(req);done=threading.Event()
        future.add_done_callback(lambda _:done.set())
        if not done.wait(timeout=15):
            future.cancel();raise RuntimeError('ControlWorld response timeout; pause='+str(paused))
        response=future.result()
        if response is None or not response.success:
            raise RuntimeError('ControlWorld request rejected; pause='+str(paused))
        event['acknowledged']=True
    except Exception as exc:
        event['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        event['wall_seconds']=time.monotonic()-started;event['sim_t_after']=node.t
        with open(node.out/'world_control.jsonl','a') as f:f.write(json.dumps(event)+'\n')

def wait_running_clock(node):
    before=node.t;deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if before is not None and node.t>before:return
        time.sleep(.01)
    raise RuntimeError('Gazebo clock did not resume after positive ControlWorld response')

def wait_paused_clock(node):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        before=node.t;time.sleep(.15)
        if before is not None and abs(node.t-before)<1e-9:return
    raise RuntimeError('Gazebo clock continued after pause acknowledgement')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--target',choices=['developer','standard'],required=True);p.add_argument('--mode',choices=['teacher','policy'],required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--duration',type=float,default=75);a=p.parse_args()
    disabled=os.environ.get('PAI_PROGRESS_DISABLED','0')=='1'
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'frames').mkdir(exist_ok=True)
    layout=json.loads((a.out/'layout.json').read_text());plan=layout['joint_plan'];dest=np.array(layout['destination']);kin=Kinematics(ROOT/'openarm.urdf')
    result={'task':'it_laptop_handover_fixed_cell','mode':a.mode,'seed':a.seed,'target':a.target,'success':False,'completed':False,'mobile_base_implemented':False,'human_receipt_confirmed':False}
    result['world_control_transport']='persistent_ros_controlworld'
    result['control_architecture']='PI05 progress projection + classical bimanual path and sequencing' if a.mode=='policy' else 'classical teacher'
    result['progress_disabled']=bool(disabled)
    result['teacher_fallback']=False
    result['policy_noise_seed_rule']='episode_seed * 1000 + inference_call_index'
    result['teacher_control']={'gain':TEACHER_GAIN,'max_position_offset_rad':TEACHER_MAX_OFFSET} if a.mode=='teacher' else None
    result['start_condition']=layout.get('start_condition','legacy home start')
    events=[{'event':'request_accepted','request_id':layout['request_id'],'sku':a.target},{'event':'reserved','asset_id':layout['asset_id']}]
    rclpy.init();node=Robot(a.out,a.mode,a.target,layout.get("initial_joint_positions"));thread=threading.Thread(target=rclpy.spin,args=(node,),daemon=True);thread.start()
    paused=False
    result['inference_timing']='Gazebo paused while obtaining policy chunks; video uses simulation time' if a.mode=='policy' else 'teacher'
    trace=[];records=[];actions=[];latencies=[];phase=0;settled=None;stable=None;success=False;lifted=False;max_z=0.;last=-1
    try:
        deadline=time.monotonic()+120
        while not node.ready():
            if node.fatal:raise RuntimeError(node.fatal)
            if time.monotonic()>deadline:raise RuntimeError(f'ROS startup timeout: joints={node.q is not None}, images={list(node.images)}, case={node.part is not None}, clock={node.t}')
            time.sleep(.1)
        q,ims,initial,quat,start=node.snapshot();node.record=True;end_wall=time.monotonic()+max(900,a.duration*20);phase_start=start
        while node.t-start<a.duration:
            if node.fatal:raise RuntimeError(node.fatal)
            if time.monotonic()>end_wall:raise RuntimeError('Simulation stopped or too slow')
            if node.t-last<.195:time.sleep(.01);continue
            if a.mode=='policy' and not success and not actions:
                paused=True;set_sim_paused(node,True);wait_paused_clock(node)
            q,ims,part,quat,t=node.snapshot();last=t;projection=None;max_z=max(max_z,float(part[2]));lifted=lifted or part[2]>initial[2]+.055
            if part[2]<.50:raise RuntimeError('Case dropped below working surfaces')
            if success:cmd=q.copy();node.phase='ready_for_collection'
            else:
                stage=plan[min(phase,len(plan)-1)];goal=np.array(stage['q'])
                if a.mode=='teacher':
                    node.phase='teacher_'+stage['phase'];cmd=teacher_command(q,goal)
                else:
                    node.phase=('disabled_' if disabled else 'hybrid_')+stage['phase']
                    if not actions:
                        actions,latency=infer(q,ims,a.target,a.seed*1000+len(latencies));latencies.append(latency)
                    prediction=actions.pop(0)
                    cmd,projection=projected_command(kin,q,prediction,goal,disabled)
                # Same nominal path, tolerances and dwell conditions as the teacher.
                if np.max(np.abs(goal-q))<(.012 if stage['dwell'] else .020):
                    if settled is None:settled=t
                    if t-settled>=stage['dwell'] and phase<len(plan)-1:
                        if stage['phase']=='lift' and stage['dwell']>0 and not lifted:
                            raise RuntimeError('Arms moved but case did not lift')
                        phase+=1;settled=None;phase_start=t
                else:settled=None
                if not disabled and t-phase_start>28:
                    raise RuntimeError('Stage timeout: '+stage['phase']+'; no automatic teacher fallback')
            # Success includes a lift, a stable placement, a level case and both hands clear.
            from scipy.spatial.transform import Rotation
            tilt=float(np.arccos(np.clip(Rotation.from_quat(quat).as_matrix()[2,2],-1,1)))
            palms=[kin.frame(side,q)[:3,3] for side in ('left','right')]
            clear=all(abs(v[1]-part[1])>.19 for v in palms)
            at_dest=np.linalg.norm(part[:2]-dest[:2])<.045 and abs(part[2]-dest[2])<.025 and tilt<.15
            if lifted and at_dest and clear:
                if stable is None:stable=t
                if t-stable>=2:success=True
            else:stable=None
            actual=node.command(cmd,kin.low,kin.high)
            if paused:
                # Deliver the action while the physics world is still frozen.
                time.sleep(.03);set_sim_paused(node,False);wait_running_clock(node);paused=False
            trace.append({'sim_t':float(t),'phase':node.phase,'q':q.tolist(),'command':actual.tolist(),'case':part.tolist(),'at_destination':bool(at_dest),'supports_clear':bool(clear),'tilt_rad':tilt,'lift_confirmed':bool(lifted),'left_support':palms[0].tolist(),'right_support':palms[1].tolist(),'projection':projection,'waypoint_index':phase})
            if a.mode=='teacher':records.append((t,q,ims[0],ims[1],actual))
            if success and t-stable>4:break
        q,ims,part,quat,t=node.snapshot();node.command(q,kin.low,kin.high)
        success=bool(success and np.linalg.norm(part[:2]-dest[:2])<.045 and abs(part[2]-dest[2])<.025)
        result.update(completed=True,success=success,simulation_seconds=float(t-start),initial_case=initial.tolist(),final_case=part.tolist(),max_case_z=max_z,lift_confirmed=bool(lifted),phase=node.phase,inference_seconds=latencies)
        if success:events.append({'event':'ready_for_collection','asset_id':layout['asset_id'],'note':'Placed on pickup stand. Human pickup and loan completion are not simulated.'})
        else:events.append({'event':'handover_failed','asset_id':layout['asset_id']})
        if records:np.savez_compressed(a.out/'episode.npz',time=np.array([r[0] for r in records]),q=np.stack([r[1] for r in records]),top=np.stack([r[2] for r in records]),side=np.stack([r[3] for r in records]),action=np.stack([r[4] for r in records]),target=np.array(a.target),seed=np.array(a.seed),success=np.array(success))
    except Exception as e:
        result['error']=type(e).__name__+': '+str(e)
        result['inference_seconds']=latencies
        if node.ready():
            try:
                _,_,failure_case,_,failure_t=node.snapshot()
                result['failure_observation']={'sim_t':float(failure_t),'case':failure_case.tolist()}
            except Exception:pass
        if trace:result['last_observation']=trace[-1]
        events.append({'event':'aborted','reason':result['error']})
        if node.q is not None:node.command(node.q,kin.low,kin.high)
    finally:
        if paused:
            try:set_sim_paused(node,False)
            except Exception as resume_error:result['resume_error']=str(resume_error)
        node.record=False;(a.out/'control_trace.json').write_text(json.dumps(trace));(a.out/'frames.json').write_text(json.dumps(node.frames));(a.out/'result.json').write_text(json.dumps(result,indent=2));(a.out/'inventory_events.json').write_text(json.dumps(events,indent=2));print(json.dumps(result,indent=2),flush=True);rclpy.shutdown();thread.join(timeout=2)
    if not result['completed']:raise SystemExit(1)
if __name__=='__main__':main()
