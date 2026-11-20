"""Synthetic evaluator tests only. Never saved or presented as a hardware run."""
import importlib.util
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('score',ROOT/'python/evaluate_v4_board_replay.py')
score=importlib.util.module_from_spec(spec);spec.loader.exec_module(score)

class TestScorer(unittest.TestCase):
    def setUp(self):
        self.protocol={'matching':{'beat_symbols':'NVL'}}
        self.record={'dataset':'MITBIH','record':'100','sha256':'streamhash'}
        self.refs=[{'sample':s,'symbol':c} for s,c in [(100,'N'),(300,'V'),(500,'L'),(700,'V'),(1100,'N')]]
        self.text='\n'.join(['ECG_ASSETS model_sha256=a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e',
            'ECG_GOLDEN_DONE samples=22 failed=0 status=PASSED',
            'V4_REPLAY_BEGIN record=MITBIH_100 samples=15360 sha256=streamhash',
            *[f'V4_PEAK r_index={p}' for p in [100,300,500,900]],
            *[f'V4_BEAT r_index={p} rejected=0 code={c} p_pvc={(c+128)/256} predicted={int(c>=98)}' for p,c in [(100,0),(300,100),(500,100),(900,100)]],
            'V4_PIPELINE_SUMMARY detected=4 classified=4 queue_drops=0 block_drops=0',
            'V4_REPLAY_END record=MITBIH_100 stream_complete=1 missed=0'])
    def run_score(self,text=None):return score.evaluate(self.text if text is None else text,self.protocol,self.record,self.refs)
    def test_other_and_missed_accounting(self):
        r=self.run_score();self.assertEqual([r[k] for k in ['TP','FP','FN','TN']],[1,1,1,1]);self.assertEqual(r['matched_OTHER'],1);self.assertEqual(r['missing_N_abstentions'],1)
    def test_one_to_one(self):
        pairs,used=score.match([{'sample':100},{'sample':110}],[105]);self.assertEqual(len(pairs),1);self.assertEqual(len(used),1)
    def test_truncation(self):
        with self.assertRaises(AssertionError):self.run_score(self.text.rsplit('\n',1)[0])
    def test_corrupt_prediction(self):
        with self.assertRaises(AssertionError):self.run_score(self.text.replace('code=100','code=99',1))
    def test_duplicate_peak(self):
        with self.assertRaises(AssertionError):self.run_score(self.text.replace('V4_PEAK r_index=300','V4_PEAK r_index=100'))
    def test_dropped_queue(self):
        with self.assertRaises(AssertionError):self.run_score(self.text.replace('queue_drops=0','queue_drops=1'))
if __name__=='__main__':unittest.main()
