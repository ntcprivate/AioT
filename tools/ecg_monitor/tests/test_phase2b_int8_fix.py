import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
FW=Path(__file__).resolve().parents[3]/'firmware/esp32_ecg_tinyml_integrated'
BASE=FW/'debug/r_peak_phase2b'
class Int8FixTests(unittest.TestCase):
    def test_actual_fixed_operators_all_eight_inputs(self):
        for case in json.loads((BASE/'int8_diagnosis/operator_comparison.json').read_text()):
            source=BASE/'int8_diagnosis'/case['id']
            with tempfile.TemporaryDirectory() as temp:
                subprocess.run([str(BASE/'int8_fixed_host/full_chain.exe'),str(FW/'main/model/ecg_cnn_int8.tflite'),str(source/'input.bin'),temp,'--inspect'],check=True,capture_output=True)
                for i in range(16):self.assertEqual((Path(temp)/f'op{i}.bin').read_bytes(),(source/f'tf_op{i}.bin').read_bytes())
    def test_rounding_evidence_is_not_saturation_or_input_error(self):
        cases=json.loads((BASE/'int8_diagnosis/operator_comparison.json').read_text());self.assertEqual(len(cases),8)
        for case in cases:
            r=case['requantization'];self.assertEqual(case['first_differing_operator']['op'],14)
            self.assertTrue(r['accumulator_fits_int32']);self.assertFalse(r['saturated'])
            self.assertEqual(abs(r['single_code']-r['double_code']),1)
            self.assertEqual(r['single_code'],case['operators'][14]['tf_first'])
    def test_full_corpus_exact_and_current_adapter(self):
        r=json.loads((BASE/'int8_fixed_checks/result.json').read_text())
        self.assertEqual(r['adapter_sha256'],hashlib.sha256((FW/'main/single_round_fc.cpp').read_bytes()).hexdigest())
        self.assertEqual(r['native_exe_sha256'],hashlib.sha256((BASE/'int8_fixed_host/full_chain.exe').read_bytes()).hexdigest())
        self.assertEqual(r['fixed9425']['windows'],9425);self.assertEqual(r['fixed9425']['mismatched_codes'],0)
        self.assertEqual(r['extended33586']['windows'],33586);self.assertEqual(r['extended33586']['mismatched_codes'],0)
if __name__=='__main__':unittest.main()
