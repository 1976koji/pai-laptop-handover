"""Regression for resume, failure retention and successful data requirements."""
import tempfile,json,unittest
from pathlib import Path
import numpy as np
from collect import collect

class CollectionTests(unittest.TestCase):
    def test_resume_and_continue_after_failure(self):
        calls=[]
        def runner(seed,target,mode,out,duration):
            calls.append(seed);out.mkdir(parents=True,exist_ok=True)
            r=dict(seed=seed,target=target,mode=mode,completed=seed!=101,success=seed!=101)
            if seed==101:r.update(error='Case dropped',last_observation={'case':[0,0,.4]})
            (out/'result.json').write_text(json.dumps(r))
            if seed==101:raise RuntimeError('Episode failed')
            np.savez(out/'episode.npz',seed=seed,target=target,success=True,q=np.zeros((2,14)),action=np.zeros((2,14)),top=np.zeros((2,2,2,3)),side=np.zeros((2,2,2,3)))
            return r
        with tempfile.TemporaryDirectory() as d:
            first=collect(Path(d),2,100,150,runner);self.assertEqual(first['usable_successes'],1)
            final=collect(Path(d),4,100,150,runner)
            self.assertEqual(calls,[100,101,102,103]);self.assertEqual(final['usable_successes'],3)
            self.assertFalse(final['episodes'][1]['success'])
            (Path(d)/'episode_002/episode.npz').unlink()
            final=collect(Path(d),4,100,150,runner)
            self.assertEqual(final['usable_successes'],2);self.assertEqual(len(calls),4)

if __name__=='__main__':unittest.main()
