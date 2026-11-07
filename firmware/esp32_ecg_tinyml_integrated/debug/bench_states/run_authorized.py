"""Current explicitly authorized no-body bench session; no fabricated input."""
import json,sys,time,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/ecg_monitor'))
from run_ai_test_only_bench import sha,markers,FW
from bench_flash import snapshot_flash
from diagnose_capture import analyze
from ecg_monitor.protocol import StreamParser
OUT=Path(__file__).resolve().parent

def main():
    import esptool
    # Keep exclusive ownership through backup, write and capture. Reopening the
    # port between chunks lets an auto-reconnecting monitor steal COM3.
    with (OUT/'connection.log').open('w') as log,contextlib.redirect_stdout(log):
        esp=esptool.detect_chip('COM3',115200).run_stub()
        assert ':'.join(f'{x:02x}' for x in esp.read_mac())=='b0:3f:d3:51:8b:ec'
    def command(args,log,timeout=120):
        with Path(log).open('w') as stream,contextlib.redirect_stdout(stream):
            esptool.main(['--chip','esp32','--baud','115200','--no-stub','--after','no_reset_stub',*map(str,args)],esp=esp)
    auth=json.loads((OUT/'authorization.json').read_text())
    assert auth['bench_confirmed'] and auth['body_testing_authorized'] is False
    build=FW/'build_bench_demo';sdk=(build/'config/sdkconfig.h').read_text()
    assert '#define CONFIG_ECG_BENCH_DEMO 1' in sdk and '#define CONFIG_ECG_AI_LIVE 1' in sdk
    for flag in ['ECG_AI_TEST_ONLY','ECG_SYNTHETIC','ECG_HARDWARE_SELF_TEST','ECG_GOLDEN_ALERT_DEMO']:
        assert '#define CONFIG_'+flag+' 1' not in sdk,flag
    command(['flash_id'],OUT/'identity.log')
    assert 'b0:3f:d3:51:8b:ec' in (OUT/'identity.log').read_text()
    image,backup=snapshot_flash(OUT,command)
    cfg=json.loads((build/'flasher_args.json').read_text());args=['write_flash',*cfg['write_flash_args']]
    for offset,rel in cfg['flash_files'].items():
        assert int(offset,0)+((build/rel).stat().st_size+4095)//4096*4096<=backup['length']
        args.extend([offset,build/rel])
    result={'authorization':auth,'app_sha256':sha(build/'esp32_ecg_tinyml_integrated.bin'),'flash':'PENDING'}
    try:
        command(args,OUT/'flash.log');result['flash']='PASS_MD5_VERIFIED'
    except Exception:
        assert sha(image)==backup['sha256']
        command(['write_flash','--flash_mode','keep','--flash_freq','keep','--flash_size','keep','0',image],OUT/'restore.log')
        raise
    print('Flash verified; capturing 45 seconds',flush=True)
    rawfile=OUT/'hardware.bin'
    esp.hard_reset();esp._port.timeout=.05
    deadline=time.monotonic()+45
    with rawfile.open('wb') as stream:
        while time.monotonic()<deadline:
            chunk=esp._port.read(max(1,esp._port.in_waiting))
            if chunk:stream.write(chunk);stream.flush()
    esp._port.close()
    raw=rawfile.read_bytes();(OUT/'hardware.log').write_bytes(raw)
    result['telemetry']=analyze(rawfile)
    result['golden']=markers(raw,'ECG_GOLDEN');result['bench']=markers(raw,'ECG_BENCH_DEMO')
    result['pulses']=markers(raw,'ECG_BENCH_PULSE')
    packets=StreamParser().feed(raw);statuses=[p for p in packets if p['type']=='status']
    result['last_status']=statuses[-1] if statuses else None
    result['gpio_statuses']=[{k:p.get(k) for k in ['state','reason','led','buzzer','ai']} for p in statuses]
    errors=[]
    if len(result['golden'])!=12 or any(r.get('status')!='EXACT_MATCH' for r in result['golden']):errors.append('golden not 12 EXACT')
    if len(result['bench'])!=1 or result['bench'][0].get('source')!='LIVE_CNN' or result['bench'][0].get('pattern')!='STATE_V2':errors.append('missing bench identity')
    for key in ['crc_failures','schema_errors','framing_errors','sequence_errors','packet_gaps','missing_samples']:
        if result['telemetry'][key]:errors.append(key)
    for key in ['adc_errors','missed_est','tx_dropped','write_errors','snapshot_errors']:
        if result['telemetry']['last_firmware_counters'][key] not in (0,None):errors.append(key)
    if any(x in raw for x in [b'Guru Meditation',b'Task watchdog',b'Stack canary watchpoint']):errors.append('runtime failure')
    indices=[p.get('beat_index') for p in result['pulses']]
    if len(indices)!=len(set(indices)):errors.append('duplicate physical pulse')
    for status in statuses:
        if status.get('reason')=='LEADS_OFF' and (status.get('led') is not True or status.get('buzzer') is not False):errors.append('LEADS_OFF output mismatch')
    result['errors']=errors;result['status']='PASS' if not errors else 'FAIL'
    result['physical_valid_pvc']='PENDING: no external GPIO measurement; host tests cover all patterns; board telemetry only covers observed input states'
    (OUT/'hardware_results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['flash','status','errors','bench','pulses']},indent=2),flush=True)

if __name__=='__main__':main()
