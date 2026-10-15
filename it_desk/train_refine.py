"""Actual imitation learning from successful original Gazebo teacher episodes."""
from pathlib import Path
import argparse,json,time,hashlib
import numpy as np
import torch
from safetensors.torch import save_file
from policy import load_policy,batch_of,REVISION,TASK

class Episodes:
    def __init__(self,root):
        self.files=sorted(Path(root).glob('episode_*/episode.npz'));self.episodes=[];self.seeds=[]
        for file in self.files:
            with np.load(file,allow_pickle=False) as d:
                if not bool(d['success']):continue
                e={k:d[k].copy() for k in d.files};self.episodes.append(e);self.seeds.append(int(d['seed']))
        if len(self.episodes)<2:raise RuntimeError('At least two successful episodes per split are required; inspect teacher failures first')
        if set(str(e['target']) for e in self.episodes)!={'developer','standard'}:raise RuntimeError('Each split needs both SKU instructions')
    def sample(self,rng,chunk):
        e=self.episodes[rng.integers(len(self.episodes))];i=rng.integers(len(e['q']))
        ids=np.minimum(np.arange(i,i+chunk),len(e['q'])-1)
        return {k:e[k][i] for k in ('q','top','side')}|{'action':e['action'][ids],'target':str(e['target'])}

def main():
    p=argparse.ArgumentParser();p.add_argument('--train',type=Path,required=True);p.add_argument('--validation',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--steps',type=int,default=500);p.add_argument('--init',type=Path,required=True);a=p.parse_args()
    if a.steps<1:raise ValueError('steps must be positive')
    a.out.mkdir(parents=True,exist_ok=True)
    if (a.out/'expert.safetensors').exists():raise RuntimeError('Checkpoint exists; use a new output directory')
    initial=json.loads((a.init/'training_result.json').read_text())
    data=Episodes(a.train);val=Episodes(a.validation)
    if set(data.seeds)&set(val.seeds):raise RuntimeError('Train/validation episode seed overlap')
    torch.manual_seed(42);rng=np.random.default_rng(42);policy,tok=load_policy(a.init)
    params=[p for p in policy.parameters() if p.requires_grad]
    optimizer=torch.optim.AdamW(params,lr=1e-5,weight_decay=.01)
    manifest={'task':TASK,'status':'running','base_revision':REVISION,'train_seeds':data.seeds,'validation_seeds':val.seeds,'steps_requested':a.steps,'model_precision':'float32','dataset_hashes':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in data.files+val.files},'task_training_completed':False}
    manifest.update(initial_checkpoint=str(a.init),initial_steps=initial.get('steps_completed'),optimizer='new AdamW optimizer; warm start from saved weights')
    def save(): (a.out/'training_result.json').write_text(json.dumps(manifest,indent=2))
    def validation():
        policy.eval();r=np.random.default_rng(1234);losses=[]
        # Identical validation samples AND diffusion noise for before/after comparison.
        with torch.random.fork_rng(devices=[0]),torch.no_grad():
            torch.manual_seed(1234)
            for _ in range(8):
                batch=batch_of([val.sample(r,policy.config.chunk_size)],tok,policy.config);loss,_=policy(batch);losses.append(float(loss))
        return float(np.mean(losses))
    save()
    try:
        manifest['validation_loss_before']=validation();save();start=time.perf_counter();history=[]
        for step in range(1,a.steps+1):
            policy.train();optimizer.zero_grad(set_to_none=True)
            batch=batch_of([data.sample(rng,policy.config.chunk_size)],tok,policy.config)
            loss,_=policy(batch)
            if not torch.isfinite(loss):raise RuntimeError('Nonfinite training loss')
            loss.backward()
            norm=torch.nn.utils.clip_grad_norm_(params,1.,error_if_nonfinite=True)
            optimizer.param_groups[0]['lr']=1e-5*min(1.,step/50)
            optimizer.step()
            history.append({'step':step,'loss':float(loss.detach()),'gradient_norm':float(norm)})
            if step%250==0:
                partial={n:p.detach().cpu().contiguous() for n,p in policy.named_parameters() if p.requires_grad}
                temporary=a.out/'partial.safetensors.tmp'
                save_file(partial,str(temporary));temporary.replace(a.out/'partial.safetensors')
                manifest['partial_weights_step']=step
                del partial
            if step%10==0 or step==1:
                print(json.dumps(history[-1]),flush=True);manifest['steps_completed']=step;save()
        manifest['validation_loss_after']=validation()
        weights={n:p.detach().cpu().contiguous() for n,p in policy.named_parameters() if p.requires_grad}
        save_file(weights,str(a.out/'expert.safetensors'))
        policy.config.save_pretrained(a.out/'config')
        manifest.update(status='trained',task_training_completed=True,steps_completed=a.steps,training_seconds=time.perf_counter()-start,history=history,peak_gpu_memory_gib=torch.cuda.max_memory_allocated()/2**30)
        save();print(json.dumps({k:v for k,v in manifest.items() if k!='history'},indent=2),flush=True)
    except Exception as e:
        manifest.update(status='failed',error=type(e).__name__+': '+str(e));save();raise
if __name__=='__main__':main()
