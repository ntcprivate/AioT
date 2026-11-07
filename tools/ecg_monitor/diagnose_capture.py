"""Analyze untouched serial byte capture offline. Never opens a COM port."""
import argparse
import hashlib
import json
from pathlib import Path
from ecg_monitor.protocol import StreamParser


def analyze(path):
    path=Path(path);examples=[]
    parser=StreamParser(lambda e:examples.append(e) if len(examples)<16 else None)
    samples=0;packets=0;first=None;last=None;status={};boot=None;boot_counts={};bytes_count=0;digest=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(4096):
            digest.update(chunk);bytes_count+=len(chunk)
            for p in parser.feed(chunk):
                packets+=1
                if p['type']=='status':status=p;continue
                boot=p['boot'];entry=boot_counts.setdefault(boot,dict(samples=0,first_us=None,last_us=None,synthetic=False))
                entry['samples']+=p['n'];entry['synthetic']=p.get('source')=='SYNTHETIC_TEST'
                if entry['first_us'] is None:entry['first_us']=p['samples'][0][0]
                entry['last_us']=p['samples'][-1][0];samples+=p['n']
    for entry in boot_counts.values():
        duration=(entry['last_us']-entry['first_us'])/1e6
        entry['received_device_time_hz']=(entry['samples']-1)/duration if duration>0 else None
    return dict(capture=str(path),sha256=digest.hexdigest(),bytes=bytes_count,valid_packets=packets,valid_samples=samples,
        crc_failures=parser.crc_failures,framing_errors=parser.framing_errors,schema_errors=parser.schema_errors,
        sequence_errors=parser.sequence_errors,packet_gaps=parser.lost_packets,missing_samples=parser.lost_samples,
        rx_timing_violations=parser.timing_violations,synthetic_mismatches=parser.synthetic_mismatches,
        trailing_partial_bytes=len(parser.buffer),unterminated_oversize=parser.discard,by_boot=boot_counts,
        last_firmware_counters={k:status.get(k) for k in ['firmware','source','baud','uart_baud_actual','sample_attempts','acq_hz','tx_samples','tx_hz','tx_dropped','write_errors','format_errors','uart_write_errors','uart_tx_timeouts','adc_errors','missed_est','late','snapshot_errors']},
        rejection_examples=examples,
        limits='No repair. Offline raw file has no host-arrival clock; RX wall rate cannot be inferred. UART completion is not a host acknowledgement. Corrupt frames alone cannot identify physical cause.')


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
    output=args.output or args.capture.with_suffix('.analysis.json')
    if output.resolve()==args.capture.resolve():p.error('Do not overwrite capture')
    report=analyze(args.capture);output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
