"""V4-A: one lightweight verification family, group-separated selection.

No training, RR input, Test record, firmware mutation or threshold optimization.
"""
import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,hashlib,time
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v4/qrs_verification_v4a';BEATS=set('NLRBAaJSVrFejnE/fQ?')
MODEL=ROOT/'models/v4/ecg_cnn_v4_best.keras'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else x))
def features(w):
 # Squared first-difference energy, same width for central and neighbor support.
 # A weak slope alone never rejects; a stronger off-center component is required.
 d=np.diff(w.astype(np.float64),axis=1)**2
 c=np.concatenate([np.zeros((len(w),1)),np.cumsum(d,axis=1)],axis=1)
 rolling=c[:,48:]-c[:,:-48]
 at=np.argmax(rolling,axis=1);maximum=np.max(rolling,axis=1)
 central=np.sum(d[:,104:152],axis=1)
 ratio=np.divide(central,maximum,out=np.ones(len(w)),where=maximum>1e-12)
 return ratio,np.abs((at+24)-128)
def assign(ref,peaks):
 used=set();match=np.full(len(ref),-1,np.int64)
 for ri,t in enumerate(ref):
  cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
  if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));match[ri]=j;used.add(j)
 return match,used
def metric(row,keep):
 peaks=row['peaks'][keep];pred=row['scores'][keep]>=.88;m,used=assign(row['ref'],peaks)
 tp=fp=fn=tn=mn=mv=0
 for ri,c in enumerate(row['symbols']):
  if c not in {'N','V'}:continue
  if m[ri]<0:fn+=int(c=='V');mn+=int(c=='N');mv+=int(c=='V');continue
  p=pred[m[ri]];tp+=int(c=='V' and p);fp+=int(c=='N' and p);fn+=int(c=='V' and not p);tn+=int(c=='N' and not p)
 fpn=fp;fp_extra=sum(int(pred[j]) for j in range(len(peaks)) if j not in used);fp+=fp_extra
 oldmatch,_=assign(row['ref'],row['peaks']);rejectedV=sum(c=='V' and oldmatch[ri]>=0 and not keep[oldmatch[ri]] for ri,c in enumerate(row['symbols']))
 return dict(TP=tp,FP=fp,FN=fn,TN=tn,FP_matched_N=fpn,FP_unmatched_alarm=fp_extra,reference_N=int(sum(row['symbols']=='N')),reference_V=int(sum(row['symbols']=='V')),peakTP=len(used),peakFP=len(peaks)-len(used),peakFN=len(row['ref'])-len(used),missing_N=mn,missing_V=mv,rejected_true_PVC=int(rejectedV),rejected_candidates=int(sum(~keep)),matched_OTHER=int(sum(c not in {'N','V'} and m[ri]>=0 for ri,c in enumerate(row['symbols']))))
def aggregate(values):
 keys=list(values[0]);out={k:sum(int(v[k]) for v in values) for k in keys};tp,fp,fn=out['TP'],out['FP'],out['FN'];p=tp/(tp+fp) if tp+fp else 0;r=tp/(tp+fn) if tp+fn else 0
 out.update(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,fp_per_1000_N=out['FP']*1000/out['reference_N'] if out['reference_N'] else 0,peak_sensitivity=out['peakTP']/(out['peakTP']+out['peakFN']),peak_ppv=out['peakTP']/(out['peakTP']+out['peakFP']) if out['peakTP']+out['peakFP'] else 0);return out
