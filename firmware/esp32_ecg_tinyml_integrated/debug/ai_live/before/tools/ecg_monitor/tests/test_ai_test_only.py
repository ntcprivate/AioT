"""Fabricated unit-test marker streams only; never recorded as hardware evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_ai_test_only_bench as bench

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads((bench.OUT/'fixture_manifest.json').read_text())
        self.telemetry=dict(valid_samples=1024,by_boot={'unit':{'synthetic':False}},**{k:0 for k in ['crc_failures','framing_errors','schema_errors','sequence_errors','packet_gaps','missing_samples','synthetic_mismatches']})
        self.lines=['ECG_AI_TEST_BEGIN source=REFERENCE_TEST_ONLY not_live=1 app_elf_sha=unit synthetic=0 live_locked=1 assets_ok=1 adc_started=1']
        self.lines += [f'ECG_GOLDEN sample={i} status=EXACT_MATCH' for i in range(12)]
        self.lines+=['ECG_GOLDEN_DONE status=PASSED']
        for i,r in enumerate(self.manifest['cases']):
            pred='PVC' if (r['code']+128)/256>=.52 else 'NORMAL'
            truth=-1 if r['label']<0 else int((pred=='PVC')==bool(r['label']))
            self.lines.append(f"ECG_AI_TEST_CASE source=REFERENCE_TEST_ONLY not_live=1 case={i} id={r['id']} record={r['record']} true_label={r['symbol']} code={r['code']} reference_code={r['code']} predicted={pred} reference_predicted={pred} truth_match={truth} p_pvc={(r['code']+128)/256:.9f} status=PASS preprocessing_exact=1 stable_exact=1 repeats=30")
        self.lines+=['ECG_AI_TEST_PERF source=REFERENCE_TEST_ONLY not_live=1 memory_ok=1 measured=600 arena_used=100 arena_allocated=200 stack_free_bytes=20',
            'ECG_AI_TEST_STRESS source=REFERENCE_TEST_ONLY not_live=1 status=PASS adc_attempts_delta=1024 acq_hz=250 adc_errors_delta=0 missed_delta=0 queue_drops_delta=0 snapshot_errors_delta=0 uart_errors_delta=0 format_errors_delta=0 uart_timeouts_delta=0',
            'ECG_AI_TEST_DONE source=REFERENCE_TEST_ONLY not_live=1 status=PASS cases=20 failed=0 golden_passed=1 live_locked=1']
    def run_review(self,lines=None):
        with tempfile.TemporaryDirectory() as tmp,patch.object(bench,'analyze',return_value=self.telemetry):
            p=Path(tmp)/'unit.bin';p.write_text('\n'.join(self.lines if lines is None else lines)+'\n')
            return bench.review(p,self.manifest,'unit',False)
    def test_complete_exact_and_truth_errors_are_distinct(self):self.assertEqual(self.run_review()['status'],'PASS')
    def test_missing_character_rejected(self):
        lines=self.lines.copy();lines[14]=lines[14].replace('preprocessing_exact=1','preprocessing_exact=')
        self.assertEqual(self.run_review(lines)['status'],'FAIL')
    def test_missing_done_rejected(self):self.assertEqual(self.run_review(self.lines[:-1])['status'],'FAIL')
    def test_duplicate_case_rejected(self):self.assertEqual(self.run_review(self.lines[:-3]+[self.lines[14]]+self.lines[-3:])['status'],'FAIL')
    def test_missing_case_rejected(self):self.assertEqual(self.run_review(self.lines[:14]+self.lines[15:])['status'],'FAIL')
    def test_wrong_elf_rejected(self):
        lines=self.lines.copy();lines[0]=lines[0].replace('sha=unit','sha=wrong');self.assertEqual(self.run_review(lines)['status'],'FAIL')
    def test_telemetry_corruption_rejected(self):
        self.telemetry['crc_failures']=1;self.assertEqual(self.run_review()['status'],'FAIL')
    def test_hidden_stress_failure_rejected(self):
        lines=self.lines.copy();lines[-2]=lines[-2].replace('missed_delta=0','missed_delta=1');self.assertEqual(self.run_review(lines)['status'],'FAIL')
    def test_output_code_mismatch_rejected(self):
        lines=self.lines.copy();ref=self.manifest['cases'][0]['code'];lines[14]=lines[14].replace(f' code={ref} ',f' code={ref+1} ');self.assertEqual(self.run_review(lines)['status'],'FAIL')
    def test_original_assets_and_lock_unchanged(self):
        before=json.loads((bench.OUT/'before/sha256.json').read_text())
        for relative,expected in before.items():
            if any(s in relative for s in ['model\\','test_data\\','preprocessing.h','signal.cpp','signal.h','system_state.h','main\\main.cpp']):self.assertEqual(bench.sha(bench.ROOT/relative),expected,relative)
        self.assertIn('constexpr bool kLivePipelineValidated = false',(bench.FW/'main/system_state.h').read_text())

if __name__=='__main__':unittest.main()
