"""Regression evidence for the UNCHANGED stage-1 detector, not desired future behavior."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from scipy.signal import resample_poly
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_r_peaks import OUT, TRACE, assignment, detailed_score, rows_from, run_native

class AuditTests(unittest.TestCase):
    def replay(self, pulses, length=1600):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'adc.bin';trace_path=Path(directory)/'trace.bin'
            raw=np.full(length,2048,dtype='<i2')
            for at,height in pulses:raw[at]+=height
            raw.tofile(path)
            native=run_native(OUT/'detector_baseline.exe',path)
            audited=run_native(OUT/'detector_audit.exe',path,trace_path)
            self.assertEqual(native,audited)
            trace=np.fromfile(trace_path,dtype=TRACE)
        rows=rows_from(native)
        return [int(r[1]) for r in rows if r[0]=='peak'],[r for r in rows if r[0]=='issue'],trace

    def test_exact_historical_tolerance_and_no_reuse(self):
        ref=np.array([100,124,200]);det=np.array([112,213]);symbols=np.array(['N','V','N'])
        m,fp=assignment(ref,det)
        np.testing.assert_array_equal(m,[0,-1,-1]);np.testing.assert_array_equal(fp,[1])
        score,_,_=detailed_score(ref,det,symbols)
        self.assertEqual((score['tp'],score['fp'],score['fn']),(1,1,2))

    def test_annotation_resampling_rounding_and_impulse_alignment(self):
        indices=np.arange(3600,dtype=np.int64)
        np.testing.assert_array_equal(np.floor(indices*25/36+.5).astype(int),(indices*25+18)//36)
        for center in (360,721,1799,2500):
            raw=np.zeros(3600);raw[center]=1
            sampled=resample_poly(raw,25,36)
            expected=(center*25+18)//36
            self.assertLessEqual(abs(int(np.argmax(sampled))-expected),1)

    def test_original_warmup_is_counted(self):
        peaks,issues,trace=self.replay([(200,400),(600,400)],1000)
        self.assertEqual(peaks,[600]);self.assertFalse(issues)
        self.assertTrue(np.all(trace['age'][:500]<500))

    def test_pending_conflict_discards_two_peaks_and_restarts_warmup(self):
        peaks,issues,trace=self.replay([(600,400),(700,400),(1000,400),(1300,400)])
        self.assertEqual(peaks,[1300])
        self.assertIn(['issue','701','AMBIGUOUS_CLOSE_PEAKS'],issues)
        self.assertEqual(trace['age'][702],0)
        self.assertTrue(trace['flags'][701]&16)
        self.assertTrue(np.all(trace['age'][702:1202]<500))

    def test_refractory_suppresses_sub300ms_peak(self):
        peaks,issues,_=self.replay([(600,400),(660,400),(1000,400)],1300)
        self.assertEqual(peaks,[600,1000]);self.assertFalse(issues)

    def test_continuous_ring_crosses_256_and_512_boundaries(self):
        peaks,issues,_=self.replay([(511,400),(767,400),(1023,400)],1400)
        self.assertEqual(peaks,[511,767,1023]);self.assertFalse(issues)

    def test_absolute_floor_and_both_polarities(self):
        for sign in (-1,1):
            peaks,issues,_=self.replay([(600,sign*29),(900,sign*100)],1300)
            self.assertEqual(peaks,[900]);self.assertFalse(issues)

    def test_no_peak_reset_can_hide_later_valid_peak(self):
        peaks,issues,trace=self.replay([(600,29),(1100,400)],1400)
        self.assertEqual(peaks,[])
        self.assertIn(['issue','1001','NO_RELIABLE_R_PEAK'],issues)
        self.assertEqual(trace['age'][1002],0)

    def test_incomplete_end_window_is_not_emitted(self):
        peaks,issues,_=self.replay([(600,400)],700)
        self.assertEqual(peaks,[]);self.assertFalse(issues)

if __name__=='__main__':unittest.main()
