"""Encode new hybrid recordings at 2x; preserve failed trials in review output."""
from pathlib import Path
import argparse,sys,tempfile,os,subprocess,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'it_desk'))
from video_review import encode

def main():
 p=argparse.ArgumentParser();p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():raise RuntimeError('Output exists; choose a new name')
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp)
  episodes=sorted(a.evaluation.glob('hybrid_*'))
  if len(episodes)!=2:raise RuntimeError('Expected two hybrid trial folders')
  for i,ep in enumerate(episodes):os.symlink(ep.resolve(),root/f'episode_{i:03d}')
  encode(root,root/'raw.mp4',False,playback_speed=2)
  a.out.parent.mkdir(parents=True,exist_ok=True)
  subprocess.run(['ffmpeg','-v','error','-i',str(root/'raw.mp4'),'-vf',"setpts=0.5*PTS",'-r','10','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(a.out)],check=True)
  duration=float(json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(a.out)]))['format']['duration'])
  print(json.dumps({'duration_seconds':duration,'duration_requirement_met':60<=duration<=180,'note':'Review actual trial results before submission.'}))
if __name__=='__main__':main()
