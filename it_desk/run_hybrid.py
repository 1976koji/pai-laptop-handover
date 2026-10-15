from pathlib import Path
import argparse,json,os
from run_sim import run

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 summary={'architecture':'PI05 progress + classical path','learned_geometry':False,'teacher_fallback':False,'success_criteria_changed':False,'episodes':[]}
 trials=[('hybrid',900,'developer','policy',150,False),('hybrid',901,'standard','policy',150,False)]
 for label,seed,target,mode,duration,disabled in trials:
  folder=a.out/(label+'_'+str(seed));os.environ['PAI_PROGRESS_DISABLED']='1' if disabled else '0'
  print('START',label,seed,flush=True)
  try:r=run(seed,target,mode,folder,duration)
  except Exception as e:
   if (folder/'result.json').exists():r=json.loads((folder/'result.json').read_text())
   else:r={'completed':False,'success':False,'error':type(e).__name__+': '+str(e)}
  entry={'label':label,'seed':seed,'target':target,'result':r}
  trace_path=folder/'control_trace.json'
  if trace_path.exists():
   trace=json.loads(trace_path.read_text());projections=[x['projection'] for x in trace if x.get('projection') is not None]
   entry['policy_updates']=len(projections)
   entry['positive_progress_updates']=sum(x['progress_fraction']>0 for x in projections)
   if trace:
    import numpy as np
    entry['max_joint_change_from_initial_rad']=float(np.max(np.abs(np.array([x['q'] for x in trace])-np.array(trace[0]['q']))))
  summary['episodes'].append(entry)
  summary['hybrid_successes']=sum(x['label']=='hybrid' and bool(x['result'].get('success')) for x in summary['episodes'])
  summary['hybrid_attempts']=sum(x['label']=='hybrid' for x in summary['episodes'])
  (a.out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(entry),flush=True)
  # Stop if the classical reference itself fails: fix physics before AI comparisons.
  if label=='teacher_reference' and not r.get('success'):
   summary['blocked']='Teacher reference failed';(a.out/'summary.json').write_text(json.dumps(summary,indent=2));break
if __name__=='__main__':main()
