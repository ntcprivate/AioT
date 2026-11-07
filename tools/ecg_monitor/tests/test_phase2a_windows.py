"""Tests the newly compiled production queue/detector; stage1 fixtures remain frozen."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'firmware/esp32_ecg_tinyml_integrated/debug/r_peak_phase2a'
class PendingWindowTests(unittest.TestCase):
    def test_queue_and_streaming_cpp(self):
        p=subprocess.run([str(OUT/'beat_window_test.exe')],capture_output=True,text=True,check=True)
        self.assertIn('PASS:',p.stdout)
    def test_original_signal_cpp_with_new_queue(self):
        p=subprocess.run([str(OUT/'current_signal_test.exe')],capture_output=True,text=True,check=True)
        self.assertIn('PASS:',p.stdout)
if __name__=='__main__':unittest.main()
