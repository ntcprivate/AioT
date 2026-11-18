import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/model_comparison/test_end_to_end_v4_v6_v11';OLD=ROOT/'results/cnn_v11/final_test';BEATS=set('NLRBAaJSVrFejnE/fQ?')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2))
def aggregate(rows):
 v={k:sum(int(r[k]) for r in rows) for k in ['TP','FP','FN','TN','reference_N','missing_N','missing_V','extra_peaks','FP_matched_N','FP_unmatched_alarm']};p=v['TP']/(v['TP']+v['FP']) if v['TP']+v['FP'] else 0;r=v['TP']/(v['TP']+v['FN']) if v['TP']+v['FN'] else 0
 v.update(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,fp_per_1000_N=v['FP']*1000/v['reference_N'] if v['reference_N'] else 0);return v
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'evaluation.json').exists():raise RuntimeError('Comparison complete; refusing rerun')
 old=json.loads((OLD/'evaluation.json').read_text());v4=json.loads((ROOT/'results/cnn_v4/selection.json').read_text());v6=json.loads((ROOT/'results/cnn_v6/evaluation.json').read_text())
 thresholds={'V4':v4['selected_threshold'],'V6':v6['selected_threshold'],'V11':old['locked']['threshold']};assert thresholds=={'V4':.88,'V6':.87,'V11':.8}
 paths={'V4':ROOT/'models/v4/ecg_cnn_v4_best.keras','V6':ROOT/'models/v6/ecg_cnn_v6_best.keras','V11':ROOT/'models/v11/v11_final_best.keras'}
 expected={'V4':v4['model_sha256'],'V6':v6['checkpoint_sha256'],'V11':old['locked']['sha256']}
 for m,p in paths.items():assert sha(p)==expected[m]
 tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
 models={m:tf.keras.models.load_model(paths[m],compile=False) for m in ['V4','V6']}
 incsplit=json.loads((ROOT/'data/processed/incart_patient_split_v4.json').read_text());inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');split=np.load(ROOT/'data/processed/mitbih_split_indices.npz')
 allowed={'MITBIH':set(mit['record_ids'][split['test_indices']]),'INCART':set(inc['record_ids'][inc['split']=='test'])};rows=[];sources=[]
 for saved in old['records']:
  ds,rec=saved['dataset'],saved['record'];assert rec in allowed[ds]
  completed=OUT/f'{ds}_{rec}_metrics.json'
  if completed.exists():rows.extend(json.loads(completed.read_text()));continue
  base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');channel=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII')
  signal=wfdb.rdrecord(str(base),channels=[channel],**({'return_res':32} if ds=='INCART' else {})).p_signal[:,0];signal=resample_poly(signal,250 if ds=='INCART' else 25,257 if ds=='INCART' else 36)
  if ds=='INCART':signal=signal.astype(np.float32)
  raw=np.clip(np.rint(2048+200*signal),0,4095).astype('<i2')
  cached=OLD/f'{ds}_{rec}_detector.npz';z=np.load(cached);peaks=z['peaks'];score11=z['scores'];events=[s.split(',') for s in (OLD/f'{ds}_{rec}_detector.csv').read_text().splitlines()];np.testing.assert_array_equal(peaks,np.array([int(e[1]) for e in events if e[0]=='peak']))
  assert np.all(np.diff(peaks)>0) and np.all(peaks>=128) and np.all(peaks+128<=len(raw))
  windows=np.stack([raw[p-128:p+128] for p in peaks]).astype(np.float32)[:,:,None];std=windows.std(1,keepdims=True);assert np.isfinite(windows).all() and np.all(std>1e-8)
  x=(windows-windows.mean(1,keepdims=True))/np.maximum(std,1e-8)
  # Last native output file survives; compare raw windows when this is that record.
  if saved==old['records'][-1]:np.testing.assert_array_equal(windows,np.fromfile(OLD/'windows.bin',dtype=np.float32).reshape(-1,256,1))
  scores={'V11':score11}
  for m,model in models.items():
   predpath=OUT/f'{ds}_{rec}_{m}_scores.npz'
   if predpath.exists():zz=np.load(predpath);np.testing.assert_array_equal(zz['peaks'],peaks);scores[m]=zz['scores']
   else:
    scores[m]=model.predict(x,batch_size=512,verbose=0).ravel();np.savez_compressed(predpath,peaks=peaks,scores=scores[m],model_sha256=expected[m])
  refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS];used=set();pairs={};errors=[]
  for i,(t,c) in enumerate(refs):
   cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
   if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);pairs[i]=j;errors.append(int(peaks[j]-t))
  patient=rec if ds=='MITBIH' else str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==rec)[0]]);local=[]
  for m in ['V4','V6','V11']:
   pred=scores[m]>=thresholds[m];tp=fpn=fn=tn=mn=mv=0
   for i,(t,c) in enumerate(refs):
    if c not in {'N','V'}:continue
    if i not in pairs:fn+=int(c=='V');mv+=int(c=='V');mn+=int(c=='N');continue
    p=pred[pairs[i]];tp+=int(c=='V' and p);fpn+=int(c=='N' and p);fn+=int(c=='V' and not p);tn+=int(c=='N' and not p)
   fpx=sum(int(pred[j]) for j in range(len(peaks)) if j not in used)
   row=dict(dataset=ds,record=rec,patient_or_record_group=patient,model=m,reference_N=sum(c=='N' for t,c in refs),reference_V=sum(c=='V' for t,c in refs),TP=tp,FP=fpn+fpx,FN=fn,TN=tn,missing_N=mn,missing_V=mv,extra_peaks=len(peaks)-len(used),FP_matched_N=fpn,FP_unmatched_alarm=fpx,matched_OTHER=sum(refs[i][1] not in {'N','V'} for i in pairs),out_of_scope_symbols=sorted(set(ann.symbol)-BEATS),timing_abs_p95_samples=float(np.percentile(abs(np.array(errors)),95)))
   if m=='V11':
    for key in ['TP','FP','FN','TN']:assert row[key]==saved['detector'][key],(rec,key)
    assert mn==saved['missing_N'] and mv==saved['missing_V'] and row['extra_peaks']==saved['extra_peaks']
   local.append(row)
  write(completed,local);rows.extend(local);sources.append({'dataset':ds,'record':rec,'reused_v11_prediction_sha256':sha(cached),'raw_ADC_sha256':hashlib.sha256(raw.tobytes()).hexdigest(),'window_raw_sha256':hashlib.sha256(windows.tobytes()).hexdigest()});print(ds,rec,'complete',flush=True)
 result={'protocol':{'scope':'Retrospective Final Test comparison; no tuning. Ungated native peaks, same stored detector centers as V11, no detector replay or V11 inference rerun. Not full firmware quality gate.','thresholds':thresholds,'matching':'greedy one-to-one nearest within38 samples; BEATS=NLRBAaJSVrFejnE/fQ?','accounting':'all missed V=FN; missing N abstention not TN; matched OTHER excluded N/V; unmatched PVC alarms=FP; unmatched does not mean noise','preprocessing':'exact final V11 test signal/ADC reconstruction, center-128:center+128, float32 window z-score','RR':'V11 cached output uses current/prior detector peaks, locked Fit scaling; no annotation RR','restriction':'No subsequent model/detector/threshold optimization from these Test results'},'models':{m:{'path':str(p.relative_to(ROOT)),'sha256':expected[m]} for m,p in paths.items()},'reused_V11_evaluation_sha256':sha(OLD/'evaluation.json'),'records':rows,'sources':sources,'summary':{},'groups':[]}
 for ds in ['MITBIH','INCART']:
  result['summary'][ds]={m:aggregate([r for r in rows if r['dataset']==ds and r['model']==m]) for m in ['V4','V6','V11']}
  for group in sorted(set(r['patient_or_record_group'] for r in rows if r['dataset']==ds)):
   for m in ['V4','V6','V11']:result['groups'].append(dict(dataset=ds,group=group,model=m,**aggregate([r for r in rows if r['dataset']==ds and r['patient_or_record_group']==group and r['model']==m])))
 write(OUT/'evaluation.json',result)
 lines=['# V4/V6/V11 FP32 Test end-to-end comparison','','Retrospective comparison on previously inspected Test. Frozen checkpoints/thresholds. Only V4/V6 inference added; V11 stored predictions reused and per-record confusion counts reproduced exactly. Same native detector centers, reconstructed raw windows and greedy tolerance38 matching. Ungated; no fabricated lead-off/RTOS/quality recovery simulation. Not independent confirmatory evidence.','', '| Dataset | Model | Precision | Recall PVC | F1 | TP | FP | FN | TN | FP/1000 reference N |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for ds,ms in result['summary'].items():
  for m,v in ms.items():lines.append(f"| {ds} | {m} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {v['TP']} | {v['FP']} | {v['FN']} | {v['TN']} | {v['fp_per_1000_N']:.2f} |")
 lines+=['','Unmatched alarms are scored FP but not proven noise: T/P, localization, rhythm/outside annotation scope or unannotated real events remain possible. OTHER beat matches are not relabeled N; only N/V classification scored. Missed V retained FN. Missed N reported separately and not TN; event ledger is not a fixed binary population. MIT missed688N/56V with2955 unmatched peaks; INC missed361N/366V with3443 unmatched. No quality-gated deployment claim.','', '## Per-record FP decomposition','', '| Dataset | Record | Patient/group | Model | Precision | Recall | F1 | FP N matched | FP unmatched alarm | FN |','|---|---|---|---|---:|---:|---:|---:|---:|---:|']
 for r in sorted(rows,key=lambda r:(r['dataset'],r['record'],r['model'])):
  v=aggregate([r]);lines.append(f"| {r['dataset']} | {r['record']} | {r['patient_or_record_group']} | {r['model']} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {r['FP_matched_N']} | {r['FP_unmatched_alarm']} | {r['FN']} |")
 lines+=['','## Patient/record groups','', '| Dataset | Group | Model | Precision | Recall | F1 | FP | FN |','|---|---|---|---:|---:|---:|---:|---:|']
 for v in result['groups']:lines.append(f"| {v['dataset']} | {v['group']} | {v['model']} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {v['FP']} | {v['FN']} |")
 (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8');print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
