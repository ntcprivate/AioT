"""Focused data isolation, sampling, metrics and preservation checks; no training."""
from pathlib import Path
import hashlib,json,unittest
import numpy as np
from cnn_v2_common import metrics
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v2'
class V2Checks(unittest.TestCase):
    def test_development_isolation(self):
        with np.load(OUT/'train_only.npz') as z:
            fit=z['fit'];dev=z['development'];ids=z['ids'];global_ids=z['global_indices']
            self.assertFalse(set(fit)&set(dev));self.assertEqual(len(set(fit)|set(dev)),len(global_ids))
            group=lambda r:'201_202' if r in ('201','202') else r
            self.assertFalse({group(r) for r in ids[fit]}&{group(r) for r in ids[dev]})
            with np.load(ROOT/'data/processed/mitbih_split_indices.npz') as original:
                np.testing.assert_array_equal(global_ids,original['train_indices'])
                self.assertFalse(set(global_ids)&set(original['validation_indices']))
                self.assertFalse(set(global_ids)&set(original['test_indices']))
    def test_sampling_keeps_regular_and_pvc_beats(self):
        with np.load(OUT/'train_only.npz') as z:
            fit=z['fit'];hard=z['hard'];y=z['y'];epoch=np.concatenate([fit,np.repeat(fit[hard[fit]],3)])
            self.assertTrue(np.all(y[hard]==0));self.assertEqual(set(epoch),set(fit))
            unique,count=np.unique(epoch,return_counts=True)
            np.testing.assert_array_equal(count,np.where(hard[unique],4,1))
            self.assertEqual(int(sum(y[epoch]==1)),int(sum(y[fit]==1)))
            r=json.loads((OUT/'training.json').read_text());self.assertEqual(r['epoch_samples'],len(epoch));self.assertEqual(r['hard_occurrences'],int(sum(hard[epoch])))
    def test_metrics_and_hard_negative_scope(self):
        m=metrics(np.array([0,0,1,1]),np.array([.1,.52,.2,.9]),np.array([False,True,False,False]))
        self.assertEqual(m['confusion_rows_N_V'],[[1,1],[1,1]]);self.assertEqual(m['f1'],.5)
        self.assertEqual(m['normal_neighbor_pvc']['false_positive'],1)
        e=json.loads((OUT/'evaluation.json').read_text());v=e['models']['V1_INT8']
        self.assertEqual(v['conditional']['N_to_PVC'],428);self.assertEqual(v['conditional']['PVC_to_N'],136)
        self.assertEqual(v['end_to_end']['V']['fp'],449);self.assertEqual(v['end_to_end']['V']['fn'],160)
    def test_v1_firmware_gui_and_split_unchanged(self):
        for p,digest in json.loads((OUT/'protected_sha256.json').read_text()).items():
            self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),digest,p)
if __name__=='__main__':unittest.main()
