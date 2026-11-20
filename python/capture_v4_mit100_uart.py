"""One authorized bench reset, bounded raw UART capture. Never flashes/retries."""
import argparse,datetime,hashlib,json,re,time
from pathlib import Path
import serial

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM3');p.add_argument('--timeout',type=float,default=240);p.add_argument('--record',choices=['MITBIH_100','INCART_PVC_V1'],default='MITBIH_100');p.add_argument('--run-dir',type=Path);p.add_argument('--bench-reset-once',action='store_true');a=p.parse_args()
    if not a.bench_reset_once:raise SystemExit('Explicit --bench-reset-once required')
    root=Path(__file__).resolve().parents[1];stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out=a.run_dir.resolve() if a.run_dir else root/'results/cnn_v4/esp32_end_to_end/board_runs'/(a.record+'_'+stamp)
    if not out.resolve().is_relative_to(root):raise SystemExit('Run directory must stay inside workspace')
    out.mkdir(parents=True,exist_ok=bool(a.run_dir))
    path=out/'uart_raw.log';status={'port':a.port,'baud':115200,'timeout_seconds':a.timeout,'reset_commands':0,'flash':False,'log':str(path),'status':'CAPTURING'}
    ser=serial.Serial(port=None,baudrate=115200,timeout=.2,write_timeout=1,dsrdtr=False,rtscts=False)
    ser.dtr=False;ser.rts=False;ser.port=a.port
    start=time.monotonic();pending=b'';boot_count=0;ids=set();goldens=[];markers={};last_report=0;end_at=None;error=None
    try:
        # File exists before port open and EN pulse; no buffered old session retained.
        with path.open('xb',buffering=0) as raw:
            ser.open();ser.reset_input_buffer()
            print('CAPTURE_FILE '+str(path),flush=True)
            status['reset_start_monotonic']=time.monotonic()
            # Standard ESP32 auto-reset EN pulse, GPIO0 held released by DTR=False.
            ser.rts=True;time.sleep(.12);ser.rts=False;status['reset_commands']=1
            while time.monotonic()-start<a.timeout:
                data=ser.read(4096)
                if data:raw.write(data);pending+=data
                while b'\n' in pending:
                    line,pending=pending.split(b'\n',1);line=line.rstrip(b'\r').decode('utf-8',errors='replace')
                    if 'rst:0x' in line:
                        boot_count+=1
                        if boot_count>1:error='UNEXPECTED_SECOND_BOOT'
                    if boot_count and '"boot":' in line:
                        m=re.search(r'"boot":"([^"]+)"',line)
                        if m:ids.add(m[1])
                        if len(ids)>1:error='BOOT_ID_CHANGED'
                    if line.startswith('ECG_GOLDEN '):
                        goldens.append(line)
                        if 'status=EXACT_MATCH' not in line:error='GOLDEN_FAILED'
                    for tag in ['ECG_GOLDEN_DONE','V4_REPLAY_BEGIN','V4_PIPELINE_SUMMARY','V4_REPLAY_END','V4_REPLAY_ABORT']:
                        if line.startswith(tag+' '):
                            markers.setdefault(tag,[]).append(line);print(line,flush=True)
                            if len(markers[tag])>1:error='DUPLICATE_'+tag
                    if line.startswith('V4_REPLAY_ABORT '):error='REPLAY_ABORT'
                    if any(x in line for x in ['Guru Meditation','Brownout detector','abort() was called','Task watchdog got triggered']):error='DEVICE_FAULT: '+line
                    if 'ECG_GOLDEN_DONE ' in line and 'status=PASSED' not in line:error='GOLDEN_SUMMARY_FAILED'
                    if line.startswith('V4_REPLAY_END '):end_at=time.monotonic()
                now=time.monotonic()
                if now-last_report>=15:
                    print(f'PROGRESS elapsed={now-start:.1f}s golden={len(goldens)}/22 boot_count={boot_count} bytes={path.stat().st_size}',flush=True);last_report=now
                if error:break
                if end_at and now-end_at>2:break
            else:error='TIMEOUT_NO_COMPLETE_SESSION'
    except Exception as e:error=type(e).__name__+': '+str(e)
    finally:
        if ser.is_open:ser.dtr=False;ser.rts=False;ser.close()
    required=['ECG_GOLDEN_DONE','V4_REPLAY_BEGIN','V4_PIPELINE_SUMMARY','V4_REPLAY_END']
    sample_ids=[int(re.search(r'\bsample=(\d+)',l)[1]) for l in goldens]
    if not error and (boot_count!=1 or len(ids)!=1 or sample_ids!=list(range(22)) or any(len(markers.get(m,[]))!=1 for m in required)):error='INCOMPLETE_SESSION_OR_GOLDEN_IDS'
    if not error:
        if any('record='+a.record+' ' not in markers[tag][0] for tag in ['V4_REPLAY_BEGIN','V4_REPLAY_END']):error='WRONG_REPLAY_RECORD'
        sequence=path.read_bytes();positions=[sequence.find(m.encode()+b' ') for m in required]
        if positions!=sorted(positions):error='MARKER_ORDER'
    status.update(status='CAPTURE_COMPLETE' if not error else 'FAILED',error=error,elapsed_seconds=time.monotonic()-start,boot_count=boot_count,boot_ids=sorted(ids),golden_count=len(goldens),golden_ids=sample_ids,markers=markers,raw_bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (out/'capture_status.json').write_text(json.dumps(status,indent=2));print(json.dumps(status,indent=2),flush=True)
    if error:raise SystemExit(1)
if __name__=='__main__':main()
