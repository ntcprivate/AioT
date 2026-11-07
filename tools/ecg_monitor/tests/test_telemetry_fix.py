"""Digital transport/GUI fixtures only. No COM is opened by these tests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import struct
import tempfile
import unittest
import time
from pathlib import Path
import numpy as np
from PySide6 import QtWidgets as W,QtGui
from ecg_monitor.protocol import StreamParser,encode,decode,samples_packet
from ecg_monitor.session import Session,demo_packet
from ecg_monitor.app import Monitor
from ecg_monitor.serial_worker import SerialWorker
from diagnose_capture import analyze


def synthetic(first,seq,t0=None):
    p=samples_packet([512+(((first+i)&0xffffffff)*17)%3072 for i in range(32)],
        first=first,seq=seq,t0=first*4000 if t0 is None else t0,boot='SYNTH_CPP')
    p.update(v=2,source='SYNTHETIC_TEST',pattern='saw17-v1');return p


class TransportFixTests(unittest.TestCase):
    def test_separate_error_counters(self):
        p=StreamParser();p.reset_connection()
        good=encode(samples_packet([1000],boot='a'))
        self.assertEqual(len(p.feed(good)),1)
        self.assertFalse(p.feed(good));self.assertEqual(p.sequence_errors,1)
        self.assertFalse(p.feed(good.replace(b'1000',b'1001') if b'1000' in good else good[:-4]+b'xxx\n'))
        bad=encode(samples_packet([2000],boot='a',seq=1,t0=4000));bad=bad[:6]+(b'0' if bad[6:7]!=b'0' else b'1')+bad[7:]
        p.feed(bad);self.assertGreaterEqual(p.crc_failures,1)
        p.feed(b'ECG1 zzzzzzzz {}\n');self.assertEqual(p.framing_errors,1)
        bad_schema=samples_packet([1000],seq=1,t0=4000);bad_schema['v']=2;p.feed(encode(bad_schema));self.assertEqual(p.schema_errors,1)
        p.reset_connection();self.assertEqual(p.errors,0);self.assertEqual(p.reconnects,1)
    def test_fragmentation_concatenation_and_injection(self):
        p=StreamParser();a=encode(synthetic(0,0));b=encode(synthetic(32,1));c=encode(synthetic(64,2))
        self.assertFalse(p.feed(a[:39]));self.assertEqual(len(p.feed(a[39:]+b)),2)
        corrupted=c[:70]+b'ESP_LOG injected\n'+c[70:]
        packets=p.feed(corrupted+encode(synthetic(96,3)))
        self.assertEqual(len(packets),1);self.assertEqual(p.crc_failures,1)
        self.assertEqual(p.lost_packets,1);self.assertEqual(p.lost_samples,32)
    def test_payload_adc_and_timestamp_rejection(self):
        for p in [samples_packet([50000]),samples_packet([65535]),samples_packet([12,13])]:
            if p['n']==2:p['data']=(struct.pack('<IHB',0,12,0)*2).hex()
            with self.assertRaises(ValueError):decode(encode(p))
        p=samples_packet([1000]);p['data']=p['data'][:-2]
        with self.assertRaises(ValueError):decode(encode(p))
        stream=StreamParser();stream.feed(encode(samples_packet([1],boot='a',seq=0,t0=4000)))
        self.assertFalse(stream.feed(encode(samples_packet([1],boot='a',seq=1,first=1,t0=4000))))
        self.assertEqual(stream.sequence_errors,1)
    def test_synthetic_reference_and_counter_wrap(self):
        p=StreamParser();self.assertEqual(len(p.feed(encode(synthetic(0xffffffe0,0xffffffff,t0=0)))),1)
        self.assertEqual(len(p.feed(encode(synthetic(0,0,t0=128000)))),1)
        bad=synthetic(32,1,t0=256000);raw=bytearray.fromhex(bad['data']);raw[4]^=1;bad['data']=raw.hex()
        self.assertFalse(p.feed(encode(bad)));self.assertEqual(p.synthetic_mismatches,1);self.assertEqual(p.crc_failures,0)
    def test_session_rejects_huge_negative_nan_atomically(self):
        for bad in (-1e18,1e18,-1,float('nan'),float('inf'),65535):
            s=Session()
            with self.assertRaises(ValueError):s.consume(dict(type='samples',boot='a',seq=0,first=0,samples=[(0,1000,0),(4000,bad,0)]),'HARDWARE')
            self.assertEqual(len(s.values),0)
    def test_wall_clock_and_device_clock_are_distinct(self):
        s=Session()
        for i in range(20):
            packet=decode(encode(synthetic(i*32,i)));packet['_received_monotonic']=10+i*.128;s.consume(packet,'SYNTHETIC_TEST')
        self.assertAlmostEqual(s.received_wall_rate(now=12.5),250,places=6)
        self.assertEqual((len(s.received_times)-1)*1e6/(s.received_times[-1]-s.received_times[0]),250)
    def test_raw_capture_preserves_bytes_and_rejections(self):
        raw=b'boot\xff\n'+encode(synthetic(0,0))+b'ECG1 00000000 {}\n'+encode(synthetic(32,2))
        chunks=[raw[i:i+17] for i in range(0,len(raw),17)]
        class Device:
            def __init__(self,**kw):self.port=None
            def open(self):assert self.dtr is False and self.rts is False
            @property
            def in_waiting(self):return len(chunks[0]) if chunks else 0
            def read(self,n):
                if chunks:return chunks.pop(0)
                worker.stop_event.set();return b''
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            worker=SerialWorker('FAKE',serial_factory=Device,capture_dir=directory);worker.start();worker.thread.join(2)
            self.assertFalse(worker.thread.is_alive());self.assertEqual(worker.capture_path.read_bytes(),raw)
            report=analyze(worker.capture_path);self.assertEqual(report['valid_samples'],64);self.assertEqual(report['crc_failures'],1)
            self.assertEqual(report['packet_gaps'],1);self.assertEqual(report['missing_samples'],0)
            rejects=worker.capture_path.with_suffix('.rejects.jsonl').read_text();self.assertIn('CRC mismatch',rejects)
    def test_cpp_production_encoder_long_run(self):
        path=Path(__file__).resolve().parents[3]/'firmware/esp32_ecg_tinyml_integrated/debug/telemetry_cpp_fixture.bin'
        if not path.exists():self.skipTest('Compile/run telemetry_wire_test.cpp fixture first')
        report=analyze(path);self.assertEqual(report['valid_samples'],16000)
        self.assertEqual(report['crc_failures']+report['schema_errors']+report['synthetic_mismatches'],0)
        self.assertEqual(report['by_boot']['CPP_FIXTURE']['received_device_time_hz'],250)
    def test_long_synthetic_stream_is_bounded(self):
        parser=StreamParser();session=Session();start=time.perf_counter();total_bytes=0
        for i in range(10000):
            raw=encode(synthetic(i*32,i));total_bytes+=len(raw)
            for packet in parser.feed(raw):session.consume(packet,'SYNTHETIC_TEST')
        self.assertEqual(session.total,320000);self.assertEqual(parser.errors,0)
        self.assertEqual(parser.lost_samples+parser.lost_packets,0);self.assertEqual(len(session.times),5000)
        duration=320000/250
        self.assertLess(time.perf_counter()-start,duration)
        path=Path(__file__).resolve().parents[1]/'reports/telemetry_long_run.json'
        path.write_text(json.dumps(dict(scope='HOST virtual21min20sec; not board validation',samples=320000,virtual_seconds=duration,
            processing_seconds=time.perf_counter()-start,bytes_per_second=total_bytes/duration,parser_errors=0,retained_points=5000),indent=2))


class GuiTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=W.QApplication.instance() or W.QApplication([])
        if not QtGui.QFontDatabase.families():QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    def setUp(self):self.w=Monitor();self.w.timer.stop();self.w.show();self.app.processEvents()
    def tearDown(self):self.w.close();self.app.processEvents()
    def test_hardware_to_demo_resets_huge_range(self):
        w=self.w;w.mode.setCurrentIndex(1);w.pause.setChecked(True);w.show_raw.setChecked(False);w.plot.setYRange(-1e18,1e18,padding=0)
        w.mode.setCurrentIndex(0);w.toggle_monitor();w.last_demo=float('inf');w.accept(decode(encode(demo_packet(0,0))),'DEMO');w.tick();self.app.processEvents()
        self.assertLess(max(abs(v) for v in w.plot.viewRange()[1]),10000)
        self.assertTrue(np.isfinite(w.raw.getData()[1]).all());self.assertEqual(w.session.origin_us,0)
        self.assertFalse(w.pause.isChecked());self.assertTrue(w.show_raw.isChecked())
    def test_demo_to_hardware_new_time_origin(self):
        w=self.w;w.toggle_monitor();w.accept(decode(encode(demo_packet(0,0))),'DEMO')
        w.mode.setCurrentIndex(1);self.assertEqual(len(w.session.values),0)
        w.monitoring=True;w.accept(decode(encode(samples_packet([2048]*32,t0=10**12))),'HARDWARE');w.tick()
        self.assertEqual(w.raw.getData()[0][0],0);self.assertEqual(w.session.origin_us,10**12)
        self.assertEqual(w.fields['ADC / generator rate'].text(),'UNKNOWN')
    def test_stop_start_and_disconnect_clear_history(self):
        w=self.w;w.toggle_monitor();w.accept(decode(encode(demo_packet(0,0))),'DEMO');w.toggle_monitor()
        self.assertEqual(len(w.session.values),0);w.toggle_monitor();self.assertEqual(w.demo_first,0)
        w.accept(decode(encode(demo_packet(0,0))),'DEMO');self.assertEqual(w.session.total,32)
        w.disconnect();self.assertEqual(len(w.session.values),0);self.assertEqual(w.last_packet,0)
    def test_poisoned_ring_is_rejected_not_clamped(self):
        w=self.w;w.toggle_monitor();w.last_demo=float('inf');w.accept(decode(encode(demo_packet(0,0))),'DEMO')
        w.session.values[3]=1e18;w.tick();self.assertEqual(len(w.session.values),0);self.assertEqual(w.display_rejections,1)
    def test_synthetic_source_stays_locked(self):
        w=self.w;w.mode.setCurrentIndex(1);w.monitoring=True;w.accept(decode(encode(synthetic(0,0))),'HARDWARE');w.tick()
        self.assertEqual(w.state.text(),'SYNTHETIC_TEST');self.assertEqual(w.fields['Classification'].text(),'UNKNOWN')
        self.assertEqual(w.fields['BPM / RR'].text(),'-- / --')
    def test_synthetic_does_not_hide_system_fault(self):
        w=self.w;w.mode.setCurrentIndex(1);w.monitoring=True
        from test_monitor import status
        w.accept(status(v=2,source='SYNTHETIC_TEST',state='SYSTEM_FAULT',reason='MODEL_OR_GOLDEN_FAILED'),'HARDWARE');w.update_status()
        self.assertEqual(w.state.text(),'SYSTEM_FAULT');self.assertEqual(w.fields['Classification'].text(),'UNKNOWN')
    def test_lost_connection_can_connect_again_without_stale_data(self):
        import queue
        from ecg_monitor.protocol import StreamParser
        class Worker:
            auto_reconnect=False;host_dropped=0
            def __init__(self):self.events=queue.Queue();self.parser=StreamParser()
            def stop(self):pass
        w=self.w;w.mode.setCurrentIndex(1);w.monitoring=True;w.worker=Worker()
        w.accept(decode(encode(samples_packet([2048]*32))),'HARDWARE')
        w.worker.events.put(('disconnected','fake cable removed'));w.tick()
        self.assertIsNone(w.worker);self.assertEqual(w.connect_button.text(),'Connect');self.assertFalse(w.monitoring)
        self.assertEqual(len(w.session.times),0)
    def test_packet_loss_does_not_relabel_adc_rate(self):
        w=self.w;w.mode.setCurrentIndex(1);w.monitoring=True
        for i in (0,2,3,5):w.accept(decode(encode(samples_packet([2048]*32,boot='a',first=i*32,seq=i,t0=i*128000))),'HARDWARE')
        from test_monitor import status
        w.accept(status(t_us=1000000,acq_hz=250,tx_hz=250,clock_last_us=764000),'HARDWARE');w.update_status()
        self.assertIn('250.00',w.fields['ADC / generator rate'].text())
        self.assertLess(float(w.fields['RX device-time rate'].text().split()[0]),180)


if __name__=='__main__':unittest.main()
