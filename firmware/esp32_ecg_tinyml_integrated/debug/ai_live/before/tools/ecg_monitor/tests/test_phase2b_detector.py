from pathlib import Path
import subprocess,unittest
OUT=Path(__file__).resolve().parents[3]/'firmware/esp32_ecg_tinyml_integrated/debug/r_peak_phase2b'
class Phase2BTests(unittest.TestCase):
    def test_current_detector(self):
        p=subprocess.run([str(OUT/'detector_unit.exe')],capture_output=True,text=True,check=True);self.assertIn('PASS:',p.stdout)
    def test_preserved_fifo_with_confirmed_enqueue(self):
        p=subprocess.run([str(OUT/'window_unit.exe')],capture_output=True,text=True,check=True);self.assertIn('PASS:',p.stdout)
if __name__=='__main__':unittest.main()
