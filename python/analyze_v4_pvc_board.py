"""Post-inference evidence/accounting only, requires completed real UART evaluation."""
import argparse,csv,hashlib,json,re,statistics,zlib
from pathlib import Path
from evaluate_v4_board_replay import match,fields
ROOT=Path(__file__).resolve().parents[1]
def stats(rows,key):
 v=[int(r[key]) for r in rows];return {'count':len(v),'mean_us':statistics.mean(v),'min_us':min(v),'max_us':max(v)} if v else None
def main():
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args();run=a.run
 if (run/'analysis.json').exists():raise SystemExit('Refuse overwrite')
 protocol=json.loads((ROOT/'results/cnn_v4/esp32_end_to_end/pvc_replay_v1/protocol.json').read_text());refs=json.loads((ROOT/protocol['annotation_list']).read_text())
 raw=(run/'uart_raw.log').read_bytes();text=raw.decode(errors='replace');capture=json.loads((run/'capture_status.json').read_text());assert capture['status']=='CAPTURE_COMPLETE'
 evaluation=json.loads((run/'evaluation.json').read_text());assert evaluation['log_sha256']==hashlib.sha256(raw).hexdigest()
 peaks=[int(fields(l)['r_index']) for l in text.splitlines() if l.startswith('V4_PEAK ')];beats=[fields(l) for l in text.splitlines() if l.startswith('V4_BEAT ')]
 by={int(b['r_index']):b for b in beats};pairs,used=match(refs,peaks);reasons={};reference_rows=[]
 for i,r in enumerate(refs):
  peak=peaks[pairs[i]] if i in pairs else None;b=by.get(peak);code=int(b['code']) if b and b['rejected']=='0' else None
  category='DETECTOR_MISS' if peak is None else 'WINDOW_NOT_COMPLETED' if b is None else 'REJECTED_'+b['reason'] if b['rejected']=='1' else 'TP' if r['symbol']=='V' and code>=98 else 'FN_CLASSIFIER' if r['symbol']=='V' else 'FP_MATCHED_N' if code>=98 else 'TN'
  reference_rows.append({'reference_index':i,**r,'peak':peak,'delta_samples':peak-r['sample'] if peak is not None else None,'category':category,'code':code})
 for b in beats:
  if b['rejected']=='1':reasons[b['reason']]=reasons.get(b['reason'],0)+1
 unmatched=[]
 for j,peak in enumerate(peaks):
  if j in used:continue
  ref=min(refs,key=lambda r:abs(peak-r['sample']));b=by.get(peak)
  unmatched.append({'peak':peak,'record_index':peak+protocol['start_250hz'],'nearest_reference':ref['sample'],'nearest_symbol':ref['symbol'],
   'signed_distance_samples':peak-ref['sample'],'inside_tolerance':abs(peak-ref['sample'])<=38,'reference_has_match':refs.index(ref) in pairs,
   'code':int(b['code']) if b and b['rejected']=='0' else None,'prediction':int(b['predicted']) if b else None})
 frames=[];crc_bad=0
 for line in text.splitlines():
  if not line.startswith('ECG1 '):continue
  _,crc,body=line.split(' ',2)
  if crc!=f'{zlib.crc32(body.encode())&0xffffffff:08x}':crc_bad+=1;continue
  frames.append(json.loads(body))
 golden=[fields(l) for l in text.splitlines() if l.startswith('ECG_GOLDEN ')];fixture=json.loads((ROOT/'results/cnn_v4/esp32_golden_test/fixtures.json').read_text())['fixtures']
 assert len(golden)==22 and all(int(g['code'])==int(g['reference_code'])==f['reference_code'] and g['status']=='EXACT_MATCH' for g,f in zip(golden,fixture))
 last=next(f for f in reversed(frames) if f.get('type')=='status');accepted=[b for b in beats if b['rejected']=='0'];invoked=[b for b in beats if int(b['invoke_us'])>0]
 hostroot=ROOT/'results/cnn_v4/esp32_end_to_end/pvc_replay_v1/host';host=list(csv.DictReader((hostroot/'beats.csv').open()));host_by={int(b['peak_index']):b for b in host}
 comparison=[]
 for peak in sorted(set(host_by)|set(peaks)):
  h=host_by.get(peak);b=by.get(peak)
  comparison.append({'peak':peak,'host_code':int(h['code']) if h and h['code'] else None,'board_code':int(b['code']) if b and b['rejected']=='0' else None,
   'board_rejection':b['reason'] if b and b['rejected']=='1' else None,'host_detected':peak in host_by,'board_detected':peak in peaks})
 common=[c for c in comparison if c['host_code'] is not None and c['board_code'] is not None]
 ncounts={};vcounts={}
 for r in reference_rows:
  target=ncounts if r['symbol']=='N' else vcounts;target[r['category']]=target.get(r['category'],0)+1
 result={'status':'REAL_BOARD_EVALUATOR_PASS','protocol_sha256':hashlib.sha256((ROOT/'results/cnn_v4/esp32_end_to_end/pvc_replay_v1/protocol.json').read_bytes()).hexdigest(),
 'device_boot_lines':[l for l in text.splitlines() if any(t in l for t in ['CPU freq:','app_init:','Project name:','App version:','ESP-IDF:','ELF file SHA256:','ECG_KERNELS ','ECG_MODEL '])],
 'boot_id':capture['boot_ids'],'golden_exact':22,'beats':len(beats),'inference_calls':len(invoked),'classified':len(accepted),'rejection_reasons':reasons,'N_accounting':ncounts,'V_accounting':vcounts,
 'invoke':stats(invoked,'invoke_us'),'preprocessing_accepted':stats(accepted,'prep_us'),'r_to_result':stats(accepted,'e2e_us'),
 'crc_errors':crc_bad,'last_telemetry_status':last,'unmatched_peaks':unmatched,'common_classified_peaks':len(common),
 'common_codes_exact':sum(c['host_code']==c['board_code'] for c in common),'max_common_code_delta':max((abs(c['host_code']-c['board_code']) for c in common),default=None),
 'comparison_differences':[c for c in comparison if c['host_code']!=c['board_code'] or c['host_detected']!=c['board_detected']],
 'host_metrics':json.loads((hostroot/'evaluation.json').read_text()),'board_metrics':evaluation}
 (run/'analysis.json').write_text(json.dumps(result,indent=2))
 for name,rows in [('reference_accounting.csv',reference_rows),('unmatched_peaks.csv',unmatched),('host_board_by_peak.csv',comparison),('beats.csv',beats)]:
  with (run/name).open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print(json.dumps({k:v for k,v in result.items() if k not in {'last_telemetry_status','unmatched_peaks','host_metrics','board_metrics'}},indent=2))
if __name__=='__main__':main()
