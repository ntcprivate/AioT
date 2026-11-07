"""Only new GPIO demo behavior/configuration; no previous CNN evaluation rerun."""
import hashlib,json,subprocess,unittest
from pathlib import Path
FW=Path(__file__).resolve().parents[3]/'firmware/esp32_ecg_tinyml_integrated'

class BenchFeedbackTests(unittest.TestCase):
    def test_controller_event_timing_and_fail_closed(self):
        p=subprocess.run([str(FW/'debug/bench_demo/controller_test.exe')],capture_output=True,check=True)
        self.assertIn(b'PASS:',p.stdout)
    def test_default_disabled_and_no_fake_source(self):
        kconfig=(FW/'main/Kconfig.projbuild').read_text();demo=kconfig.split('config ECG_BENCH_DEMO',1)[1].split('config ',1)[0]
        self.assertIn('default n',demo);self.assertIn('depends on ECG_AI_LIVE && !ECG_HARDWARE_SELF_TEST && !ECG_GOLDEN_ALERT_DEMO',demo)
        source=(FW/'main/pipeline.cpp').read_text()
        self.assertNotIn('bench_feedback.submit(',source)
        self.assertNotIn('ECG_BENCH_PULSE',source)
        self.assertIn('BenchFeedback::select(status.bench_leads_off,invalid,unknown,status.ai,now)',source)
        self.assertIn('status.bench_leads_off=leads',source)
        self.assertIn('bench_feedback.step(now,selected)',source)
        self.assertIn('bool led=false,buzzer=false;',source)
    def test_reference_and_signal_components_untouched(self):
        manifest=json.loads((FW/'debug/bench_demo/before_sha256.json').read_text())
        for relative,digest in manifest.items():
            if any(x in relative for x in ['main\\model','main\\preprocessing.h','main\\signal.','main\\research_shadow.h','main\\main.cpp','main\\telemetry','main\\test_data']):
                self.assertEqual(hashlib.sha256((FW.parents[1]/relative).read_bytes()).hexdigest(),digest,relative)
    def test_build_modes_are_explicit(self):
        normal=(FW/'sdkconfig').read_text();bench=(FW/'debug/bench_demo/sdkconfig.bench').read_text()
        self.assertNotIn('CONFIG_ECG_BENCH_DEMO=y',normal);self.assertIn('CONFIG_ECG_BENCH_DEMO=y',bench)
        self.assertNotIn('CONFIG_ECG_HARDWARE_SELF_TEST=y',bench);self.assertNotIn('CONFIG_ECG_GOLDEN_ALERT_DEMO=y',bench)

if __name__=='__main__':unittest.main()
