"""Encode actual Gazebo camera frames at 1x simulation time (not wall-clock speed)."""
from pathlib import Path
import argparse,json,subprocess,math,tempfile
import numpy as np
from PIL import Image,ImageDraw

def encode(root,out,submission=False):
    episodes=sorted(Path(root).glob('episode_*'))
    valid=[]
    for e in episodes:
        r=json.loads((e/'result.json').read_text());frames=json.loads((e/'frames.json').read_text())
        if (submission and not r['completed']) or len(frames)<5:raise RuntimeError('Incomplete simulation recording: '+str(e))
        if submission and r['mode']!='policy':raise RuntimeError('Submission video must use policy rollouts')
        valid.append((e,r,frames))
    if not valid:raise RuntimeError('No recorded episodes')
    duration=sum(f[-1][0]-f[0][0] for _,_,f in valid)+6
    if submission and not 60<=duration<=180:raise RuntimeError(f'Submission video duration would be {duration:.1f}s; expected 60–180s. Use 2 policy episodes of 75s.')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    fps=5
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp);index=0
        def emit(im):
            nonlocal index
            im.save(temp/f'{index:06d}.png');index+=1
        intro=Image.new('RGB',(640,480),(15,20,30));d=ImageDraw.Draw(intro)
        d.text((30,110),'PAI final project | kojikoji_s',fill='white')
        d.text((30,155),'ROS 2 + Gazebo Harmonic + LeRobot PI0.5',fill='white')
        d.text((30,200),'IT service desk: bimanual laptop-case handover.',fill='white')
        d.text((30,245),'POLICY EVALUATION' if submission else 'TEACHER PREVIEW - NOT A TRAINED POLICY',fill=(120,220,160))
        d.text((30,290),'Playback: 1x simulation time (not wall-clock time)',fill='white')
        d.text((30,320),'Start: hands beside case; home approach excluded.',fill='white')
        for _ in range(3*fps):emit(intro)
        for e,r,frames in valid:
            stamps=np.array([f[0] for f in frames]);frame_ids=np.array([f[1] for f in frames]);previous=None;image=None
            for t in np.arange(stamps[0],stamps[-1],1/fps):
                j=max(0,int(np.searchsorted(stamps,t,side='right')-1));fid=frame_ids[j]
                if fid!=previous:image=Image.open(e/'frames'/f'{fid:05d}.jpg').convert('RGB');previous=fid
                emit(image)
        end=intro.copy();d=ImageDraw.Draw(end);d.rectangle((0,100,640,390),fill=(15,20,30))
        d.text((30,140),f'Observed success: {sum(r["success"] for _,r,_ in valid)} / {len(valid)}',fill='white')
        d.text((30,185),'Success: lifted, placed level, both supports withdrawn.',fill='white')
        d.text((30,230),'Fixed cell. No mobile base or human receipt simulation.',fill='white')
        d.text((30,280),'All frames rendered by Gazebo. Failures are retained.',fill='white')
        for _ in range(3*fps):emit(end)
        subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(fps),'-i',str(temp/'%06d.png'),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(out)]))
    actual=float(probe['format']['duration'])
    if submission and not 60<=actual<=180:raise RuntimeError('Encoded duration outside submission range')
    meta={'duration_seconds':actual,'fps':fps,'playback':'1x simulation time','mode':'policy' if submission else 'teacher_preview','successes':sum(r['success'] for _,r,_ in valid),'episodes':len(valid)}
    out.with_suffix('.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--submission',action='store_true');a=p.parse_args();encode(a.root,a.out,a.submission)
