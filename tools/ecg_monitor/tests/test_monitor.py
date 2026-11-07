import csv
import struct
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np
from ecg_monitor.protocol import StreamParser,encode,decode,samples_packet
from ecg_monitor.session import Session,demo_packet,valid_classification
from ecg_monitor.serial_worker import SerialWorker
from ecg_monitor.offline import measures,display_filter,capture


def status(**kw):
    p=dict(v=1,type='status',boot='a',seq=0,t_us=2000000,state='WAITING',reason='R_DETECTOR_UNVALIDATED_LIVE_DISABLED',
        source='HARDWARE',model='LOCKED',classification='UNKNOWN',p_pvc=None,led=False,buzzer=False,self_test=False)
    p.update(kw);return p


class ProtocolTests(unittest.TestCase):
    def test_crc_vector(self):
        import zlib
        self.assertEqual(zlib.crc32(b'123456789'),0xcbf43926)
    def test_fragmented_full_batch(self):
        parser=StreamParser();frame=encode(samples_packet(range(32),t0=123456789));packets=[]
        for byte in frame:packets+=parser.feed(bytes([byte]))
        self.assertEqual(len(packets),1);self.assertEqual(packets[0]['samples'][31],(123580789,31,0))
    def test_corrupt_and_truncated(self):
        for bad in [lambda f:f[:-8]+f[-7:],lambda f:f.replace(b'"fs":250',b'"fs":251'),lambda f:f[:30]+b'\n']:
            parser=StreamParser();self.assertFalse(parser.feed(bad(encode(samples_packet(range(32))))));self.assertGreater(parser.errors,0)
    def test_debug_separation_and_resync(self):
        parser=StreamParser();frames=parser.feed(b'ESP_LOG ADC normal\n'+b'X'*6000+b'\n'+encode(samples_packet([2,3])))
        self.assertEqual(len(frames),1);self.assertGreater(parser.errors,0)
    def test_lost_sequence_samples_and_reorder(self):
        p=StreamParser();p.feed(encode(samples_packet(range(32),boot='a')))
        p.feed(encode(samples_packet(range(32),boot='a',seq=2,first=64,t0=256000)))
        self.assertEqual((p.lost_packets,p.lost_samples),(1,32))
        self.assertFalse(p.feed(encode(samples_packet([1],boot='a',seq=1,first=96,t0=400000))))
    def test_reconnect_and_new_boot(self):
        p=StreamParser();p.feed(encode(samples_packet([1],boot='a',seq=9,t0=500)))
        self.assertTrue(p.feed(encode(samples_packet([1],boot='b'))))
        p.feed(b'ECG1 partial');p.reset_connection();self.assertTrue(p.feed(encode(samples_packet([1],boot='b'))))
    def test_schema(self):
        for change in [dict(v=2),dict(n=33),dict(data='00'),dict(t0=-1),dict(fs=360)]:
            p=samples_packet([1]);p.update(change)
            with self.assertRaises(ValueError):decode(encode(p))
        with self.assertRaises(ValueError):decode(encode(status(led='false')))
    def test_adc_error_and_time(self):
        p=samples_packet([65535],flags=[4]);self.assertEqual(decode(encode(p))['samples'][0][1],65535)
        with self.assertRaises(ValueError):decode(encode(samples_packet([65535])))
        p=samples_packet([1,2]);p['data']=(struct.pack('<IHB',0,1,0)*2).hex()
        with self.assertRaises(ValueError):decode(encode(p))
    def test_wraparound_sequence(self):
        p=StreamParser();p.feed(encode(status(seq=0xffffffff)));self.assertTrue(p.feed(encode(status(seq=0))))


