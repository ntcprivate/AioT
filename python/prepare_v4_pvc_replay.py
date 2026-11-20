"""Annotation-only deterministic segment selection; freeze before model access."""
import hashlib,json
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/cnn_v4/esp32_end_to_end/pvc_replay_v1'
FW=ROOT/'firmware/esp32_ecg_v4_experiment'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(exist_ok=False)
 rule={'dataset':'INCART Validation only from incart_patient_split_v4.json','order':'record ID ascending, then start ascending on 250-sample (1s) grid',
 'samples':15360,'fs':250,'duration_seconds':61.44,'minimum_N':20,'minimum_V':20,
 'selection_count_interval':'[start+1000,end-256); excludes 4s startup and 1.024s tail for selection only',
 'scoring':'all annotations within supplied stream, including startup/edges; missing V always FN',
 'selection_inputs':'annotation symbols/times, header sampling rate/duration only; no waveform/model scores',
 'fallback':'none; FAIL if no candidate; waveform numeric/contract failure stops, no reselection',
 'interpretation':'small engineering pilot, not statistically precise independent PVC performance'}
 (OUT/'selection_rule.json').write_text(json.dumps(rule,indent=2))
 split=json.loads((ROOT/'data/processed/incart_patient_split_v4.json').read_text());chosen=None;scanned=[]
 for rec in sorted(split['validation']['records']):
  base=ROOT/'files'/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr')
  positions=np.floor(ann.sample*250/h.fs+.5).astype(np.int64);symbols=np.array(ann.symbol)
  n=positions[symbols=='N'];v=positions[symbols=='V'];length=int(np.ceil(h.sig_len*250/h.fs));examined=0
  for start in range(0,length-15360+1,250):
   examined+=1;lo=start+1000;hi=start+15360-256
   nc=int(np.searchsorted(n,hi)-np.searchsorted(n,lo));vc=int(np.searchsorted(v,hi)-np.searchsorted(v,lo))
   if nc>=20 and vc>=20:chosen=(rec,start,h,ann,positions,nc,vc);break
  scanned.append({'record':rec,'windows_examined':examined})
  if chosen:break
 if chosen is None:
  (OUT/'selection_failed.json').write_text(json.dumps({'status':'FAIL_INSUFFICIENT_N_V','scanned':scanned},indent=2));raise RuntimeError('No eligible Validation segment; no fallback')
 rec,start,h,ann,positions,nc,vc=chosen;end=start+15360;base=ROOT/'files'/rec
 selected={'record':rec,'start_250hz':start,'end_250hz_exclusive':end,'interior_N':nc,'interior_V':vc,'scanned':scanned,'rule_sha256':sha(OUT/'selection_rule.json')}
 # Freeze choice before opening waveform or model.
 (OUT/'selected_segment.json').write_text(json.dumps(selected,indent=2))
 leads=[x.strip().upper() for x in h.sig_name];assert h.fs==257 and leads.count('II')==1
 raw=wfdb.rdrecord(str(base),channels=[leads.index('II')],physical=True).p_signal[:,0]
 signal=resample_poly(raw,250,257)[start:end];assert len(signal)==15360 and np.isfinite(signal).all()
 counts=np.clip(np.rint(2048+200*signal),0,4095).astype('<u2')
 asset=FW/'main/assets/INCART_PVC_V1.bin';assert not asset.exists();asset.write_bytes(counts.tobytes())
 refs=[{'sample':int(s-start),'record_sample_250hz':int(s),'source_sample':int(src),'symbol':c} for s,src,c in zip(positions,ann.sample,ann.symbol) if start<=s<end]
 annpath=OUT/'annotations.json';annpath.write_text(json.dumps(refs,indent=2))
 protocol={'version':1,'segment_id':'INCART_PVC_V1','dataset':'INCART','record':rec,'split':'Validation','lead':'II','source_hz':257,'fs':250,
 'start_250hz':start,'end_250hz_exclusive':end,'samples':15360,'N':sum(r['symbol']=='N' for r in refs),'V':sum(r['symbol']=='V' for r in refs),
 'OTHER':sum(r['symbol'] not in {'N','V'} for r in refs),'annotation_list':str(annpath.relative_to(ROOT)),
 'annotation_sha256':sha(annpath),'asset':str(asset.relative_to(ROOT)),'stream_sha256':sha(asset),
 'source_hashes':{ext:sha(base.with_suffix('.'+ext)) for ext in ['hea','dat','atr']},'selection_rule_sha256':sha(OUT/'selection_rule.json'),
 'selection_sha256':sha(OUT/'selected_segment.json'),'mapping':'full resample_poly 250/257 then crop; clip(rint(2048+200*mV),0,4095)',
 'annotation_mapping':'floor(source_sample*250/257+0.5)-start_250hz','threshold':.88,'threshold_code':98,
 'model_sha256':'a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e',
 'matching':{'tolerance_samples':38,'algorithm':'chronological reference nearest unused detection, ties lower index','beat_symbols':'NLRBAaJSVrFejnE/fQ?',
 'OTHER':'matched beat TP detector; excluded N/V classifier','missing_V':'FN','missing_N':'abstention not TN','unmatched_PVC':'FP alarm, not automatically noise'},
 'rail_samples':int(((counts<=16)|(counts>=4079)).sum()),'labels_in_firmware':False}
 (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
 (OUT/'protocol.sha256').write_text(sha(OUT/'protocol.json')+'\n')
 (FW/'main/pvc_replay_identity.h').write_text('#pragma once\nconstexpr char kReplayRecord[]="INCART_PVC_V1";\nconstexpr char kReplaySha[]="'+sha(asset)+'";\n')
 print(json.dumps(protocol,indent=2))
if __name__=='__main__':main()
