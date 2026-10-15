"""Resumable teacher collection; retain failures, never overwrite episode data."""
from pathlib import Path
import argparse,json
import numpy as np

def atomic_json(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2));temp.replace(path)

def collect(out,count,seed,duration,runner=None):
    if runner is None:
        from run_sim import run
        runner=run
    out=Path(out);out.mkdir(parents=True,exist_ok=True);results=[];consecutive_errors=0
    for i in range(count):
        folder=out/f'episode_{i:03d}';expected_seed=seed+i;target='developer' if i%2==0 else 'standard'
        cached=False
        if (folder/'result.json').exists():
            r=json.loads((folder/'result.json').read_text());cached=True
            if r.get('seed')!=expected_seed or r.get('target')!=target or r.get('mode')!='teacher':
                raise RuntimeError(f'Existing episode identity differs: {folder}; preserve it and choose another output folder')
        elif folder.exists() and any(folder.iterdir()):
            # Interrupted attempt: retain files and mark unavailable, not successful.
            r={'mode':'teacher','seed':expected_seed,'target':target,'success':False,'completed':False,'error':'Interrupted attempt without result.json; original files retained'}
            atomic_json(folder/'result.json',r);cached=True
        else:
            try:r=runner(expected_seed,target,'teacher',folder,duration)
            except Exception as exc:
                if (folder/'result.json').exists():r=json.loads((folder/'result.json').read_text())
                else:
                    folder.mkdir(parents=True,exist_ok=True)
                    r={'mode':'teacher','seed':expected_seed,'target':target,'success':False,'completed':False,'error':type(exc).__name__+': '+str(exc)}
                    atomic_json(folder/'result.json',r)
        usable=False
        if r.get('success') and r.get('completed'):
            try:
                with np.load(folder/'episode.npz',allow_pickle=False) as d:
                    usable=bool(d['success']) and int(d['seed'])==expected_seed and str(d['target'])==target and len(d['q'])>0
                    for key in ('action','top','side'):usable=usable and len(d[key])==len(d['q'])
                    usable=usable and d['q'].shape[1:]==(14,) and d['action'].shape[1:]==(14,) and np.isfinite(d['q']).all() and np.isfinite(d['action']).all()
            except (OSError,ValueError,KeyError):pass
        entry=dict(r,data_usable=bool(usable));results.append(entry)
        summary={'mode':'teacher','attempts_planned':count,'attempts_recorded':len(results),'successes':sum(bool(x.get('success')) for x in results),'usable_successes':sum(x['data_usable'] for x in results),'episodes':results}
        atomic_json(out/'summary.json',summary)
        print(f'{i+1}/{count} seed={expected_seed} cached={cached} success={r.get("success",False)} usable={usable}',flush=True)
        if r.get('error'):print('  '+r['error'],flush=True)
        # System failures with no observations are different from task failures.
        system_error=not r.get('completed') and not r.get('last_observation')
        consecutive_errors=consecutive_errors+1 if system_error and not cached else 0
        if consecutive_errors>=3:raise RuntimeError('Three consecutive infrastructure failures; inspect collection diagnostic before continuing')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--duration',type=float,default=150);a=p.parse_args()
    collect(a.out,a.count,a.seed,a.duration)
