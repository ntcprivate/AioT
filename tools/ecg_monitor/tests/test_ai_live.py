"""Main AI_LIVE contract and CSV safety. No serial, tuning or offline evaluation."""
import csv,json,tempfile,unittest
from pathlib import Path
from ecg_monitor.protocol import decode,encode
from ecg_monitor.session import Session,valid_classification
from test_research_shadow import research_packet,sample,FW
from test_monitor import status

class MainLiveTests(unittest.TestCase):
    def test_main_payload_is_ready_without_offline_flags(self):
        p=research_packet();p['model']='READY';p.pop('r_validated',None);p.pop('ai_validated',None)
        self.assertEqual(decode(encode(p))['ai']['mode'],'AI_LIVE')
        self.assertEqual(valid_classification(p,'HARDWARE',4000000),('PVC',135/256))
    def test_old_capture_is_an_adapter_not_a_second_active_payload(self):
        p=research_packet();p['research']=p.pop('ai');p['research']['mode']='RESEARCH_SHADOW'
        self.assertEqual(valid_classification(decode(encode(p)),'HARDWARE',4000000),('PVC',135/256))
        p['ai']=dict(p['research'],mode='AI_LIVE')
        with self.assertRaises(ValueError):decode(encode(p))
    def test_csv_uses_actual_ai_without_approval_gate_and_keeps_raw_flags(self):
        s=Session();s.consume(status(t_us=1000000),'HARDWARE');p=research_packet();p.update(model='READY',r_validated=False,ai_validated=False)
        s.consume(p,'HARDWARE')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'new.csv';s.start_recording(path);s.consume(sample(),'HARDWARE');s.consume(sample(1,32,3928000),'HARDWARE');s.stop_recording()
            with path.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),64);self.assertTrue(all(r['classification']=='PVC' and float(r['p_pvc'])==135/256 for r in rows[:32]))
            self.assertTrue(all(r['classification']=='UNKNOWN' and r['p_pvc']=='' and r['lo_plus']=='1' for r in rows[32:]))
            self.assertTrue(all(r['raw_adc']=='2048' for r in rows))
    def test_current_runtime_has_no_offline_lock_or_duplicate_inference(self):
        main=FW/'main';source=(main/'pipeline.cpp').read_text();state=(main/'system_state.h').read_text()
        for removed in ['kLivePipelineValidated','classification_allowed','ECG_ENABLE_EXPERIMENTAL_LIVE','CONFIG_ECG_RESEARCH_SHADOW']:
            self.assertNotIn(removed,source+state)
        self.assertNotIn('"LOCKED"',(main/'telemetry.cpp').read_text())
        self.assertEqual(source.count('model_invoke_quantized('),1)
        self.assertNotIn('status.state=pvc',source)
        self.assertIn('SIGNAL_CHANGED_BEFORE_INFERENCE',source);self.assertIn('INPUT_QUANTIZATION_CLIPPING',source)
    def test_protected_algorithms_and_assets_unchanged(self):
        import hashlib
        manifest=json.loads((FW/'debug/ai_live/before_sha256.json').read_text())
        for relative,expected in manifest.items():
            if any(s in relative for s in ['main\\signal.cpp','main\\signal.h','main\\preprocessing.h','main\\main.cpp','main\\model\\','main\\test_data\\','single_round']):
                self.assertEqual(hashlib.sha256((FW.parents[1]/relative).read_bytes()).hexdigest(),expected,relative)

if __name__=='__main__':unittest.main()
