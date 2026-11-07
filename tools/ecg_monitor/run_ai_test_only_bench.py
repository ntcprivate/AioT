"""Bounded bench runner. Requires saved explicit no-body/flash authorization.

Never enables live AI. Captures unmodified UART bytes and restores backed-up
sectors in finally. No serial port is opened when importing/analyzing this module.
"""
import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from diagnose_capture import analyze

ROOT=Path(__file__).resolve().parents[2]
FW=ROOT/'firmware/esp32_ecg_tinyml_integrated'
OUT=FW/'debug/esp32_ai_test_only'
IDFPY=Path('C:/Espressif/tools/python/v5.4.4/venv/Scripts/python.exe')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def markers(raw,name):
    found=[]
    for line in raw.decode('ascii',errors='replace').splitlines():
        if line.startswith(name+' '):
            pairs=re.findall(r'([a-zA-Z0-9_]+)=([^\s]+)',line)
            if len(pairs)!=len(set(k for k,v in pairs)):raise ValueError('Duplicate marker fields')
            row=dict(pairs)
            if row.get('live_locked')=='1' and 'live_inference' not in row:row['live_inference']='0'
            found.append(row)
    return found

def review(capture,manifest,elf_sha,synthetic):
    raw=Path(capture).read_bytes();errors=[];parsed={}
    for name,count in [('BEGIN',1),('CASE',20),('PERF',1),('STRESS',1),('DONE',1)]:
        rows=markers(raw,'ECG_AI_TEST_'+name);parsed[name]=rows
        if len(rows)!=count:errors.append(f'{name}: expected {count}, got {len(rows)}')
        for r in rows:
            if r.get('source')!='REFERENCE_TEST_ONLY' or r.get('not_live')!='1':errors.append('Missing TEST_ONLY identity')
    if parsed['BEGIN']:
        b=parsed['BEGIN'][0]
        for k,v in dict(app_elf_sha=elf_sha,synthetic=str(int(synthetic)),live_inference='0',assets_ok='1',adc_started='1').items():
            if b.get(k)!=v:errors.append(f'BEGIN {k} mismatch')
    indices=[]
    for row in parsed['CASE']:
        try:
            i=int(row['case']);indices.append(i);ref=manifest['cases'][i]
            if row['id']!=ref['id'] or row['record']!=ref['record'] or row['true_label']!=ref['symbol']:errors.append(f'CASE {i} identity mismatch')
            if int(row['code'])!=ref['code'] or int(row['reference_code'])!=ref['code']:errors.append(f'CASE {i} code mismatch')
            pred='PVC' if (ref['code']+128)/256>=.52 else 'NORMAL'
            truth=-1 if ref['label']<0 else int((pred=='PVC')==bool(ref['label']))
            if row['predicted']!=pred or row['reference_predicted']!=pred or int(row['truth_match'])!=truth:errors.append(f'CASE {i} prediction/truth mismatch')
            if abs(float(row['p_pvc'])-(ref['code']+128)/256)>1e-8:errors.append(f'CASE {i} probability mismatch')
            if any(row.get(k)!=v for k,v in dict(status='PASS',preprocessing_exact='1',stable_exact='1',repeats='30').items()):errors.append(f'CASE {i} not EXACT')
        except (KeyError,ValueError,IndexError):errors.append('Malformed CASE')
    if indices!=list(range(20)):errors.append('CASE order/coverage mismatch')
    for name in ['PERF','STRESS','DONE']:
        if not parsed[name]:continue
        row=parsed[name][0]
        if name=='PERF':
            if row.get('memory_ok')!='1' or row.get('measured')!='600':errors.append('PERF incomplete')
            try:
                if not 0<int(row['arena_used'])<=int(row['arena_allocated']) or int(row['stack_free_bytes'])<=0:errors.append('Invalid memory evidence')
            except (ValueError,KeyError):errors.append('Missing memory measurements')
        elif row.get('status')!='PASS':errors.append(name+' FAIL')
        if name=='STRESS':
            try:
                for k in ['adc_errors_delta','missed_delta','queue_drops_delta','snapshot_errors_delta','uart_errors_delta','format_errors_delta','uart_timeouts_delta']:
                    if int(row[k])!=0:errors.append('STRESS '+k+' nonzero')
                if int(row['adc_attempts_delta'])<=0 or not 249<=float(row['acq_hz'])<=251:errors.append('Invalid ADC stress evidence')
            except (ValueError,KeyError):errors.append('Missing stress counters')
    if parsed['DONE'] and any(parsed['DONE'][0].get(k)!=v for k,v in dict(cases='20',failed='0',golden_passed='1',live_inference='0').items()):errors.append('DONE incomplete')
    if not (raw.find(b'ECG_AI_TEST_BEGIN ')<raw.find(b'ECG_AI_TEST_CASE ')<raw.find(b'ECG_AI_TEST_PERF ')<raw.find(b'ECG_AI_TEST_STRESS ')<raw.find(b'ECG_AI_TEST_DONE ')):errors.append('Marker order invalid')
    golden=markers(raw,'ECG_GOLDEN')
    if len(golden)!=12 or any(r.get('status')!='EXACT_MATCH' for r in golden):errors.append('Golden not 12 EXACT')
    gd=markers(raw,'ECG_GOLDEN_DONE')
    if len(gd)!=1 or gd[0].get('status')!='PASSED':errors.append('Golden DONE missing/failed')
    if any(token in raw for token in [b'Guru Meditation',b'panic\'ed',b'Task watchdog',b'Stack canary watchpoint']):errors.append('Runtime panic/watchdog')
    telemetry=analyze(capture)
    for key in ['crc_failures','framing_errors','schema_errors','sequence_errors','packet_gaps','missing_samples','synthetic_mismatches']:
        if telemetry[key]:errors.append(f'telemetry {key}={telemetry[key]}')
    if telemetry['valid_samples']<512 or len(telemetry['by_boot'])!=1:errors.append('Insufficient telemetry or unexpected reboot')
    for boot in telemetry['by_boot'].values():
        if boot['synthetic']!=synthetic:errors.append('Wrong telemetry source')
    return dict(status='PASS' if not errors else 'FAIL',errors=errors,markers=parsed,telemetry=telemetry)