class SafetyTests(unittest.TestCase):
    def test_no_fake_ai(self):
        for s in [status(),status(classification='NORMAL',state='NORMAL',p_pvc=.1),status(model='READY',bpm=72)]:
            self.assertEqual(valid_classification(s,'HARDWARE',2_000_000),('UNKNOWN',None))
    def test_full_gates_and_stale(self):
        from test_research_shadow import research_packet
        s=research_packet();s['ai'].update(result_t_us=1900000,valid_until_us=3400000,r_t_us=1000000,window_end_us=1508000)
        self.assertEqual(valid_classification(s,'HARDWARE',2000000),('PVC',135/256))
        for source in ['DEMO','REPLAY']:self.assertEqual(valid_classification(s,source,2000000)[0],'UNKNOWN')
        for key in ['golden','quality_valid']:
            self.assertEqual(valid_classification({**s,key:False},'HARDWARE',2000000)[0],'UNKNOWN')
        self.assertEqual(valid_classification(s,'HARDWARE',4000000)[0],'UNKNOWN')
        self.assertEqual(valid_classification({**s,'self_test':True},'HARDWARE',2000000)[0],'UNKNOWN')
    def test_record_pause_and_disconnect(self):
        with tempfile.TemporaryDirectory() as d:
            s=Session();path=Path(d)/'session.csv';s.start_recording(path)
            s.consume(decode(encode(demo_packet(0,0))),'DEMO');s.consume(decode(encode(demo_packet(32,1))),'DEMO')
            s.stop_recording()
            with path.open() as file:rows=list(csv.DictReader(file))
            self.assertEqual(len(rows),64);self.assertTrue(all(r['classification']=='UNKNOWN' and r['source']=='DEMO' for r in rows))
            self.assertTrue(path.with_suffix('.report.json').exists());s.disconnect();self.assertFalse(s.status)
    def test_no_device(self):
        def factory(**kwargs):raise OSError('no device')
        w=SerialWorker('NOT_A_PORT',serial_factory=factory);w.start();w.thread.join(1)
        self.assertEqual(w.events.get_nowait()[0],'disconnected')
    def test_recording_io_error_does_not_stop_monitor(self):
        class BrokenWriter:
            def writerow(self,row):raise OSError('disk full')
        class File:
            def close(self):pass
        s=Session();s.writer=BrokenWriter();s.csv=File()
        s.consume(decode(encode(samples_packet([2048]))),'DEMO')
        self.assertEqual(s.total,1);self.assertIsNone(s.csv);self.assertEqual(s.record_error,'disk full')
    def test_per_sample_lead_off_overrides_old_valid_ai(self):
        s=Session();s.consume(status(state='NORMAL',classification='NORMAL',p_pvc=.1,model='RUNNING',
            ai_validated=True,r_validated=True,golden=True,quality_valid=True,result_t_us=1_900_000),'HARDWARE')
        s.consume(decode(encode(samples_packet([2048],flags=[1],boot='a',seq=1,t0=2_000_000))),'HARDWARE')
        self.assertEqual(s.local_invalid_reason,'LEADS_OFF')
        s.consume(status(seq=2,quality_valid=True,quality_t_us=1_999_000),'HARDWARE')
        self.assertEqual(s.local_invalid_reason,'LEADS_OFF')
        s.consume(status(seq=3,quality_valid=True,quality_t_us=2_004_000),'HARDWARE')
        self.assertIsNone(s.local_invalid_reason)
        self.assertEqual(valid_classification(s.status,'HARDWARE',2_004_000,s.last_invalid_t)[0],'UNKNOWN')
    def test_line_settings_no_reset_command(self):
        calls=[]
        class Fake:
            def __init__(self,**kw):self.kw=kw;calls.append(kw)
            def open(self):calls.append((self.dtr,self.rts));w.stop_event.set()
            def close(self):calls.append('closed')
        w=SerialWorker('FAKE',serial_factory=Fake);w.start();w.thread.join(1)
        self.assertEqual(calls[1],(False,False));self.assertIsNone(calls[0]['port'])
    def test_demonstration_psd(self):
        t=np.arange(7500)/250;raw=2048+100*np.sin(2*np.pi*50*t)+20*np.sin(2*np.pi*t)
        before,_,_=measures(raw);after,_,_=measures(display_filter(raw)+2048)
        self.assertGreater(before['power50_fraction'],.9);self.assertLess(after['power50_fraction'],before['power50_fraction']/10)
    def test_first10_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'bad.csv';f.write_text('first10\n1,2,3\n')
            with self.assertRaises(ValueError):capture(f)
    def test_parser_throughput_and_bounded_memory(self):
        p=StreamParser();s=Session();start=time.perf_counter();size=0
        for i in range(1000):
            frame=encode(samples_packet([2048]*32,first=i*32,t0=i*128000,seq=i));size+=len(frame)
            for packet in p.feed(frame):s.consume(packet,'HARDWARE')
        elapsed=time.perf_counter()-start
        self.assertLess(elapsed,128);self.assertEqual(s.total,32000);self.assertLessEqual(len(s.times),5000)
        self.assertLess(size/128,11520*.75)


if __name__=='__main__':unittest.main()
