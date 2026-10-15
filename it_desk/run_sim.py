"""Start only task-owned Gazebo/bridge processes, run episodes, cleanly stop them."""
from pathlib import Path
import subprocess,os,signal,json,time,argparse,sys
import xml.etree.ElementTree as ET
from world import world
from kinematics import JOINTS
ROOT=Path(__file__).resolve().parent

def stop(p):
    if p.poll() is None:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=8)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()

def run(seed,target,mode,out,duration=75):
    out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').exists():raise RuntimeError('Output exists; choose a new run folder: '+str(out))
    sdf,layout=world(seed,target);(out/'world.sdf').write_text(sdf);(out/'layout.json').write_text(json.dumps(layout))
    env=os.environ.copy();env['GZ_PARTITION']='pai_'+str(os.getpid());env['ROS_DOMAIN_ID']='68';env['ROS_LOCALHOST_ONLY']='1';env['PYTHONNOUSERSITE']='1';env.pop('PYTHONPATH',None)
    # EGL software rendering keeps A100 VRAM available to the learned policy.
    env['GZ_CONFIG_PATH']='/usr/share/gz'
    env['LIBGL_ALWAYS_SOFTWARE']='1';env['EGL_PLATFORM']='surfaceless';env['GALLIUM_DRIVER']='llvmpipe'
    mesa=Path('/usr/share/glvnd/egl_vendor.d/50_mesa.json')
    if mesa.exists():env['__EGL_VENDOR_LIBRARY_FILENAMES']=str(mesa)
    procs=[];files=[]
    try:
        def launch(cmd,log):
            f=open(out/log,'w');files.append(f)
            p=subprocess.Popen(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);procs.append(p);return p
        sim=launch(['/usr/bin/gz','sim','-s','-r','--headless-rendering',str(out/'world.sdf')], 'gazebo.log')
        # ROS is sourced in the parent wrapper; retain its environment paths.
        env['PYTHONPATH']=os.environ.get('PYTHONPATH','')
        topics=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock','/it/joints@sensor_msgs/msg/JointState[gz.msgs.Model']
        topics += ['/it/'+k+'@sensor_msgs/msg/Image[gz.msgs.Image' for k in ('front','overhead')]
        topics += ['/model/laptop_case/pose@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V']
        topics += ['/it/cmd/'+k+'@std_msgs/msg/Float64]gz.msgs.Double' for k in JOINTS]
        bridge_path=Path('/opt/ros')/os.environ['ROS_DISTRO']/'lib/ros_gz_bridge/parameter_bridge'
        world_name=ET.fromstring(sdf).find('world').attrib['name']
        topics.append('/world/'+world_name+'/control@ros_gz_interfaces/srv/ControlWorld')
        bridge=launch([str(bridge_path),*topics],'bridge.log')
        result=subprocess.run([sys.executable,str(ROOT/'episode.py'),'--out',str(out),'--mode',mode,'--seed',str(seed),'--target',target,'--duration',str(duration)],env=env)
        if result.returncode:
            for log in ('gazebo.log','bridge.log'):
                print('\n'+log+' tail:\n'+(out/log).read_text(errors='replace')[-3500:])
            raise RuntimeError('Episode failed; result.json and logs contain diagnostics')
        return json.loads((out/'result.json').read_text())
    finally:
        for p in reversed(procs):stop(p)
        for f in files:f.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['teacher','policy'],required=True);p.add_argument('--count',type=int,default=1);p.add_argument('--seed',type=int,default=100);p.add_argument('--out',type=Path,required=True);p.add_argument('--duration',type=float,default=75);a=p.parse_args()
    results=[]
    for i in range(a.count):
        result=run(a.seed+i,'developer' if i%2==0 else 'standard',a.mode,a.out/f'episode_{i:03d}',a.duration);results.append(result)
        (a.out/'summary.json').write_text(json.dumps({'mode':a.mode,'successes':sum(r['success'] for r in results),'episodes':results},indent=2))
if __name__=='__main__':main()