def command(args,log,cwd=FW,timeout=120):
    with Path(log).open('wb') as f:
        r=subprocess.run([str(IDFPY),'-m','esptool','--chip','esp32','--port','COM3','--baud','115200',*map(str,args)],cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
    if r.returncode:raise RuntimeError(f'esptool exit {r.returncode}; see {log}')

def capture(path,timeout=150,stop_on_done=True):
    import serial
    device=serial.Serial(port=None,baudrate=115200,timeout=.05)
    device.dtr=False;device.rts=False;device.port='COM3'
    data=bytearray();deadline=time.monotonic()+timeout;done_at=None
    with device,Path(path).open('wb') as f:
        # Serial context opens the selected port; no DTR/RTS reset here.
        while True:
            chunk=device.read(max(1,device.in_waiting))
            if chunk:f.write(chunk);f.flush();data.extend(chunk)
            if stop_on_done and b'ECG_AI_TEST_DONE ' in data and done_at is None:done_at=time.monotonic()
            end=min(deadline,done_at+3) if done_at else deadline
            if time.monotonic()>=end and (data.endswith(b'\n') or time.monotonic()>end+1):break
    return len(data)

def main():
    global OUT
    p=argparse.ArgumentParser();p.add_argument('--execute-authorized-bench',action='store_true');a=p.parse_args()
    if not a.execute_authorized_bench:p.error('Explicit bench execution flag required')
    authorization=json.loads((OUT/'authorization.json').read_text(encoding='utf-8-sig'))
    if authorization.get('bench_confirmed') is not True or authorization.get('body_testing_authorized') is not False:raise RuntimeError('Missing bench authorization')
    manifest=json.loads((OUT/'fixture_manifest.json').read_text())
    import uuid
    from bench_flash import snapshot_flash
    OUT=FW/'debug/ai_test_sessions'/uuid.uuid4().hex;OUT.mkdir(parents=True)
    image,backup=snapshot_flash(OUT,command)
    result=dict(authorization=authorization,runs={},restoration={'status':'NOT_NEEDED'})
    touched=False
    try:
        for variant,synthetic in [('adc',False),('synthetic',True)]:
            build=FW/f'build_ai_test_only_{variant}';cfg=json.loads((build/'flasher_args.json').read_text());files=cfg['flash_files']
            for offset,rel in files.items():
                end=int(offset,0)+((build/rel).stat().st_size+4095)//4096*4096
                if end>backup['length']:raise RuntimeError('Backup does not cover all written sectors')
            sdk=(build/'config/sdkconfig.h').read_text()
            if '#define CONFIG_ECG_AI_TEST_ONLY 1' not in sdk or '#define CONFIG_ECG_AI_LIVE 1' in sdk:raise RuntimeError('Unsafe configuration')
            elf=build/'esp32_ecg_tinyml_integrated.elf';elf_sha=sha(elf)
            app_sha=sha(build/'esp32_ecg_tinyml_integrated.bin')
            command(['flash_id'],OUT/f'identity_{variant}.log')
            if 'b0:3f:d3:51:8b:ec' not in (OUT/f'identity_{variant}.log').read_text():raise RuntimeError('Board identity changed')
            args=['write_flash',*cfg['write_flash_args']]
            for offset,rel in files.items():args.extend([offset,build/rel])
            touched=True;result['runs'][variant]={'status':'FLASHING'}
            command(args,OUT/f'flash_{variant}.log')
            raw=OUT/f'hardware_{variant}.bin'
            capture(raw)
            if sha(elf)!=elf_sha or sha(build/'esp32_ecg_tinyml_integrated.bin')!=app_sha:raise RuntimeError('Build artifacts changed during board test')
            result['runs'][variant]=review(raw,manifest,elf_sha,synthetic)
            result['runs'][variant]['app_sha256']=app_sha
            (OUT/f'hardware_{variant}.log').write_bytes(raw.read_bytes())
            (OUT/'hardware_results.json').write_text(json.dumps(result,indent=2))
            print(variant,result['runs'][variant]['status'],result['runs'][variant]['errors'],flush=True)
    except Exception as e:
        result['error']=str(e);print('Bench error:',e,flush=True)
    finally:
        if touched:
            try:
                if sha(image)!=backup['sha256']:raise RuntimeError('Backup changed')
                command(['flash_id'],OUT/'identity_restore.log')
                if 'b0:3f:d3:51:8b:ec' not in (OUT/'identity_restore.log').read_text():raise RuntimeError('Wrong board for restore')
                command(['write_flash','--flash_mode','keep','--flash_freq','keep','--flash_size','keep','0',image],OUT/'restore_flash.log')
                # write_flash performs MD5 verification on device before hard-reset.
                capture(OUT/'restored_firmware.bin',timeout=45,stop_on_done=False)
                result['restoration']={'status':'PASS','image_sha256':sha(image),'length':backup['length'],'telemetry':analyze(OUT/'restored_firmware.bin')}
            except Exception as e:result['restoration']={'status':'FAIL','error':str(e)}
        (OUT/'hardware_results.json').write_text(json.dumps(result,indent=2))
        print('Restoration',result['restoration']['status'],flush=True)

if __name__=='__main__':main()
