"""V4 UART/GUI regression only; fabricated packets are not ECG measurements."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6 import QtWidgets as W
from ecg_monitor.protocol import encode,decode
from ecg_monitor.app import Monitor
from test_monitor import status
from test_research_shadow import research_packet,sample


def packet(code):
    score=(code+128)/256
    p=research_packet(state='PVC' if score>=.88 else 'NORMAL',p_pvc=score)
    p.update(model_version='V4',threshold=.88)
    return p


class V4ThresholdTests(unittest.TestCase):
    def test_code97_normal_code98_pvc(self):
        for code,label in [(97,'NORMAL'),(98,'PVC')]:
            self.assertEqual(decode(encode(packet(code)))['ai']['state'],label)

    def test_firmware_label_mismatch_is_rejected_not_reclassified(self):
        p=packet(97);p['ai']['state']='PVC'
        with self.assertRaises(ValueError):decode(encode(p))

    def test_v4_missing_threshold_rejected(self):
        p=packet(98);del p['threshold']
        with self.assertRaises(ValueError):decode(encode(p))

    def test_invalid_thresholds_rejected(self):
        for threshold in [True,0,1,'0.88']:
            p=packet(98);p['threshold']=threshold
            with self.assertRaises(ValueError):decode(encode(p))

    def test_gui_v4_states_and_counts(self):
        app=W.QApplication.instance() or W.QApplication([])
        for code,label in [(97,'NORMAL (N)'),(98,'PVC (V)')]:
            w=Monitor();w.timer.stop();w.mode.setCurrentIndex(1);w.monitoring=True
            try:
                w.accept(status(t_us=1000000),'HARDWARE')
                p=packet(code)
                w.accept(decode(encode(p)),'HARDWARE');w.accept(sample(),'HARDWARE');w.update_status()
                self.assertEqual(w.state.text(),'AI LIVE')
                self.assertEqual(w.ai_fields['Classification'].text(),label)
                self.assertEqual(w.ai_fields['PVC probability'].text(),f'{100*(code+128)/256:.4f}%')
                self.assertEqual(w.ai_fields['CNN latency'].text(),'81.000 ms')
                self.assertEqual(w.ai_fields['R-peak count'].text(),'1')
                self.assertEqual(w.ai_fields['Total classified beats'].text(),'1')
                p.update(state='SIGNAL_INVALID',reason='ADC_SATURATION')
                w.accept(decode(encode(p)),'HARDWARE');w.update_status()
                self.assertEqual(w.ai_fields['Classification'].text(),'UNKNOWN')
            finally:w.close()


if __name__=='__main__':unittest.main()
