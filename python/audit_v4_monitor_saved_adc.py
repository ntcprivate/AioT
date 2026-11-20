"""Compare saved hardware bytes with Monitor decoder/session/plot. No device access."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,json,re,zlib,struct,math,csv,hashlib,time
from pathlib import Path
from collections import Counter
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tools/ecg_monitor'))
from ecg_monitor.protocol import decode,StreamParser
from ecg_monitor.session import Session
from ecg_monitor.app import Monitor
from PySide6 import QtWidgets as W
import numpy as np

out=root/'results/cnn_v4/esp32_end_to_end/monitor_adc_comparison_20261120'
out.mkdir(exist_ok=False)
paths=[root/'results/cnn_v4/esp32_end_to_end/board_runs/ADC_V4_20261120_173711/uart_raw.log',
       root/'tools/ecg_monitor/captures/20261120T120914Z_5a1c16ff.bin',
       root/'tools/ecg_monitor/captures/20261120T110601Z_7d859e74.bin']
app=W.QApplication.instance() or W.QApplication([])
results=[]
for path in paths:
    data=path.read_bytes(); session=Session(); samples=[];status=[];badcrc=0;errors=Counter();diffs=0;example=None;beats=[]
    for lineno,line in enumerate(data.splitlines(),1):
        if line.startswith(b'V4_BEAT '):beats.append(dict(re.findall(r'(\w+)=([^ ]+)',line.decode(errors='replace'))))
        m=re.fullmatch(rb'ECG1 ([0-9a-fA-F]{8}) (.*)',line.strip())
        if not m:continue
        if zlib.crc32(m[2])!=int(m[1],16):badcrc+=1;continue
        f=json.loads(m[2])
        try:p=decode(line)
        except Exception as e:errors[type(e).__name__+':'+str(e)]+=1;continue
        if p['type']=='samples':
            blob=bytes.fromhex(f['data']); manual=list(struct.iter_unpack('<IHB',blob))
            expected=[(f['t0']+dt,adc,flags) for dt,adc,flags in manual]
            assert p['samples']==expected
            samples.extend(expected)
            if example is None:
                for i,(dt,adc,flags) in enumerate(manual):
                    if adc==4095:
                        example=dict(line=lineno,first=f['first'],sample_index=f['first']+i,t_us=f['t0']+dt,
                                     raw=adc,flags=flags,packed_hex=blob[i*7:(i+1)*7].hex(),adc_bytes=blob[i*7+4:i*7+6].hex())
                        break
        else:status.append(p)
        session.consume(p,p.get('source','HARDWARE'))
        if p['type']=='samples':
            stored=dict(zip(session.times,zip(session.values,session.flags)))
            for t,v,flags in p['samples']:
                value,flag=stored[t]
                if flag!=flags or not (value==v if v<=4095 else math.isnan(value)):diffs+=1
    parser=StreamParser()
    for i in range(0,len(data),4096):parser.feed(data[i:i+4096])
    # Exercise the actual raw-curve update with stored samples, not a generated signal.
    monitor=Monitor();monitor.timer.stop();monitor.mode.setCurrentIndex(1)
    monitor.session=session;monitor.monitoring=True;monitor.last_packet=time.monotonic()
    monitor.show_filtered.setChecked(False)
    expected_y=np.array(session.values,dtype=float)
    monitor.tick();_,actual_y=monitor.raw.getData()
    plot_equal=actual_y is not None and np.array_equal(actual_y,expected_y,equal_nan=True)
    assert plot_equal
    monitor.close()
    r=dict(file=str(path.relative_to(root)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
           sample_count=len(samples),adc4095=sum(v==4095 for _,v,_ in samples),
           rail_high=sum(v>=4079 and v<=4095 for _,v,_ in samples),rail_low=sum(v<=16 for _,v,_ in samples),
           lo_plus_high=sum(bool(f&1) for _,_,f in samples),lo_minus_high=sum(bool(f&2) for _,_,f in samples),
           lo_any=sum(bool(f&3) for _,_,f in samples),lo_combinations=dict(Counter(f'{int(bool(f&1))},{int(bool(f&2))}' for _,_,f in samples)),
           status_reasons=dict(Counter(p['reason'] for p in status)),
           r_peaks_max=max((p.get('ai',{}).get('detected',0) for p in status),default=0),
           classified_max=max((p.get('ai',{}).get('classified',0) for p in status),default=0),
           r_peaks_start=status[0].get('ai',{}).get('detected') if status else None,
           classified_start=status[0].get('ai',{}).get('classified') if status else None,
           successful_beat_events=sum(b.get('rejected')=='0' for b in beats),
           boot_ids=sorted({p['boot'] for p in status}),golden=status[-1].get('golden') if status else None,
           adc_byte_example=example,session_value_mismatches=diffs,plot_raw_matches_session=plot_equal,
           independent_crc_rejects=badcrc,decoder_rejects=dict(errors),
           stream_parser=dict(crc=parser.crc_failures,schema=parser.schema_errors,framing=parser.framing_errors,
                              sequence=parser.sequence_errors,lost_samples=parser.lost_samples))
    results.append(r)
(out/'comparison.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
