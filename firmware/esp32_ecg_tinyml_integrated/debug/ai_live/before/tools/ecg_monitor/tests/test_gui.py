import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from PySide6 import QtWidgets as W,QtGui
from ecg_monitor.app import Monitor
from ecg_monitor.protocol import decode,encode
from ecg_monitor.session import demo_packet


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=W.QApplication.instance() or W.QApplication([])
        if not QtGui.QFontDatabase.families():QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    def setUp(self):
        self.window=Monitor();self.window.timer.stop();self.window.show();self.app.processEvents()
    def tearDown(self):self.window.close();self.app.processEvents()
    def test_demo_without_device_and_ai_lock(self):
        w=self.window;w.toggle_monitor()
        for i in range(80):w.accept(decode(encode(demo_packet(i*32,i))),'DEMO')
        w.tick();self.app.processEvents()
        self.assertEqual(w.ai_fields['Classification'].text(),'UNKNOWN');self.assertEqual(w.fields['BPM / RR'].text(),'-- / --')
        self.assertEqual(w.state.text(),'DEMO');self.assertIsNone(w.worker)
    def test_pause_keeps_recording(self):
        with tempfile.TemporaryDirectory() as d:
            w=self.window;w.toggle_monitor();w.pause.setChecked(True);w.session.start_recording(Path(d)/'session.csv')
            for i in range(5):w.accept(decode(encode(demo_packet(i*32,i))),'DEMO')
            self.assertEqual(w.session.rows,160);w.session.stop_recording()
    def test_reject_unvalidated_normal_display(self):
        w=self.window;w.mode.setCurrentIndex(1);w.monitoring=True
        from test_monitor import status
        w.accept(status(state='NORMAL',classification='NORMAL',p_pvc=.1),'HARDWARE');w.update_status()
        self.assertEqual(w.ai_fields['Classification'].text(),'UNKNOWN');self.assertEqual(w.state.text(),'WAITING')
    def test_only_stream_source_modes(self):
        self.assertEqual(self.window.mode.count(),2)
        self.assertTrue(all('LOCKED' not in self.window.mode.itemText(i) for i in range(2)))
    def test_graph_performance(self):
        w=self.window;w.monitoring=True;w.last_demo=float('inf');durations=[]
        for i in range(160):w.accept(decode(encode(demo_packet(i*32,i))),'DEMO')
        for i in range(160,260):
            w.accept(decode(encode(demo_packet(i*32,i))),'DEMO')
            start=time.perf_counter();w.tick();self.app.processEvents();durations.append(time.perf_counter()-start)
        #40ms budget for25FPS, measured actual headless Qt rendering; not UART/board.
        mean=sum(durations)/len(durations);self.assertLess(mean,.04)
        report=Path(__file__).resolve().parents[1]/'reports/gui_performance.json'
        import json
        report.write_text(json.dumps(dict(frames=100,mean_frame_ms=mean*1000,samples=w.session.total,
            platform='Qt offscreen on Windows; no COM opened',budget_ms=40),indent=2))
    def test_filtered_graph_performance(self):
        w=self.window;w.monitoring=True;w.last_demo=float('inf');w.show_filtered.setChecked(True);durations=[]
        for i in range(160):w.accept(decode(encode(demo_packet(i*32,i))),'DEMO')
        for i in range(160,260):
            w.accept(decode(encode(demo_packet(i*32,i))),'DEMO')
            start=time.perf_counter();w.tick();self.app.processEvents();durations.append(time.perf_counter()-start)
        mean=sum(durations)/len(durations);self.assertLess(mean,.04)
        import json
        (Path(__file__).resolve().parents[1]/'reports/gui_filtered_performance.json').write_text(json.dumps(
            dict(frames=100,mean_frame_ms=mean*1000,budget_ms=40,scope='Host Qt offscreen, raw plus display-only filter'),indent=2))


if __name__=='__main__':unittest.main()
