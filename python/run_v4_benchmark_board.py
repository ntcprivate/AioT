"""One explicit V4 benchmark flash/capture. Stop on failure; no retries/restores."""
import argparse,hashlib,json,math,re,serial,struct,subprocess,sys,time
from pathlib import Path
def fields(l):return dict(re.findall(r'(\w+)=([^\s]+)',l))
def f32(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);p.add_argument('--backend',required=True,choices=['FP32','INT8']);p.add_argument('--bench-authorized',action='store_true');a=p.parse_args()
 if not a.bench_authorized:raise SystemExit('Explicit authorized bench only')
 root=Path(__file__).resolve().parents[1];exp=a.experiment.resolve();run=exp/a.backend;config=json.loads((exp/'config.json').read_text());build=run/'build';manifest=json.loads((run/'build_verification.json').read_text())
 assert sha(build/'application.bin')==manifest['application_sha256'];assert manifest['backend']==a.backend and manifest['CPU_MHz']==160
 for name,digest in manifest['flash_hashes'].items():assert sha(build/name)==digest
 # Opening COM during flash proves availability; no automatic port/process killing.
 cmd=[sys.executable,'-m','esptool','--chip','esp32','--port','COM3','--baud','460800','--before','default_reset','--after','no_reset','write_flash','--flash_mode','dio','--flash_freq','40m','--flash_size','4MB','0x1000',str(build/'bootloader.bin'),'0x8000',str(build/'partition-table.bin'),'0x10000',str(build/'application.bin')]
 with (run/'flash.log').open('xb') as log:result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 (run/'flash_status.json').write_text(json.dumps({'exit_code':result.returncode,'command':cmd},indent=2))
 if result.returncode:raise SystemExit('FLASH_FAILED; no reset/capture/retry')
 print('FLASH_PASS '+a.backend,flush=True)
 port=serial.Serial(port=None,baudrate=115200,timeout=.2,dsrdtr=False,rtscts=False);port.dtr=False;port.rts=False;port.port='COM3'
 path=run/'uart_raw.log';start=time.monotonic();lines=[];pending=b'';boot=0;last_progress=0;end_time=None;error=None;reset_count=0
 try:
  with path.open('xb',buffering=0) as raw:
   port.open();port.reset_input_buffer()
   # Raw file exists before EN pulse. Flash ended in bootloader, not unlogged benchmark.
   port.rts=True;time.sleep(.12);port.rts=False;reset_count=1
   while time.monotonic()-start<600:
    data=port.read(4096)
    if data:raw.write(data);pending+=data
    while b'\n' in pending:
     b,pending=pending.split(b'\n',1);line=b.rstrip(b'\r').decode('utf-8',errors='replace');lines.append(line)
     if 'rst:0x' in line:
      boot+=1
      if boot>1:error='UNEXPECTED_RESET'
     if line.startswith(('V4_BENCH_IDENTITY ','V4_BENCH_BEGIN ','V4_BENCH_END ','V4_BENCH_FAILED ')):print(line,flush=True)
     if any(s in line for s in ['V4_BENCH_FAILED','Guru Meditation','abort() was called','Brownout detector','Task watchdog got triggered']):error='DEVICE_FAILURE: '+line
     if line.startswith('V4_BENCH_END '):end_time=time.monotonic()
    now=time.monotonic()
    if now-last_progress>=15:
     print(f'PROGRESS {a.backend} elapsed={now-start:.1f}s samples={sum(l.startswith("V4_BENCH_SAMPLE ") for l in lines)}/726 boots={boot}',flush=True);last_progress=now
    if error:break
    if end_time and now-end_time>.5:break
   else:error='TIMEOUT'
 except Exception as e:error=repr(e)
 finally:
  if port.is_open:port.dtr=False;port.rts=False;port.close()
 capture={'backend':a.backend,'error':error,'boots':boot,'measurement_EN_resets':reset_count,'elapsed_seconds':time.monotonic()-start,'uart_sha256':sha(path),'uart_bytes':path.stat().st_size}
 (run/'capture_status.json').write_text(json.dumps(capture,indent=2))
 if error:raise SystemExit(error)
 try:
  assert boot==1,'Require one ROM boot'
  def rows(tag):return [fields(l) for l in lines if l.startswith(tag+' ')]
  identity=rows('V4_BENCH_IDENTITY');begin=rows('V4_BENCH_BEGIN');end=rows('V4_BENCH_END');samples=rows('V4_BENCH_SAMPLE')
  assert len(identity)==len(begin)==len(end)==1,'Incomplete/duplicate markers'
  assert identity[0]['sha256']==config['model_hashes'][a.backend],'Wrong model'
  assert begin[0]['backend']==a.backend and begin[0]['cpu_mhz']=='160' and begin[0]['fixtures']=='22' and begin[0]['warmup']=='3' and begin[0]['measured']=='30','Protocol mismatch'
  assert any('cpu freq: 160000000 Hz' in l for l in lines),'Actual CPU clock not confirmed'
  assert len(samples)==726,'Missing sample records'
  expected=[(i,k) for i in range(22) for k in range(-3,30)];assert [(int(s['i']),int(s['run'])) for s in samples]==expected,'Incomplete/order/duplicate run IDs'
  fixture=json.loads((root/'results/cnn_v4/esp32_golden_test/fixtures.json').read_text())['fixtures']
  for s in samples:
   score=float(s['score']);assert math.isfinite(score) and 0<=score<=1,'Invalid score'
   assert int(s['predicted'])==int(f32(score)>=f32(.88)),'Decision mismatch'
   assert int(s['total_us'])==sum(int(s[k]) for k in ['norm_us','quant_copy_us','invoke_us']),'Timing sum'
   assert all(int(s[k])>=0 for k in ['norm_us','quant_copy_us','invoke_us'])
   if a.backend=='INT8':
    code=int(s['code']);assert code==fixture[int(s['i'])]['reference_code'],'INT8 golden mismatch'
    assert abs(score-(code+128)/256)<1e-8,'INT8 dequantization'
  if a.backend=='INT8':assert end[0]['int8_exact']=='1'
  (run/'validated_samples.json').write_text(json.dumps({'status':'PASS','backend':a.backend,'warmup_runs':66,'measured_runs':660,'memory':end[0],'samples':samples},indent=2))
 except Exception as e:
  (run/'validation_failure.json').write_text(json.dumps({'error':repr(e)},indent=2));raise
 print('BENCH_VALIDATED_PASS '+a.backend,flush=True)
if __name__=='__main__':main()
