"""Frozen PVC pilot; annotation consulted only after native inference."""
import csv,hashlib,json,subprocess
from pathlib import Path
from evaluate_v4_board_replay import match
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/cnn_v4/esp32_end_to_end';OUT=BASE/'pvc_replay_v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 protocol=json.loads((OUT/'protocol.json').read_text());assert sha(OUT/'protocol.json')==(OUT/'protocol.sha256').read_text().strip()
 run=OUT/'host';run.mkdir(exist_ok=False);asset=ROOT/protocol['asset'];model=ROOT/'models/v4/ecg_cnn_v4_int8.tflite'
 assert sha(asset)==protocol['stream_sha256'] and sha(model)==protocol['model_sha256']
 subprocess.run([str(BASE/'replay_host.exe'),str(asset),str(run/'events.csv'),str(run/'inputs.bin'),str(run/'windows.bin')],check=True)
 subprocess.run([str(BASE/'tflm_replay_host.exe'),str(model),str(run/'inputs.bin'),str(run/'codes.bin'),str(run/'timings.csv')],check=True)
 events=list(csv.reader((run/'events.csv').open()));peaks=[int(l[1]) for l in events if l[0]=='peak'];windows=[l for l in events if l[0]=='window'];ready=[l for l in windows if l[2]=='1' and l[3]=='0']
 codes=[x-256 if x>127 else x for x in (run/'codes.bin').read_bytes()];timings=list(csv.DictReader((run/'timings.csv').open()))
 assert len(codes)==len(ready)==len(timings);assert len(set(peaks))==len(peaks);assert all(int(w[1]) in peaks for w in windows)
 pred={int(w[1]):int(c>=98) for w,c in zip(ready,codes)}
 # First reference access occurs only here, after TFLM process has exited.
 refsfile=ROOT/protocol['annotation_list'];assert sha(refsfile)==protocol['annotation_sha256']
 refs=[x for x in json.loads(refsfile.read_text()) if x['symbol'] in protocol['matching']['beat_symbols']];pairs,used=match(refs,peaks)
 inverse={peaks[j]:refs[i] for i,j in pairs.items()};counts={'TP':0,'FP':0,'FN':0,'TN':0};miss_v=miss_n=window_v=classifier_fn=0
 for i,r in enumerate(refs):
  c=r['symbol']
  if c not in {'N','V'}:continue
  if i not in pairs:miss_v+=c=='V';miss_n+=c=='N';counts['FN']+=c=='V';continue
  peak=peaks[pairs[i]]
  if peak not in pred:window_v+=c=='V';miss_n+=c=='N';counts['FN']+=c=='V';continue
  p=pred[peak];key='TP' if c=='V' and p else 'FN' if c=='V' else 'FP' if p else 'TN';counts[key]+=1;classifier_fn+=key=='FN'
 unmatched=sum(pred.get(p,0) for j,p in enumerate(peaks) if j not in used);counts['FP']+=unmatched
 p=counts['TP']/(counts['TP']+counts['FP']) if counts['TP']+counts['FP'] else 0;r=counts['TP']/(counts['TP']+counts['FN']) if counts['TP']+counts['FN'] else 0
 bywindow={int(w[1]):w for w in windows};bycode={int(w[1]):(c,t) for w,c,t in zip(ready,codes,timings)}
 with (run/'beats.csv').open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['peak_index','record_index_250hz','matched_symbol','offset','rejected','reason','code','probability','prediction','invoke_HOST_us'])
  for peak in peaks:
   ref=inverse.get(peak);w=bywindow.get(peak);ct=bycode.get(peak)
   reason='NONE' if ct else 'WINDOW_INCOMPLETE' if w is None else 'INPUT_QUANTIZATION_CLIPPING' if int(w[3]) else 'NORMALIZATION_FAILED'
   writer.writerow([peak,peak+protocol['start_250hz'],ref['symbol'] if ref else 'UNMATCHED',peak-ref['sample'] if ref else '',int(ct is None),reason,ct[0] if ct else '',(ct[0]+128)/256 if ct else '',int(ct[0]>=98) if ct else '',ct[1]['invoke_host_us'] if ct else ''])
 result={'scope':'HOST ungated deterministic stream, not RTOS/generation/lead-off/ADC simulation or board result',
 'protocol_sha256':sha(OUT/'protocol.json'),'record':protocol['record'],'N':protocol['N'],'V':protocol['V'],**counts,'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0,
 'peakTP':len(pairs),'peakFP':len(peaks)-len(used),'peakFN':len(refs)-len(pairs),'peaks':len(peaks),'completed_windows':len(windows),'inferences':len(codes),'rejected_windows':len(windows)-len(ready),'pending_incomplete_windows':len(peaks)-len(windows),
 'PVC_detector_missed':miss_v,'PVC_window_or_clipping_missing':window_v,'PVC_classifier_FN':classifier_fn,'missing_N_abstentions':miss_n,'unmatched_PVC_alarms':unmatched,
 'detector_issues':[l for l in events if l[0]=='issue'],'lost_samples_host_file_scan':0,'board_latency_queue_drops':'PENDING_BOARD'}
 (run/'evaluation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