def gate(row,t):return ~((row['ratio']<t)&(row['offset']>40))
def evaluate(rows,t):
 return {ds:aggregate([metric(r,gate(r,t)) for r in rows if r['dataset']==ds]) for ds in ['MITBIH','INCART']}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'evaluation.json').exists():raise RuntimeError('Complete artifacts exist; refusing overwrite')
 select=json.loads((ROOT/'results/cnn_v4/selection.json').read_text());assert sha(MODEL)==select['model_sha256'] and select['selected_threshold']==.88
 foldpath=ROOT/'results/v10_research/step1_5fold_cv/folds_split.json';f=json.loads(foldpath.read_text())[0]
 groups={role:{'MITBIH':f[key+'_MITBIH_records'],'INCART':f[key+'_INCART_patients']} for role,key in [('Fit','fit'),('Calibration','threshold'),('Evaluation','outer')]}
 # Add the former checkpoint fold to Evaluation: 40% Fit,20% calibration,40% evaluation.
 groups['Evaluation']['MITBIH']+=f['checkpoint_MITBIH_records'];groups['Evaluation']['INCART']+=f['checkpoint_INCART_patients']
 for ds in ['MITBIH','INCART']:
  assert all(not set(groups[a][ds])&set(groups[b][ds]) for a,b in [('Fit','Calibration'),('Fit','Evaluation'),('Calibration','Evaluation')])
 plan={'model':'V4 only,849 params,ECG input256x1,no RR','model_sha256':sha(MODEL),'cnn_threshold':.88,'groups':groups,'split_rule':'locked CV fold0: Fit original folds3+4, Calibration fold2, Evaluation folds0+1; split frozen before new gate feature computation','feature':'central48-sample derivative-energy / maximum48-sample derivative-energy in256; strongest support-center offset','gate_rule':'reject iff ratio < t AND strongest support offset>40samples; never reject on RR or absolute slope','threshold_candidates':[0,.05,.1,.2,.3],'selection':'Fit matched-PVC rejection <=0.1%; Calibration zero matched-PVC rejection, no increase FN, no F1 reduction on either dataset; maximize worst-dataset F1 gain then total FP reduction; smaller threshold tie','latency':'window complete at center+127; no additional samples beyond existing256 window','evaluation_limit':'Evaluation groups not used to select this gate; previously exposed in V1-V11 research, not independent new patients','matching':'unchanged greedy one-to-one +/-38samples, full BEATS; OTHER not N; missing V=FN, missing N abstention, unmatched PVC alarm=FP','test_access':'forbidden; historical Test metrics not used'}
 if (OUT/'design.json').exists():assert json.loads((OUT/'design.json').read_text())==plan
 else:write(OUT/'design.json',plan)
 tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2);model=tf.keras.models.load_model(MODEL,compile=False);assert model.count_params()==849 and len(model.inputs)==1
 inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');sp=np.load(ROOT/'data/processed/mitbih_split_indices.npz')
 allowed={'MITBIH':set(mit['record_ids'][np.concatenate([sp['train_indices'],sp['validation_indices']])]),'INCART':set(inc['record_ids'][np.isin(inc['split'],['train','validation'])])}
 corpus={};start=time.perf_counter();reuse=ROOT/'results/model_comparison/end_to_end_v4_v6_v11'
 for role in ['Fit','Calibration','Evaluation']:
  if role=='Evaluation':
   assert (OUT/'gate_locked.json').exists();locked=json.loads((OUT/'gate_locked.json').read_text());chosen=locked['selected_threshold']
  rows=[]
  for log in sorted((ROOT/'results/cnn_v11/rr_detector_validation').glob('*.csv')):
   ds,rec=log.stem.split('_',1);assert rec in allowed[ds]
   group=rec if ds=='MITBIH' else str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==rec)[0]])
   if group not in groups[role][ds]:continue
   cache=OUT/f'{ds}_{rec}_features.npz'
   if cache.exists():
    z=np.load(cache);row={k:z[k] for k in ['peaks','scores','ratio','offset','ref','symbols']}
   else:
    base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');ch=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII')
    sig=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*sig),0,4095)
    peaks=np.array([int(v[1]) for line in log.read_text().splitlines() if (v:=line.split(','))[0]=='peak']);w=np.stack([raw[p-128:p+128] for p in peaks]).astype(np.float32);ratio,offset=features(w)
    old=reuse/f'{ds}_{rec}_V4_scores.npz'
    if old.exists():z=np.load(old);np.testing.assert_array_equal(z['peaks'],peaks);scores=z['scores']
    else:
     x=((w-w.mean(1,keepdims=True))/np.maximum(w.std(1,keepdims=True),1e-8))[:,:,None];scores=model.predict(x,batch_size=512,verbose=0).ravel()
    ref=np.array([int(np.floor(s*250/h.fs+.5)) for s,c in zip(ann.sample,ann.symbol) if c in BEATS]);symbols=np.array([c for c in ann.symbol if c in BEATS]);row=dict(peaks=peaks,scores=scores,ratio=ratio,offset=offset,ref=ref,symbols=symbols);np.savez_compressed(cache,**row,source_model_sha256=sha(MODEL),trace_sha256=sha(log))
   row.update(dataset=ds,record=rec,group=group,role=role);rows.append(row)
  corpus[role]=rows;print(role,len(rows),'records features prepared',flush=True)
  if role=='Calibration':
   fit=corpus['Fit'];baseline=evaluate(rows,0);fitbase=evaluate(fit,0);trials=[]
   for t in plan['threshold_candidates']:
    a=evaluate(fit,t);b=evaluate(rows,t);ok=all(a[ds]['rejected_true_PVC']<=.001*fitbase[ds]['reference_V'] and b[ds]['rejected_true_PVC']==0 and b[ds]['FN']<=baseline[ds]['FN'] and b[ds]['f1']>=baseline[ds]['f1']-1e-12 for ds in ['MITBIH','INCART'])
    trials.append(dict(threshold=t,fit=a,calibration=b,eligible=ok,min_f1_gain=min(b[ds]['f1']-baseline[ds]['f1'] for ds in baseline),FP_reduction=sum(baseline[ds]['FP']-b[ds]['FP'] for ds in baseline)))
   best=max((t for t in trials if t['eligible']),key=lambda t:(t['min_f1_gain'],t['FP_reduction'],-t['threshold']));write(OUT/'calibration_trials.json',trials);write(OUT/'gate_locked.json',{'selected_threshold':best['threshold'],'reason':plan['selection'],'design_sha256':sha(OUT/'design.json'),'calibration_FPs_reduced':best['FP_reduction']})
 allrows=[];summary={}
 for role,rows in corpus.items():
  summary[role]={'baseline':evaluate(rows,0),'V4-A':evaluate(rows,chosen)}
  for r in rows:
   for mode,t in [('baseline',0),('V4-A',chosen)]:allrows.append(dict(dataset=r['dataset'],record=r['record'],group=r['group'],role=role,mode=mode,**metric(r,gate(r,t))))
 result={'design':plan,'gate_locked':json.loads((OUT/'gate_locked.json').read_text()),'summary':summary,'records':allrows,'wall_seconds':time.perf_counter()-start,'status':'PASS' if chosen>0 and all(summary['Evaluation']['V4-A'][ds]['FP']<summary['Evaluation']['baseline'][ds]['FP'] and summary['Evaluation']['V4-A'][ds]['f1']>summary['Evaluation']['baseline'][ds]['f1'] and summary['Evaluation']['V4-A'][ds]['rejected_true_PVC']==0 for ds in ['MITBIH','INCART']) else 'FAIL'}
 write(OUT/'evaluation.json',result);print(json.dumps({'status':result['status'],'threshold':chosen,'Evaluation':summary['Evaluation']},indent=2))
if __name__=='__main__':main()
