"""Bounded ADC capture; requires a separately reviewed physical checklist. No flash."""
import argparse, csv, datetime, hashlib, json, re, struct, time, zlib
from pathlib import Path


def inspect_line(line):
    m = re.fullmatch(rb'ECG1 ([0-9a-fA-F]{8}) (.*)', line.strip())
    if not m:
        if line.strip().startswith(b'ECG1 '):
            raise ValueError('MALFORMED_UART_FRAME')
        return None
    if zlib.crc32(m[2]) != int(m[1], 16):
        raise ValueError('UART_CRC_MISMATCH')
    return json.loads(m[2])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--confirmation', type=Path, required=True)
    p.add_argument('--port', default='COM3')
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--startup-timeout', type=float, default=150)
    p.add_argument('--disconnected-check', action='store_true', help='Firmware/ADC check only; no person or simulator required, not valid ECG evidence')
    p.add_argument('--run-dir', type=Path)
    p.add_argument('--continue-from', type=Path, help='Attach without reset to the same boot after exact golden evidence in an earlier raw log')
    p.add_argument('--passive-log-only', action='store_true', help='Read already-running UART only; never pulse reset or certify physical safety')
    a = p.parse_args()
    c = json.loads(a.confirmation.read_text(encoding='utf-8-sig'))
    required = ['physical_review_approved', 'no_body_connection', 'simulator_source_verified',
                'supply_measured_and_approved', 'out_voltage_measured_and_approved',
                'wiring_verified', 'ADC_binary_verified']
    if a.disconnected_check:
        required=['no_body_connection','ADC_binary_verified']
    if a.passive_log_only:
        required=[]
    if any(c.get(k) is not True for k in required):
        raise SystemExit('Physical/binary checklist incomplete; UART was not opened')
    if not 0 < a.seconds <= 3600 or not 0 < a.startup_timeout <= 600:
        raise SystemExit('Invalid bounded duration')
    import serial
    root = Path(__file__).resolve().parents[1]
    out = a.run_dir.resolve() if a.run_dir else root/'results/cnn_v4/esp32_end_to_end/board_runs'/datetime.datetime.now().strftime('ADC_V4_%Y%m%d_%H%M%S')
    if not out.resolve().is_relative_to(root): raise SystemExit('Run directory outside workspace')
    out.mkdir(exist_ok=bool(a.run_dir))
    meta = dict(confirmation=c, port=a.port, baud=115200, requested_seconds=a.seconds,
                host_start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), flash=False,
                disconnected_check=a.disconnected_check, valid_ecg_claim=False)
    meta['passive_log_only']=a.passive_log_only
    meta['reset_commands']=0
    golden = []; boots = 0; boot_ids = set(); frames = []; beats = []; error = None
    pending = b''; ready = None; adc_mode = False; start = time.monotonic()
    if a.continue_from:
        prior=a.continue_from.read_bytes()
        lines=prior.splitlines()
        gl=[l.decode() for l in lines if l.startswith(b'ECG_GOLDEN ')]
        golden=[int(re.search(r'\bsample=(\d+)',l)[1]) for l in gl]
        assert golden==list(range(22)) and all('status=EXACT_MATCH' in l for l in gl)
        assert any(l.startswith(b'ECG_GOLDEN_DONE ') and b'failed=0 status=PASSED' in l for l in lines)
        prior_frames=[inspect_line(l) for l in lines if l.startswith(b'ECG1 ') and l.endswith(b'}')]
        prior_ids={f['boot'] for f in prior_frames if f}
        assert len(prior_ids)==1
        boot_ids=prior_ids; boots=1
        meta.update(continued_from=str(a.continue_from),prior_log_sha256=hashlib.sha256(prior).hexdigest(),reset_commands=0)
    ser = serial.Serial(port=None, baudrate=115200, timeout=.2, dsrdtr=False, rtscts=False)
    ser.dtr = False; ser.rts = False; ser.port = a.port
    try:
        with (out/'uart_raw.log').open('xb', buffering=0) as raw:
            ser.open(); ser.reset_input_buffer()
            if not a.continue_from and not a.passive_log_only:
                ser.rts = True; time.sleep(.12); ser.rts = False
                meta['reset_commands']=1
            while True:
                data = ser.read(4096)
                raw.write(data); pending += data
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    text = line.decode('utf-8', errors='replace').strip()
                    if 'rst:0x' in text:
                        boots += 1
                        if boots > 1: raise ValueError('UNEXPECTED_RESET')
                    if text.startswith('V4_EXPERIMENT '):
                        adc_mode = 'mode=ADC ' in text
                        if not adc_mode: raise ValueError('WRONG_FIRMWARE_MODE')
                    if text.startswith('ECG_GOLDEN '):
                        golden.append(int(re.search(r'\bsample=(\d+)', text)[1]))
                        if 'status=EXACT_MATCH' not in text: raise ValueError('GOLDEN_FAILED')
                    if text.startswith('ECG_GOLDEN_DONE '):
                        if golden != list(range(22)) or 'status=PASSED' not in text or not adc_mode:
                            raise ValueError('INCOMPLETE_GOLDEN_OR_ADC_MODE')
                        ready = time.monotonic()
                        meta['measurement_start_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    if any(s in text for s in ['Guru Meditation', 'Brownout detector', 'abort() was called']):
                        raise ValueError('DEVICE_FAULT')
                    frame = inspect_line(line)
                    if frame:
                        boot_ids.add(frame.get('boot'))
                        if len(boot_ids) > 1: raise ValueError('BOOT_ID_CHANGED')
                        if frame.get('source') not in (None, 'HARDWARE'): raise ValueError('NON_HARDWARE_SOURCE')
                        if (frame.get('type')=='status' and frame.get('source')=='HARDWARE'
                            and frame.get('model_version')=='V4' and frame.get('threshold')==.88
                            and frame.get('ai',{}).get('source')=='ADC_CNN'):
                            adc_mode=True
                            if a.continue_from and ready is None and frame.get('golden') is True:
                                ready=time.monotonic()
                                meta['measurement_start_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
                        if ready is not None: frames.append(frame)
                    if text.startswith('V4_BEAT ') and ready is not None:
                        beats.append(dict(re.findall(r'(\w+)=([^ ]+)', text)))
                if ready is not None and time.monotonic()-ready >= a.seconds: break
                if ready is None and time.monotonic()-start > a.startup_timeout:
                    raise TimeoutError('GOLDEN_STARTUP_TIMEOUT')
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        if ser.is_open: ser.dtr=False; ser.rts=False; ser.close()
    if boots != 1 or len(boot_ids) != 1 or golden != list(range(22)):
        error = error or 'INCOMPLETE_BOOT_OR_GOLDEN'
    meta.update(host_end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), error=error,
                golden_ids=golden, boots=boots, boot_ids=list(boot_ids), trailing_bytes=len(pending),
                elapsed_seconds=time.monotonic()-start,
                uart_sha256=hashlib.sha256((out/'uart_raw.log').read_bytes()).hexdigest())
    (out/'session_metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    (out/'telemetry.json').write_text(json.dumps(frames), encoding='utf-8')
    fields=sorted({k for b in beats for k in b}) or ['r_index','predicted','reason']
    with (out/'predictions.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(beats)
    statuses=[f for f in frames if f.get('type')=='status']
    samples=[]; sequence_errors=[]; previous_seq=None
    for frame in frames:
        seq=frame.get('seq')
        if previous_seq is not None and seq != (previous_seq+1) & 0xffffffff:
            sequence_errors.append([previous_seq,seq])
        previous_seq=seq
        if frame.get('type')=='samples':
            packed=bytes.fromhex(frame['data'])
            if len(packed)!=frame['n']*7:
                error=error or 'SAMPLE_PAYLOAD_LENGTH'; continue
            for i,(delta,raw_adc,flags) in enumerate(struct.iter_unpack('<IHB',packed)):
                samples.append(dict(sample_index=frame['first']+i,t_us=frame['t0']+delta,
                    adc_raw=raw_adc,lo_plus=int(bool(flags&1)),lo_minus=int(bool(flags&2)),
                    adc_error=int(bool(flags&4)),missed=int(bool(flags&8))))
    with (out/'adc_raw.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['sample_index','t_us','adc_raw','lo_plus','lo_minus','adc_error','missed'])
        w.writeheader(); w.writerows(samples)
    if not samples or not statuses:
        error=error or 'MISSING_ADC_TELEMETRY'
    meta['error']=error
    (out/'session_metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    metrics=dict(status='FAILED' if error else 'CAPTURED_REQUIRES_REVIEW',
                 golden_exact=len(golden), beat_events=len(beats),
                 captured_adc_samples=len(samples), sequence_errors=sequence_errors,
                 first_status=statuses[0] if statuses else None,
                 last_status=statuses[-1] if statuses else None,
                 confusion_matrix=None, precision=None, recall=None, f1=None,
                 note='Capture completion is not ADC end-to-end PASS; review quality, gaps, rejection and inference.')
    invoked=[b for b in beats if int(b.get('invoke_us','0'))>0]
    metrics.update(inference_events=len(invoked),
        rejected_events=sum(b.get('rejected')=='1' for b in beats),
        normal_predictions=sum(b.get('predicted')=='0' and b.get('rejected')=='0' for b in invoked),
        pvc_predictions=sum(b.get('predicted')=='1' and b.get('rejected')=='0' for b in invoked),
        invoke_mean_us=sum(int(b['invoke_us']) for b in invoked)/len(invoked) if invoked else None,
        r_peak_to_result_mean_us=sum(int(b['e2e_us']) for b in invoked)/len(invoked) if invoked else None)
    (out/'adc_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    (out/'report.md').write_text('# ADC capture requires review\n\n'+json.dumps(metrics,indent=2),encoding='utf-8')
    print(out)
    if error: raise SystemExit(error)


if __name__ == '__main__':
    main()
