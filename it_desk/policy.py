"""LeRobot PI05: original Gazebo observations -> learned absolute joint targets.
Fixed scaling, camera processing and state tokenization are identical in train/eval.
"""
from pathlib import Path
import json,io,contextlib,os,time
from request_validation import read_payload
import numpy as np
import torch
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer
from lerobot.policies.pi05.configuration_pi05 import PI05Config
from lerobot.policies.pi05.modeling_pi05 import PI05Policy
from lerobot.configs.types import PolicyFeature,FeatureType
from lerobot.utils.constants import OBS_LANGUAGE_TOKENS,OBS_LANGUAGE_ATTENTION_MASK
import lerobot.policies.pi05.modeling_pi05 as pi05_module

REVISION='22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0'
TASK='it_laptop_handover_fixed_cell'
MANIFEST=json.loads((Path(__file__).resolve().parent/'robot_manifest.json').read_text())
LOW=np.array(MANIFEST['low'],np.float32);HIGH=np.array(MANIFEST['high'],np.float32)
_original=pi05_module.create_sinusoidal_pos_embedding

def cpu_time_embedding(time,dimension,min_period,max_period,device='cpu'):
    return _original(time.to('cpu'),dimension,min_period,max_period,device=torch.device('cpu')).to(device)
pi05_module.create_sinusoidal_pos_embedding=cpu_time_embedding

def scale(q):return np.clip(2*(np.asarray(q)-LOW)/(HIGH-LOW)-1,-1,1).astype(np.float32)
def unscale(q):return np.clip((np.asarray(q)[...,:14]+1)*.5*(HIGH-LOW)+LOW,LOW,HIGH).astype(np.float32)

def load_policy(checkpoint=None):
    if not torch.cuda.is_available():raise RuntimeError('CUDA GPU required')
    if torch.version.cuda!='12.8':raise RuntimeError('Use successful CUDA 12.8 venv')
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    local=snapshot_download('lerobot/pi05_base',revision=REVISION,allow_patterns=['config.json','model.safetensors'])
    cfg=PI05Config.from_pretrained(local);cfg.device='cuda';cfg.dtype='float32';cfg.compile_model=False
    cfg.gradient_checkpointing=True;cfg.freeze_vision_encoder=True;cfg.train_expert_only=True
    cfg.n_action_steps=3;cfg.num_inference_steps=10;cfg.empty_cameras=1
    cfg.input_features={'observation.state':PolicyFeature(type=FeatureType.STATE,shape=(14,)),**{k:PolicyFeature(type=FeatureType.VISUAL,shape=(3,224,224)) for k in ('observation.images.image','observation.images.image2')}}
    cfg.output_features={'action':PolicyFeature(type=FeatureType.ACTION,shape=(14,))}
    captured=io.StringIO()
    with contextlib.redirect_stdout(captured):policy=PI05Policy.from_pretrained(local,config=cfg,strict=True)
    if 'All keys loaded successfully!' not in captured.getvalue():raise RuntimeError('Strict pretrained weight loading not confirmed')
    if checkpoint:
        from safetensors.torch import load_file
        m=json.loads((Path(checkpoint)/'training_result.json').read_text())
        if m.get('status')!='trained' or m.get('base_revision')!=REVISION or m.get('task')!=TASK:raise RuntimeError('Invalid or incomplete training checkpoint')
        state=load_file(str(Path(checkpoint)/'expert.safetensors'))
        expected={n for n,p in policy.named_parameters() if p.requires_grad}
        if set(state)!=expected:raise RuntimeError('Checkpoint trainable-parameter names differ')
        missing,unexpected=policy.load_state_dict(state,strict=False)
        if unexpected:raise RuntimeError('Unexpected checkpoint keys')
    tokenizer=AutoTokenizer.from_pretrained('google/paligemma-3b-pt-224')
    return policy,tokenizer

def batch_of(samples,tokenizer,cfg):
    prompts=[]
    for s in samples:
        state=scale(s['q'])
        # Same quantization as PI05 state tokens; fixed physical bounds in scale().
        bins=np.digitize(state,np.linspace(-1,1,256)[:-1])-1
        prompts.append('Task: use both arms to carry the '+s['target']+' laptop case from the inventory shelf to the pickup stand, State: '+' '.join(map(str,bins))+';\nAction: ')
    tokens=tokenizer(prompts,return_tensors='pt',padding='max_length',truncation=True,max_length=cfg.tokenizer_max_length)
    batch={OBS_LANGUAGE_TOKENS:tokens['input_ids'].cuda(),OBS_LANGUAGE_ATTENTION_MASK:tokens['attention_mask'].bool().cuda()}
    for key,img in [('observation.images.image','top'),('observation.images.image2','side')]:
        a=np.stack([s[img] for s in samples]);batch[key]=torch.from_numpy(a).permute(0,3,1,2).float().cuda()/255
    if 'action' in samples[0]:
        actions=np.stack([scale(s['action']) for s in samples])
        batch['action']=torch.from_numpy(actions).cuda()
    return batch

if __name__=='__main__':
    import argparse
    from http.server import BaseHTTPRequestHandler,HTTPServer
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True);a=p.parse_args()
    policy,tok=load_policy(a.checkpoint);policy.eval()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'ready')
        def do_POST(self):
            try:
                if self.path!='/act':raise ValueError('Unknown endpoint')
                payload=read_payload(self.headers,self.rfile)
                with np.load(io.BytesIO(payload),allow_pickle=False) as d:
                    s={'q':d['q'],'top':d['top'],'side':d['side'],'target':str(d['target'])}
                    if d['noise_seed'].shape!=() or d['noise_seed'].dtype.kind not in 'iu':raise ValueError('Invalid seed')
                    noise_seed=int(d['noise_seed'])
                if not 0<=noise_seed<2**63:raise ValueError('Invalid seed')
                if s['q'].shape!=(14,) or s['q'].dtype.kind not in 'fiu' or not np.isfinite(s['q']).all():raise ValueError('Invalid joints')
                for key in ('top','side'):
                    if s[key].shape!=(224,224,3) or s[key].dtype!=np.uint8:raise ValueError('Invalid image')
                if s['target'] not in ('developer','standard'):raise ValueError('Unknown instruction')
                batch=batch_of([s],tok,policy.config);start=time.perf_counter()
                torch.manual_seed(noise_seed)
                with torch.inference_mode():output=policy.predict_action_chunk(batch)[0].float().cpu().numpy()
                actions=unscale(output)
                if not np.isfinite(actions).all():raise ValueError('Nonfinite policy output')
                body=json.dumps({'actions':actions.tolist(),'seconds':time.perf_counter()-start}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            except Exception as e:
                self.send_response(500);self.end_headers();self.wfile.write(type(e).__name__.encode())
    print('POLICY_SERVER_READY',flush=True)
    HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
