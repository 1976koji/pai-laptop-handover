"""Compare trained PI05 actions to held-out teacher actions. No robot commands."""
from pathlib import Path
import argparse,json,time,traceback
import numpy as np
import torch
from policy import load_policy,batch_of,unscale,REVISION

def metrics(predicted,expected,current):
    error=np.asarray(predicted)-np.asarray(expected)
    baseline=np.broadcast_to(current,expected.shape)-expected
    return {'joint_rmse_rad':float(np.sqrt(np.mean(error**2))),
            'max_joint_error_rad':float(np.max(np.abs(error))),
            'hold_position_rmse_rad':float(np.sqrt(np.mean(baseline**2)))}

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--checkpoint',type=Path,required=True);a=p.parse_args()
    out=a.checkpoint/'policy_action_check.json'
    report={'status':'running','purpose':'offline_prediction_check_not_task_success',
            'checkpoint':str(a.checkpoint),'base_revision':REVISION,'rows':[]}
    def save():out.write_text(json.dumps(report,indent=2))
    save()
    try:
        train=json.loads((a.checkpoint/'training_result.json').read_text())
        if train.get('status')!='trained':raise RuntimeError('Training not completed')
        samples=[]
        for file in sorted((a.run/'validation').glob('episode_*/episode.npz')):
            with np.load(file,allow_pickle=False) as d:
                if not bool(d['success']):continue
                seed=int(d['seed'])
                if seed in train['train_seeds']:raise RuntimeError('Validation seed is in training set')
                q=d['q'];actions=d['action'];ts=d['time'];target=str(d['target'])
                images1=d['top'];images2=d['side']
                # Early lift/insert is where observed policy rollouts fail; include midpoint too.
                indices=sorted(set([0,int(np.argmin(abs(ts-ts[0]-2))),int(np.argmin(abs(ts-ts[0]-4))),len(ts)//2]))
                for i in indices:
                    ids=np.minimum(np.arange(i,i+3),len(ts)-1)
                    samples.append(({'q':q[i].copy(),'top':images1[i].copy(),'side':images2[i].copy(),'target':target},
                        actions[ids].copy(),{'seed':seed,'frame':i,'elapsed_sim_seconds':float(ts[i]-ts[0])}))
        if not samples:raise RuntimeError('No validation samples available')
        policy,tok=load_policy(a.checkpoint);policy.eval()
        errors=[];baselines=[]
        for index,(s,expected,info) in enumerate(samples):
            torch.manual_seed(9000+index)
            start=time.perf_counter()
            with torch.inference_mode():
                raw=policy.predict_action_chunk(batch_of([s],tok,policy.config))[0].float().cpu().numpy()
            predicted=unscale(raw[:3])
            if predicted.shape!=expected.shape or not np.isfinite(predicted).all():raise RuntimeError('Invalid predicted actions')
            row=info|metrics(predicted,expected,s['q'])
            row.update(target=s['target'],inference_seconds=time.perf_counter()-start,
                       current_q=s['q'].tolist(),teacher_actions=expected.tolist(),predicted_actions=predicted.tolist())
            report['rows'].append(row);save()
            errors.append((predicted-expected).ravel());baselines.append((s['q']-expected).ravel())
            print(f"{index+1}/{len(samples)} seed={info['seed']} frame={info['frame']} AI_RMSE={row['joint_rmse_rad']:.5f} hold_RMSE={row['hold_position_rmse_rad']:.5f}",flush=True)
        error=np.concatenate(errors);baseline=np.concatenate(baselines)
        report.update(status='completed',samples=len(samples),joint_rmse_rad=float(np.sqrt(np.mean(error**2))),
            hold_position_rmse_rad=float(np.sqrt(np.mean(baseline**2))),
            note='Teacher-action comparison only; low error does not establish physical handover success.')
        save();print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2),flush=True)
    except Exception as e:
        report.update(status='failed',error=type(e).__name__+': '+str(e));save();traceback.print_exc();raise
if __name__=='__main__':main()
