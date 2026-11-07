"""Virtual60-second protocol/recording load, no COM or device access."""
import json
from pathlib import Path
import time
from ecg_monitor.protocol import StreamParser,encode,samples_packet
from ecg_monitor.session import Session

p=StreamParser();session=Session();seq=0;byte_count=0;start=time.perf_counter();status_count=0
for batch in range(469):
    packet=samples_packet([2048]*32,first=batch*32,t0=batch*128000,seq=seq,boot='HOST_LOAD');seq+=1
    packet.update(v=2,source='HARDWARE',pattern='none')
    frame=b'\n'+encode(packet);byte_count+=len(frame)
    for row in p.feed(frame):session.consume(row,'REPLAY')
    if batch%4==0:
        s=dict(v=2,type='status',boot='HOST_LOAD',seq=seq,t_us=batch*128000,firmware='ecg-monitor-2',source='HARDWARE',
            state='WAITING',reason='R_DETECTOR_UNVALIDATED_LIVE_DISABLED',model='LOCKED',golden=True,classification='UNKNOWN',
            p_pvc=None,threshold=.52,r_validated=False,bpm=None,rr_ms=None,led=False,buzzer=False,self_test=False,
            clip_count=0,ptp=100,diff_percent=15.0,power50_ratio=.1,baseline_delta=0,quality_known=True,quality_valid=True,
            quality_t_us=batch*128000,tx_dropped=0,write_errors=0,r_peaks=[],adc_errors=0,missed_est=0,late=0,snapshot_errors=0,
            rail_margin=16,diff_limit=25)
        s.update(firmware='ecg-monitor-2',baud=115200,uart_baud_actual=115200,sample_attempts=(batch+1)*32,
            tx_samples=(batch+1)*32,tx_bytes=byte_count,acq_hz=250.,tx_hz=250.,dt_mean_us=4000.,
            dt_min_us=4000,dt_max_us=4000,clock_last_us=batch*128000,
            format_errors=0,uart_write_errors=0,uart_tx_timeouts=0)
        seq+=1;frame=b'\n'+encode(s);byte_count+=len(frame);status_count+=1
        for row in p.feed(frame):session.consume(row,'REPLAY')
elapsed=time.perf_counter()-start;duration=469*32/250
result=dict(scope='HOST simulated serial protocol only, not hardware bandwidth/latency measurement',
    samples=session.total,virtual_seconds=duration,status_packets=status_count,parser_errors=p.errors,
    bytes_per_second=byte_count/duration,uart_capacity_8n1=115200/10,uart_fraction=byte_count/duration/(115200/10),
    host_processing_seconds=elapsed,sample_points_retained=len(session.times),lost_packets=p.lost_packets)
assert p.errors==0 and p.lost_packets==0 and result['uart_fraction']<.75 and elapsed<duration and len(session.times)<=5000
Path('reports/transport_load.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
