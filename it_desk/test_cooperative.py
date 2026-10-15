import unittest,numpy as np
from cooperative import projected_command
class LinearKin:
 low=np.full(14,-10.);high=np.full(14,10.)
 def frame(self,side,q):
  t=np.eye(4);i=0 if side=='left' else 7;t[:3,3]=q[i:i+3];return t
class ProjectionTests(unittest.TestCase):
 def test_no_ai_motion_no_progress(self):
  q=np.zeros(14);g=np.full(14,.2);c,m=projected_command(LinearKin(),q,q,g)
  self.assertTrue(np.array_equal(q,c));self.assertEqual(m['progress_fraction'],0.)
 def test_disabled_stays(self):
  q=np.zeros(14);g=np.full(14,.2);c,m=projected_command(LinearKin(),q,g,g,True)
  self.assertTrue(np.array_equal(q,c))
 def test_backwards_stays(self):
  q=np.zeros(14);g=np.full(14,.2);c,m=projected_command(LinearKin(),q,-g,g)
  self.assertTrue(np.array_equal(q,c))
 def test_progress_preserves_joint_direction(self):
  q=np.zeros(14);g=np.arange(14)*.02;c,m=projected_command(LinearKin(),q,g,g)
  self.assertEqual(m['progress_fraction'],1.);self.assertLessEqual(float(max(abs(c-q))),.1+1e-12)
  self.assertTrue(np.allclose(c[1:]/g[1:],c[1]/g[1]))
 def test_nan_rejected(self):
  with self.assertRaises(ValueError):projected_command(LinearKin(),np.zeros(14),np.full(14,np.nan),np.zeros(14))
if __name__=='__main__':unittest.main()
