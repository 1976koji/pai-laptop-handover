"""Learned forward progress on a hand-designed bimanual path.
The path and sequencing are classical control. PI05 selects progress, not geometry.
No minimum progress, timed forward drive, or teacher fallback is used.
"""
import numpy as np
from kinematics import teacher_command

def palm_positions(kin,q):
 return np.concatenate([kin.frame(side,q)[:3,3] for side in ('left','right')])

def projected_command(kin,q,predicted,waypoint,disabled=False):
 q=np.asarray(q,dtype=float);predicted=np.asarray(predicted,dtype=float);waypoint=np.asarray(waypoint,dtype=float)
 if q.shape!=(14,) or predicted.shape!=(14,) or waypoint.shape!=(14,):raise ValueError('Expected 14 joints')
 if not all(np.isfinite(v).all() for v in (q,predicted,waypoint)):raise ValueError('Nonfinite command')
 current=palm_positions(kin,q);desired=palm_positions(kin,waypoint)-current
 learned=palm_positions(kin,np.clip(predicted,kin.low,kin.high))-current
 length=float(np.linalg.norm(desired))
 # Require a positive projection to move. A current-pose output causes zero motion.
 raw=float(np.dot(learned,desired)/(length*length)) if length>1e-7 else 0.
 alpha=0. if disabled else float(np.clip(raw,0.,1.))
 nominal=teacher_command(q,waypoint)
 command=q+alpha*(nominal-q)
 return command,{'progress_fraction':alpha,'unclipped_projection':raw,
  'remaining_palm_distance_m':length,'predicted_palm_displacement_m':float(np.linalg.norm(learned)),
  'command_offset_max_rad':float(np.max(abs(command-q))),
  'disabled':bool(disabled),'learned_joint_goal':predicted.tolist()}
