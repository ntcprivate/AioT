"""Authorized no-body bench only; no valid ECG generator is assumed or invented."""
import argparse,json
from run_ai_test_only_bench import FW,command,capture,sha,markers
from diagnose_capture import analyze
from bench_flash import snapshot_flash
from ecg_monitor.protocol import StreamParser

OUT=FW/'debug/ai_live'
def main():
    p=argparse.ArgumentParser();p.add_argument('--execute-authorized-bench',action='store_true');p.add_argument('--seconds',type=int,default=120);a=p.parse_args()
    if not a.execute_authorized_bench:p.error('Explicit bench authorization flag required')
    if not 60<=a.seconds<=180:p.error('Bounded bench duration60..180seconds')
    auth=json.loads((OUT/'authorization.json').read_text())
    assert auth['bench_confirmed'] and not auth['body_testing_authorized']
    command(['flash_id'],OUT/'identity.log')
    assert 'b0:3f:d3:51:8b:ec' in (OUT/'identity.log').read_text(),'Unexpected board'
    backup,meta=snapshot_flash(OUT,command)
    b=FW/'build';cfg=json.loads((b/'flasher_args.json').read_text());sdk=(b/'config/sdkconfig.h').read_text()
    assert '#define CONFIG_ECG_AI_LIVE 1' in sdk
    for k in ['ECG_AI_TEST_ONLY','ECG_SYNTHETIC_TELEMETRY_TEST','ECG_GOLDEN_ALERT_DEMO']:
        assert f'#define CONFIG_{k} 1' not in sdk,k
    for off,rel in cfg['flash_files'].items():assert int(off,0)+((b/rel).stat().st_size+4095)//4096*4096<=meta['length']
    args=['write_flash',*cfg['write_flash_args']]
    for off,rel in cfg['flash_files'].items():args.extend([off,b/rel])
    flashed=False;result=dict(status='PENDING',ai_mode='AI_LIVE',app_sha256=sha(b/'esp32_ecg_tinyml_integrated.bin'),elf_sha256=sha(b/'esp32_ecg_tinyml_integrated.elf'))
    try:
        flashed=True;command(args,OUT/'flash.log')
        raw=OUT/'hardware.bin';capture(raw,timeout=a.seconds,stop_on_done=False);data=raw.read_bytes()
        (OUT/'hardware.log').write_bytes(data)
        parser=StreamParser();packets=parser.feed(data);statuses=[x for x in packets if x['type']=='status'];ai_rows=[x['ai'] for x in statuses if 'ai' in x]
        if not ai_rows:raise RuntimeError('No valid AI LIVE telemetry')
        golden=markers(data,'ECG_GOLDEN');gd=markers(data,'ECG_GOLDEN_DONE')
        t=analyze(raw);errors=[]
        if len(golden)!=12 or any(x.get('status')!='EXACT_MATCH' for x in golden) or len(gd)!=1 or gd[0].get('status')!='PASSED':errors.append('Golden not12 EXACT')
        if any(x.get('model')=='LOCKED' for x in statuses):errors.append('Obsolete runtime lock emitted')
        if any(x.get('buzzer') is True and x.get('self_test') is not True for x in statuses):errors.append('Unexpected prediction-driven buzzer')
        for k in ['crc_failures','framing_errors','schema_errors','sequence_errors','packet_gaps','missing_samples']:
            if t[k]:errors.append(f'{k}={t[k]}')
        fc=t['last_firmware_counters']
        for k in ['adc_errors','missed_est','tx_dropped','write_errors','format_errors','uart_write_errors','uart_tx_timeouts','snapshot_errors']:
            if fc.get(k)!=0:errors.append(f'{k}={fc.get(k)}')
        if not 249<=fc.get('acq_hz',0)<=251:errors.append('Acquisition frequency')
        unsafe=[x for x in statuses if (x['state'] in ('SIGNAL_INVALID','SYSTEM_FAULT') or x.get('quality_valid') is False) and x.get('ai',{}).get('state') in ('NORMAL','PVC')]
        if unsafe:errors.append('Prediction exposed during invalid signal')
        if any(x in data for x in [b'Guru Meditation',b'Stack canary watchpoint',b'Task watchdog']):errors.append('Runtime fault')
        result.update(status='FAIL' if errors else 'PASS_OBSERVED_BENCH_SAFETY',errors=errors,telemetry=t,golden=golden,
            reference_classification_errors=[x for x in golden if x['true']!=x['predicted']],
            ai_status_count=len(ai_rows),ai_states={s:sum(x['state']==s for x in ai_rows) for s in ['UNKNOWN','INVALID','NORMAL','PVC']},
            classified=max(x['classified'] for x in ai_rows),rejected=max(x['rejected'] for x in ai_rows),queue_drops=max(x['queue_drops'] for x in ai_rows),block_drops=max(x['block_drops'] for x in ai_rows),
            inference_calls=max((x.get('inference_calls',0) for x in ai_rows)),capture_seconds=a.seconds,
            min_heap=min(x['heap_min'] for x in ai_rows),last_heap=ai_rows[-1]['heap_free'],minimum_stack_free=min(x['stack_free'] for x in ai_rows if x['stack_free']>0),
            valid_adc_inference='OBSERVED_NOT_VALIDATED' if any(x['classified'] for x in ai_rows) else 'PENDING_NO_VALID_ANALOG_INPUT',
            firmware_left_on_board='build; main AI_LIVE enabled; prototype, prediction alerts disabled',backup_sha256=sha(backup))
        print(result['status'],result['errors'],result['ai_states'],flush=True)
    except Exception as e:
        result.update(status='FAIL',error=str(e));print('Bench failed:',e,flush=True)
        if flashed:
            command(['write_flash','--flash_mode','keep','--flash_freq','keep','--flash_size','keep','0',backup],OUT/'restore_after_failure.log')
            result['firmware_left_on_board']='Restored pre-test image verified by esptool MD5'
    finally:(OUT/'hardware_results.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':main()
