"""GUI/transport contract tests use actual preserved golden scores, no COM."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy,json,time,unittest
from pathlib import Path
from PySide6 import QtWidgets as W
from ecg_monitor.protocol import encode,decode,StreamParser,samples_packet
from ecg_monitor.session import Session,valid_classification
from ecg_monitor.app import Monitor
from ecg_monitor.research import COUNTERS,TIMES
from test_monitor import status

FW=Path(__file__).resolve().parents[3]/'firmware/esp32_ecg_tinyml_integrated'
CASES=json.loads((FW/'debug/esp32_ai_test_only/fixture_manifest.json').read_text())['cases']

def research_packet(golden=5,**changes):
    code=CASES[golden]['code'];prob=(code+128)/256
    r=dict(mode='RESEARCH_SHADOW',source='ADC_CNN',experimental=True,state='PVC' if prob>=.52 else 'NORMAL',reason='CNN_RESEARCH_PREDICTION',p_pvc=prob,
        **dict.fromkeys(COUNTERS,0),**dict.fromkeys(TIMES,0),r_index=750)
    r.update(r_t_us=3000000,window_end_us=3508000,result_t_us=3600000,valid_until_us=5100000,latency_us=81000,prep_us=2300,classified=1,detected=1)
    r.update(changes)
    return status(v=2,t_us=4000000,golden=True,r_validated=False,quality_valid=True,quality_known=False,research=r)

def sample(flags=0,first=0,t0=3800000):
    p=samples_packet([2048]*32,first=first,t0=t0,seq=first//32+1,boot='a',flags=[flags]*32);p.update(v=2,source='HARDWARE');return decode(encode(p))

class ShadowTests(unittest.TestCase):
    def session(self,p):
        s=Session();s.consume(status(t_us=1000000),'HARDWARE');s.consume(decode(encode(p)),'HARDWARE');s.consume(sample(),'HARDWARE');return s
    def test_pvc_from_recorded_reference_and_official_locked(self):
        s=self.session(research_packet());d=s.research_display();self.assertEqual(d['prediction'],'PVC');self.assertEqual(d['probability'],135/256)
        self.assertEqual(valid_classification(s.status,'HARDWARE',4000000)[0],'UNKNOWN')
    def test_normal_from_recorded_reference(self):self.assertEqual(self.session(research_packet(0)).research_display()['prediction'],'NORMAL')
    def test_all_golden_probability_and_known_truth_errors_separate(self):
        for i in range(12):
            s=self.session(research_packet(i));d=s.research_display();self.assertEqual(d['probability'],(CASES[i]['code']+128)/256)
            self.assertEqual(d['prediction'],'PVC' if CASES[i]['code']>=6 else 'NORMAL')
    def test_instant_lead_clip_and_gap_clear(self):
        for flags,raw in [(1,2048),(2,2048),(4,65535),(8,2048),(0,4095)]:
            s=self.session(research_packet());p=sample(flags,32,3928000);p['samples']=[(t,raw,f) for t,_,f in p['samples']];s.consume(p,'HARDWARE')
            d=s.research_display();self.assertEqual(d['prediction'],'UNKNOWN');self.assertEqual(d['state'],'INVALID')
    def test_stale_without_disconnect(self):
        s=self.session(research_packet());d=s.research_display(now=s.last_received+1.2);self.assertEqual(d['prediction'],'UNKNOWN');self.assertEqual(d['reason'],'PREDICTION_STALE')
    def test_invalid_quality_blocks_prediction(self):
        for reason in ['LEADS_OFF','ADC_SATURATION','HIGH_FREQUENCY_NOISE','SAMPLE_GAP']:
            p=research_packet();p.update(state='SIGNAL_INVALID',reason=reason,quality_valid=False)
            self.assertEqual(self.session(p).research_display()['state'],'INVALID')
    def test_no_r_unknown_and_queue_full(self):
        for reason in ['NO_RELIABLE_R_PEAK','SHADOW_QUEUE_FULL','MODEL_VALIDATION_PENDING']:
            p=research_packet(state='UNKNOWN',p_pvc=None,reason=reason,r_index=-1,**dict.fromkeys(TIMES,0))
            self.assertEqual(self.session(p).research_display()['prediction'],'UNKNOWN')
    def test_schema_crc_source_and_malformed_probability(self):
        p=research_packet();p['research']['p_pvc']=.1
        with self.assertRaises(ValueError):decode(encode(p))
        p=research_packet();p['source']='SYNTHETIC_TEST'
        with self.assertRaises(ValueError):decode(encode(p))
        raw=bytearray(encode(research_packet()));raw[30]^=1;parser=StreamParser();self.assertEqual(parser.feed(raw),[]);self.assertEqual(parser.crc_failures,1)
    def test_restart_disconnect_and_stop_clear(self):
        s=self.session(research_packet());s.disconnect();self.assertEqual(s.research_display()['prediction'],'UNKNOWN')
        s=self.session(research_packet());self.assertEqual(s.research_display(connected=False)['prediction'],'UNKNOWN')
        p=sample();p['boot']='new';s.consume(p,'HARDWARE');self.assertEqual(s.research_display()['prediction'],'UNKNOWN')
    def test_old_window_cannot_return_after_invalid(self):
        s=self.session(research_packet());s.last_invalid_t=2900000
        self.assertEqual(s.research_display()['reason'],'WINDOW_OVERLAPS_INVALID_SIGNAL')
    def test_reconnect_same_boot_does_not_restore_cached_prediction(self):
        s=self.session(research_packet());self.assertEqual(s.research_display()['prediction'],'PVC');s.disconnect()
        s.consume(research_packet(),'HARDWARE');s.consume(sample(),'HARDWARE')
        self.assertEqual(s.research_display()['reason'],'WAITING_NEW_PREDICTION_AFTER_CONNECT')
        newer=research_packet(result_t_us=4200000,valid_until_us=5700000);newer['t_us']=4300000
        s.consume(newer,'HARDWARE');self.assertEqual(s.research_display()['prediction'],'PVC')
    def test_cpp_engine_and_protected_sources(self):
        import subprocess,hashlib
        r=subprocess.run([str(FW/'debug/research_shadow/unit.exe')],capture_output=True,check=True);self.assertIn(b'PASS:',r.stdout)
        before=json.loads((FW/'debug/research_shadow/before_sha256.json').read_text())
        for relative,digest in before.items():
            if any(x in relative for x in ['signal.cpp','signal.h','preprocessing.h','system_state.h','main.cpp','model\\','test_data\\','single_round']):
                self.assertEqual(hashlib.sha256((FW.parents[1]/relative).read_bytes()).hexdigest(),digest,relative)

class ShadowGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=W.QApplication.instance() or W.QApplication([])
    def setUp(self):
        self.w=Monitor();self.w.timer.stop();self.w.mode.setCurrentIndex(1);self.w.monitoring=True
        self.w.accept(status(t_us=1000000),'HARDWARE')
    def tearDown(self):self.w.close()
    def test_reference_replay_pvc_normal_then_stop(self):
        w=self.w
        self.assertTrue(any(x.text()=='EXPERIMENTAL — NOT FOR MEDICAL DIAGNOSIS.' for x in w.findChildren(W.QLabel)))
        for count,(case,label) in enumerate([(5,'PVC'),(0,'NORMAL')]):
            w.accept(decode(encode(research_packet(case))),'HARDWARE');w.accept(sample(first=count*32,t0=3800000+count*128000),'HARDWARE');w.update_status()
            self.assertEqual(w.research_fields['Latest prediction'].text(),label)
            self.assertEqual(w.fields['Classification'].text(),'UNKNOWN')
            self.assertIn('LOCKED',w.fields['AI mode'].text())
        w.toggle_monitor();self.assertEqual(w.research_fields['Latest prediction'].text(),'UNKNOWN')
    def test_disconnect_immediate_and_invalid(self):
        w=self.w;w.accept(decode(encode(research_packet())),'HARDWARE');w.accept(sample(),'HARDWARE');w.update_status()
        w.accept(sample(1,32,3928000),'HARDWARE');w.update_status();self.assertEqual(w.research_fields['Signal / validity'].text(),'INVALID')
        w.disconnect();self.assertEqual(w.research_fields['Latest prediction'].text(),'UNKNOWN')

if __name__=='__main__':unittest.main()
