"""Encode actual Gazebo camera frames at 1x simulation time (not wall-clock speed)."""
from pathlib import Path
from functools import lru_cache
import argparse,json,subprocess,math,tempfile
import numpy as np
from PIL import Image,ImageDraw,ImageFont


@lru_cache(maxsize=4)
def caption_font(size=20):
    path=Path("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
    if not path.is_file():
        raise RuntimeError("日本語フォントがありません。環境構築セルで fonts-ipafont-gothic を導入してください。")
    return ImageFont.truetype(str(path),size)


def footer(image,playback_speed):
    image=image.copy();d=ImageDraw.Draw(image);font=caption_font(17)
    d.rectangle((0,430,640,480),fill=(15,20,30))
    d.text((12,434),f"{playback_speed:g}倍速（シミュレーション時間基準）",font=font,fill="white")
    d.text((12,457),"AI推論中は物理シミュレーションを一時停止",font=font,fill="white")
    return image

def encode(root,out,submission=False,playback_speed=1):
    episodes=sorted(Path(root).glob('episode_*'))
    valid=[]
    for e in episodes:
        r=json.loads((e/'result.json').read_text());frames=json.loads((e/'frames.json').read_text())
        if (submission and not r['completed']) or len(frames)<5:raise RuntimeError('Incomplete simulation recording: '+str(e))
        if submission and r['mode']!='policy':raise RuntimeError('Submission video must use policy rollouts')
        valid.append((e,r,frames))
    if not valid:raise RuntimeError('No recorded episodes')
    duration=sum(f[-1][0]-f[0][0] for _,_,f in valid)+16
    if submission and not 60<=duration<=180:raise RuntimeError(f'Submission video duration would be {duration:.1f}s; expected 60–180s. Use 2 policy episodes of 75s.')
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    fps=5
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp);index=0
        def emit(im):
            nonlocal index
            footer(im,playback_speed).save(temp/f'{index:06d}.png');index+=1
        font=caption_font(20)
        intro=Image.new('RGB',(640,480),(15,20,30));d=ImageDraw.Draw(intro)
        intro_lines=[
            'PAI最終課題 | kojikoji_s',
            '双腕ロボットによるPCケース搬送',
            '搬送元から受取台へ',
            'ROS 2 + Gazebo + LeRobot π',
            '学習済みAIと双腕協調制御による評価'
            if all(r.get('mode')=='policy' for _,r,_ in valid) else '教師制御の確認映像',
            'ケースの両脇に両手を配置した状態から開始',
            '待機姿勢からケースへ近づく動作は対象外',
        ]
        for i,line in enumerate(intro_lines):
            d.text((24,65+45*i),line,font=font,fill='white')
        model_x=24+d.textlength(intro_lines[3],font=font)
        d.text((model_x,65+45*3+9),'0.5',font=caption_font(13),fill='white')
        for _ in range(8*fps):emit(intro)
        for e,r,frames in valid:
            stamps=np.array([f[0] for f in frames]);frame_ids=np.array([f[1] for f in frames]);previous=None;image=None
            for t in np.arange(stamps[0],stamps[-1],1/fps):
                j=max(0,int(np.searchsorted(stamps,t,side='right')-1));fid=frame_ids[j]
                if fid!=previous:image=Image.open(e/'frames'/f'{fid:05d}.jpg').convert('RGB');previous=fid
                emit(image)
        end=Image.new('RGB',(640,480),(15,20,30));d=ImageDraw.Draw(end)
        end_lines=[
            f'搬送成功：{sum(r["success"] for _,r,_ in valid)} / {len(valid)} 試行',
            '判定：持ち上げ・水平な設置・両手の退避など',
            '固定式の双腕ロボットによる搬送',
            '移動・人の受け取り動作は対象外',
            'AI：設計済み経路に沿う進行量を調整',
            '通常の制御：搬送経路と左右の腕の協調',
            '開発時にも使用した２条件での評価',
        ]
        for i,line in enumerate(end_lines):
            d.text((24,65+45*i),line,font=font,fill='white')
        for _ in range(8*fps):emit(end)
        subprocess.run(['ffmpeg','-y','-loglevel','error','-framerate',str(fps),'-i',str(temp/'%06d.png'),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(out)]))
    actual=float(probe['format']['duration'])
    if submission and not 60<=actual<=180:raise RuntimeError('Encoded duration outside submission range')
    meta={'duration_seconds':actual,'fps':fps,'playback':'1x simulation time','caption_playback_speed':playback_speed,'mode':'hybrid_review' if all(r.get('mode')=='policy' for _,r,_ in valid) else 'teacher_preview','submission_duration_ok':60<=actual<=180,'submission_ready':False,'successes':sum(r['success'] for _,r,_ in valid),'episodes':len(valid)}
    out.with_suffix('.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--submission',action='store_true');a=p.parse_args();encode(a.root,a.out,a.submission)
