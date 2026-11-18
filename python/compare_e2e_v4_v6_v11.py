import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/model_comparison/end_to_end_v4_v6_v11';BEATS=set('NLRBAaJSVrFejnE/fQ?')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def metric(a):
 tp,fp,fn,tn,n=[sum(int(v[k]) for v in a) for k in ['TP','FP','FN','TN','reference_N']];p=tp/(tp+fp) if tp+fp else 0;r=tp/(tp+fn) if tp+fn else 0
 return dict(TP=tp,FP=fp,FN=fn,TN=tn,precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,fp_per_1000_N=fp*1000/n if n else 0,missingN=sum(v['missingN'] for v in a),missingV=sum(v['missingV'] for v in a))
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'evaluation.json').exists():raise RuntimeError('Completed comparison exists')
 priorpath=ROOT/'results/cnn_v11/rpeak_optimization/evaluation.json';prior=json.loads(priorpath.read_text());rows=[r.copy() for r in prior['records'] if r['stage']=='old'];cohort=sorted(set((r['dataset'],r['record'],r['group']) for r in rows))
 paths={'V4':ROOT/'models/v4/ecg_cnn_v4_best.keras','V6':ROOT/'models/v6/ecg_cnn_v6_best.keras','V11':ROOT/'models/v11/v11_final_best.keras'}
 assert sha(paths['V4'])==json.loads((ROOT/'results/cnn_v4/selection.json').read_text())['model_sha256']
 assert sha(paths['V6'])==json.loads((ROOT/'results/cnn_v6/evaluation.json').read_text())['checkpoint_sha256']
 assert sha(paths['V11'])==json.loads((ROOT/'results/cnn_v11/final_test/locked.json').read_text())['sha256']
 tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
 model=tf.keras.models.load_model(paths['V4'],compile=False);details=[];trace_hashes={}
 for ds,rec,group in cohort:
  cache=OUT/f'{ds}_{rec}_V4.json'
  if cache.exists():row=json.loads(cache.read_text());rows.append(row);continue
  base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');lead=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII')
  signal=resample_poly(wfdb.rdrecord(str(base),channels=[lead]).p_signal[:,0],250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*signal),0,4095)
  log=ROOT/f'results/cnn_v11/rr_detector_validation/{ds}_{rec}.csv';trace_hashes[ds+'_'+rec]=sha(log)
  peaks=np.array([int(v[1]) for line in log.read_text().splitlines() if (v:=line.split(','))[0]=='peak'])
  assert np.all(np.diff(peaks)>0)
  x=np.stack([raw[p-128:p+128] for p in peaks]).astype(np.float32)[:,:,None];assert np.isfinite(x).all() and np.all(x.std(1)>1e-8)
  x=(x-x.mean(1,keepdims=True))/np.maximum(x.std(1,keepdims=True),1e-8)
  scores=model.predict(x,batch_size=512,verbose=0).ravel();pred=scores>=.88
  refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS];used=set();pairs={};offset=[]
  for ri,(t,c) in enumerate(refs):
   cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
   if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);pairs[ri]=j;offset.append(int(peaks[j]-t))
  tp=fp=fn=tn=mn=mv=0
  for ri,(t,c) in enumerate(refs):
   if c not in {'N','V'}:continue
   if ri not in pairs:fn+=int(c=='V');mv+=int(c=='V');mn+=int(c=='N');continue
   p=pred[pairs[ri]];tp+=int(c=='V' and p);fp+=int(c=='N' and p);fn+=int(c=='V' and not p);tn+=int(c=='N' and not p)
  fpn=fp;fpx=sum(int(pred[j]) for j in range(len(peaks)) if j not in used);fp+=fpx
  row=dict(dataset=ds,record=rec,group=group,stage='old',model='V4',reference_N=sum(c=='N' for t,c in refs),peakTP=len(pairs),peakFP=len(peaks)-len(used),peakFN=len(refs)-len(pairs),missingN=mn,missingV=mv,TP=tp,FP=fp,FN=fn,TN=tn)
  old=next(v for v in rows if v['dataset']==ds and v['record']==rec)
  for key in ['reference_N','peakTP','peakFP','peakFN','missingN','missingV']:assert old[key]==row[key],(rec,key)
  row.update(metric([row]));cache.write_text(json.dumps(row,indent=2));rows.append(row)
  details.append(dict(dataset=ds,record=rec,matched_OTHER=sum(refs[i][1] not in {'N','V'} for i in pairs),out_of_scope_annotation_symbols=sorted(set(ann.symbol)-BEATS),FP_matched_N=fpn,FP_unmatched_alarm=fpx,timing_abs_p95_samples=float(np.percentile(abs(np.array(offset)),95))))
  np.savez_compressed(OUT/f'{ds}_{rec}_V4_scores.npz',peaks=peaks,scores=scores,predictions=pred);print(ds,rec,'V4 complete',flush=True)
 folds=json.loads((ROOT/'results/v10_research/step1_5fold_cv/folds_split.json').read_text())
 result={'protocol':{'scope':'Original Development only, 7 MIT records + 11 INCART records; no Train metrics or Final Test inference','gate':'ungated peak stream; firmware quality/recovery/lead-off/timing not simulated','thresholds':{'V4':.88,'V6':.87,'V11':.80},'matching':'greedy one-to-one nearest within38 samples; full BEATS reference, missing V=FN, missing N abstention, unmatched PVC alarm=FP, matched OTHER excluded N/V','RR':'V11 current/prior detector peaks, frozen Fit scaling, no future peak or label input','selection_limit':'All three models used Development for selection; results exploratory, not independent or OOF','fold_definition':'group bins inherited from CV split, using final models; no new five-fold training and empty bins not reported as zero','reused_V6_V11':str(priorpath.relative_to(ROOT)),'reused_metrics_sha256':sha(priorpath),'source_pipeline':'python/evaluate_rpeak_candidate_v11.py stage old; identical raw representation, centers, zscore and matching for added V4'},'models':{m:{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for m,p in paths.items()},'trace_sha256':trace_hashes,'records':rows,'scope_details':details,'summary':{},'patient_groups':[],'folds':[]}
 for ds in ['MITBIH','INCART']:
  result['summary'][ds]={m:metric([r for r in rows if r['dataset']==ds and r['model']==m]) for m in ['V4','V6','V11']}
  for m in ['V4','V6','V11']:
   for group in sorted(set(r['group'] for r in rows if r['dataset']==ds)):
    a=[r for r in rows if r['dataset']==ds and r['model']==m and r['group']==group];result['patient_groups'].append(dict(dataset=ds,model=m,group=group,**metric(a)))
   for f in folds:
    groups=f['outer_MITBIH_records' if ds=='MITBIH' else 'outer_INCART_patients'];a=[r for r in rows if r['dataset']==ds and r['model']==m and r['group'] in groups]
    if a:result['folds'].append(dict(dataset=ds,model=m,fold=f['fold_index'],records=[r['record'] for r in a],**metric(a)))
 (OUT/'evaluation.json').write_text(json.dumps(result,indent=2))
 lines=['# Fair FP32 detector-window comparison: V4/V6/V11','','Original Development only; ungated, adaptive evaluation, not independent or OOF. Same native detector centers and ECG windows, final models at locked thresholds. Only V4 inference added; V6/V11 stage-old metrics reused after detector reference/miss count checks.','', '| Dataset | Model | Precision | Recall | F1 | TP | FP | FN | TN | FP/1000 N |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for ds,ms in result['summary'].items():
  for m,v in ms.items():lines.append(f"| {ds} | {m} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {v['TP']} | {v['FP']} | {v['FN']} | {v['TN']} | {v['fp_per_1000_N']:.2f} |")
 lines+=['','Missing V are FN; missed N remain reported abstentions, never TN. Same detector missing counts for every model: MIT34N+14V; INCART324N+19V. Matching includes OTHER beat symbols; predictions on matched OTHER excluded, never relabeled Normal. Unmatched does not establish noise: outside-scope annotations/rhythm, localization, T/P and unannotated events remain possible. Neither raw lead-off nor real RTOS/gap/age data are available; no fabricated hardware quality gate. No claim of complete firmware equivalence.','', 'Per record, patient/group and occupied fold bins are in evaluation.json. Fold bins are descriptive subsets of Development, not new independent CV. V4/V6/V11 all used this Development in checkpoint/threshold selection; label exposure differs between datasets/models. Fixed-model protocol fairness does not imply equal independent training selection or unbiased generalization.','', '## Per-record and patient results','', '| Dataset | Record | Patient/group | Model | P | R | F1 | TP | FP | FN | FP/1000 N |','|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for r in sorted(rows,key=lambda r:(r['dataset'],r['record'],r['model'])):
  v=metric([r]);lines.append(f"| {r['dataset']} | {r['record']} | {r['group']} | {r['model']} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {v['TP']} | {v['FP']} | {v['FN']} | {v['fp_per_1000_N']:.2f} |")
 lines+=['','## Fold bins','', '| Dataset | Fold | Model | Precision | Recall | F1 | TP | FP | FN | FP/1000 N |','|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
 for v in result['folds']:lines.append(f"| {v['dataset']} | {v['fold']} | {v['model']} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {v['TP']} | {v['FP']} | {v['FN']} | {v['fp_per_1000_N']:.2f} |")
 (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8');print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
