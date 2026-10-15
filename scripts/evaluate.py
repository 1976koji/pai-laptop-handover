"""Start a local learned-policy server and run the recorded hybrid protocol.
Requires an already prepared ROS/Gazebo environment and trained checkpoint.
"""
import argparse, json, os, subprocess, time, urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--python',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    a.out=a.out.resolve();a.checkpoint=a.checkpoint.resolve();a.python=a.python.resolve()
    if a.out.exists():raise RuntimeError('Use a new output directory; existing results are preserved')
    report=json.loads((a.checkpoint/'training_result.json').read_text())
    if report.get('status')!='trained':raise RuntimeError('Checkpoint is not trained')
    if not (a.checkpoint/'expert.safetensors').is_file():raise FileNotFoundError('expert.safetensors')
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',8765))==0:raise RuntimeError('Port 8765 is already in use')
    a.out.mkdir(parents=True)
    env=os.environ.copy();env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    env['PYTHONNOUSERSITE']='1'
    ros_env=env.copy()
    for key in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN'):
        ros_env.pop(key,None)
    with (a.out/'policy_server.log').open('w') as log:
        server=subprocess.Popen([str(a.python),str(root/'it_desk/policy.py'),'--checkpoint',str(a.checkpoint)],stdout=log,stderr=subprocess.STDOUT,env=env)
        try:
            deadline=time.monotonic()+900
            while True:
                if server.poll() is not None:raise RuntimeError('Policy server exited; inspect policy_server.log')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8765',timeout=2) as res:
                        if res.read()==b'ready':break
                except OSError:pass
                if time.monotonic()>deadline:raise RuntimeError('Policy server startup timed out')
                time.sleep(1)
            subprocess.run(['bash',str(root/'scripts/ros_run.sh'),'run_hybrid.py','--out',str(a.out/'evaluation')],check=True,env=ros_env)
            summary=json.loads((a.out/'evaluation/summary.json').read_text())
            if summary.get('hybrid_successes')!=2 or summary.get('hybrid_attempts')!=2:
                raise RuntimeError('Evaluation did not pass 2/2; preserve and inspect results')
        finally:
            if server.poll() is None:
                server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait()
if __name__=='__main__':main()
