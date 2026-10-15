"""Fetch pinned official model, expand xacro, preserve license, add task adapters."""
from pathlib import Path
import subprocess,shutil,json,xml.etree.ElementTree as ET
REVISION='c10304158f917579491b02682e02f903b948d74d'
ROOT=Path(__file__).resolve().parent

def prepare():
    repo=ROOT/'vendor/openarm_description';repo.parent.mkdir(exist_ok=True)
    if not (repo/'.git').exists():
        subprocess.run(['git','clone','https://github.com/enactic/openarm_description.git',str(repo)],check=True)
    subprocess.run(['git','-C',str(repo),'checkout','--detach',REVISION],check=True)
    actual=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    if actual!=REVISION:raise RuntimeError('Unexpected robot description revision')
    # Work on a separate expansion copy; original source and license remain intact.
    expanded=ROOT/'robot_assets'
    if expanded.exists():shutil.rmtree(expanded)
    shutil.copytree(repo,expanded,ignore=shutil.ignore_patterns('.git'))
    for p in expanded.rglob('*.xacro'):
        p.write_text(p.read_text().replace('$(find openarm_description)',str(expanded)))
    import xacro
    doc=xacro.process_file(str(expanded/'assets/robot/openarm_v2.0/urdf/openarm_v20.urdf.xacro'),mappings={'emit_grasp_frame':'true'})
    (ROOT/'openarm.urdf').write_text(doc.toxml())
    r=ET.fromstring(doc.toxml())
    from kinematics import Kinematics,JOINTS
    k=Kinematics(ROOT/'openarm.urdf')
    manifest={'robot':'OpenArm V2 official kinematics + original case-support adapters','upstream':'https://github.com/enactic/openarm_description','revision':REVISION,'license':'Apache-2.0','joints':JOINTS,'low':k.low.tolist(),'high':k.high.tolist(),'mobile_base_implemented':False,'finger_actuation':False,'end_effector':'custom compact mount and 340 mm support plate; stock gripper housing and fingers replaced','gravity_compensation':'idealized; robot link gravity disabled','self_collision':False,'case_attachment':'none; contact support only'}
    (ROOT/'robot_manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':prepare()
