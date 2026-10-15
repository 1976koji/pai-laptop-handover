"""Recreate the successful isolated AI environment without ROS Python packages."""
from pathlib import Path
import subprocess,sys,argparse
p=argparse.ArgumentParser();p.add_argument('--venv',type=Path,default=Path('/content/pai_kojikoji_s/venv_cu128_v4'));a=p.parse_args()
a.venv.parent.mkdir(parents=True,exist_ok=True);python=a.venv/'bin/python'
if not python.exists():
    subprocess.run([sys.executable,'-m','pip','install','virtualenv'],check=True)
    subprocess.run([sys.executable,'-m','virtualenv',str(a.venv)],check=True)
subprocess.run([str(python),'-m','pip','--version'],check=True)
c=a.venv.parent/'pai_ai_constraints.txt';c.write_text('torch==2.11.0+cu128\ntorchvision==0.26.0+cu128\ntransformers==5.5.4\n')
subprocess.run([str(python),'-m','pip','install','torch==2.11.0+cu128','torchvision==0.26.0+cu128','--index-url','https://download.pytorch.org/whl/cu128'],check=True)
subprocess.run([str(python),'-m','pip','install','-c',str(c),'lerobot[pi]==0.6.1','transformers==5.5.4'],check=True)
print('AI environment:',python)
