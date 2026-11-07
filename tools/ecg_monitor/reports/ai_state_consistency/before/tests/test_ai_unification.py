"""Focused GUI/decoder checks, using preserved real golden outputs; no COM/CNN run."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6 import QtWidgets as W
from ecg_monitor.app import Monitor
from ecg_monitor.session import Session
from ecg_monitor.protocol import StreamParser,encode,decode
from test_monitor import status
from test_research_shadow import research_packet,sample,FW

def session(packet):
    s=Session();s.consume(status(t_us=1000000),'HARDWARE');s.consume(packet,'HARDWARE');s.consume(sample(),'HARDWARE');return s

class DecoderTests(unittest.TestCase):
    def test_official_approval_flags_do_not_gate_shadow(self):
        for model in ['LOCKED','READY','RUNNING','DISABLED']:
            p=research_packet();p.update(model=model,r_validated=True,ai_validated=False,f1_pass=False)
            self.assertEqual(session(decode(encode(p))).research_display()['prediction'],'PVC')
    def test_missing_object_does_not_restore_old_prediction(self):
        s=session(research_packet());self.assertEqual(s.research_display()['prediction'],'PVC')
        s.consume(status(t_us=4100000,quality_valid=True,classification='PVC',p_pvc=.99),'HARDWARE')
        d=s.research_display();self.assertEqual(d['prediction'],'UNKNOWN');self.assertIsNone(d['probability'])
        self.assertEqual(d['reason'],'FIRMWARE_AI_TELEMETRY_UNAVAILABLE')
    def test_wait_for_first_status_and_detect_status_timeout(self):
        s=Session();s.consume(sample(),'HARDWARE');self.assertEqual(s.research_display()['reason'],'WAITING_AI_TELEMETRY')
        s=session(research_packet());s.status={};self.assertEqual(s.research_display()['reason'],'AI_STATUS_TIMEOUT')
    def test_invalid_signal_outranks_missing_ai_object(self):
        p=status(state='SIGNAL_INVALID',reason='LEADS_OFF')
        d=session(p).research_display();self.assertEqual(d['state'],'INVALID');self.assertEqual(d['reason'],'LEADS_OFF')
    def test_existing_uart_capture_has_no_spurious_no_research_reason(self):
        s=Session();parser=StreamParser()
        for p in parser.feed((FW/'debug/research_shadow/hardware.bin').read_bytes()):s.consume(p,p['source'])
        d=s.research_display();self.assertEqual(parser.errors,0);self.assertEqual(d['prediction'],'UNKNOWN');self.assertEqual(d['reason'],'LEADS_OFF')
    def test_model_and_quality_readiness_still_required(self):
        for key in ['golden','quality_valid']:
            p=research_packet();p[key]=False;self.assertEqual(session(p).research_display()['prediction'],'UNKNOWN')

class SinglePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=W.QApplication.instance() or W.QApplication([])
    def setUp(self):
        self.w=Monitor();self.w.timer.stop();self.w.mode.setCurrentIndex(1);self.w.monitoring=True
        self.w.accept(status(t_us=1000000),'HARDWARE')
    def tearDown(self):self.w.close()
    def test_one_panel_large_result_and_required_fields(self):
        titles=[g.title() for g in self.w.findChildren(W.QGroupBox)]
        self.assertEqual(titles.count('AI ECG CLASSIFICATION'),1)
        self.assertFalse(any('RESEARCH AI' in t for t in titles))
        self.assertNotIn('Classification',self.w.fields);self.assertNotIn('AI mode',self.w.fields)
        self.assertIn('32px',self.w.ai_fields['Classification'].styleSheet())
        for name in ['PVC probability','CNN latency','R-peak count','Total classified beats','Reason']:self.assertIn(name,self.w.ai_fields)
    def test_known_wrong_cnn_predictions_are_displayed_unchanged(self):
        # golden1: true N -> CNN PVC; golden2: true V -> CNN NORMAL.
        for n,(case,label,prob) in enumerate([(1,'PVC (V)',50+128),(2,'NORMAL (N)',-66+128)]):
            p=research_packet(case);p.update(ai_validated=False,r_validated=False,model='LOCKED')
            self.w.accept(decode(encode(p)),'HARDWARE');self.w.accept(sample(first=n*32,t0=3800000+n*128000),'HARDWARE');self.w.update_status()
            self.assertEqual(self.w.ai_fields['Classification'].text(),label)
            self.assertEqual(self.w.ai_fields['PVC probability'].text(),f'{100*prob/256:.4f}%')
            self.assertEqual(self.w.ai_fields['CNN latency'].text(),'81.000 ms')
            self.assertEqual(self.w.ai_fields['R-peak count'].text(),'1')
            self.assertEqual(self.w.ai_fields['Total classified beats'].text(),'1')
        self.w.disconnect();self.assertEqual(self.w.ai_fields['Classification'].text(),'UNKNOWN')
    def test_legacy_normal_is_not_an_inference_fallback(self):
        self.w.accept(status(t_us=4000000,state='NORMAL',classification='NORMAL',p_pvc=.01),'HARDWARE')
        self.w.accept(sample(),'HARDWARE');self.w.update_status()
        self.assertEqual(self.w.ai_fields['Classification'].text(),'UNKNOWN')
        self.assertEqual(self.w.ai_fields['Reason'].text(),'FIRMWARE AI TELEMETRY UNAVAILABLE')
        self.assertEqual(self.w.ai_fields['Reason'].toolTip(),'FIRMWARE_AI_TELEMETRY_UNAVAILABLE')
    def test_long_reason_fits_side_panel_without_horizontal_clipping(self):
        self.w.accept(research_packet(),'HARDWARE');self.w.accept(sample(),'HARDWARE');self.w.update_status()
        self.w.show();self.app.processEvents()
        scroll=self.w.findChild(W.QScrollArea)
        self.assertLessEqual(scroll.widget().width(),scroll.viewport().width())

if __name__=='__main__':unittest.main()
