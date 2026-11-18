import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
from run_v11_rr import BEATS,rr_at
from evaluate_v11_e2e import score
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/rpeak_optimization'
def main():
 if (OUT/'evaluation.json').exists():raise RuntimeError('exists')
 lock=json.loads((ROOT/'results/cnn_v11/final_test/locked.json').read_text());mean=np.array(lock['rr_fit_mean']);sd=np.array(lock['rr_fit_std'])
 m11=tf.keras.models.load_model(ROOT/'models/v11/v11_final_best.keras',compile=False);m6=tf.keras.models.load_model(ROOT/'models/v6/ecg_cnn_v6_best.keras',compile=False)
 mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');spl=np.load(ROOT/'data/processed/mitbih_split_indices.npz');inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
 devmit=set(mit['record_ids'][spl['validation_indices']]);devinc=set(inc['record_ids'][inc['split']=='validation']);rows=[]
 for log in sorted((ROOT/'results/cnn_v11/rr_detector_validation').glob('*.csv')):
  ds,rec=log.stem.split('_',1)
  if rec not in (devmit if ds=='MITBIH' else devinc):continue
  base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');ch=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII')
  signal=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*signal),0,4095)
  peaks=np.array([int(v[1]) for s in log.read_text().splitlines() if (v:=s.split(','))[0]=='peak']);slopes=np.array([np.max(abs(np.diff(raw[p-8:p+9]))) for p in peaks]);gate=np.r_[False,(np.diff(peaks)<150)&(slopes[1:]<.5*slopes[:-1])]
  refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS];n=sum(c=='N' for t,c in refs)
  group=rec if ds=='MITBIH' else str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==rec)[0]])
  for stage,pp in [('old',peaks),('candidate',peaks[~gate])]:
   x=np.stack([raw[p-128:p+128] for p in pp]).astype(np.float32)[:,:,None];x=(x-x.mean(1,keepdims=True))/np.maximum(x.std(1,keepdims=True),1e-8)
   rr=np.array([rr_at(pp[:j+1]/250.,pp[j]/250.) for j in range(len(pp))]);sc11=m11.predict({'ecg_256':x,'rr_features':(rr-mean)/sd},batch_size=512,verbose=0).ravel();sc6=m6.predict(x,batch_size=512,verbose=0).ravel()
   used=set();pairs={};offset=[]
   for ri,(t,c) in enumerate(refs):
    cand=[int(j) for j in np.flatnonzero(abs(pp-t)<=38) if int(j) not in used]
    if cand:j=min(cand,key=lambda j:abs(pp[j]-t));used.add(j);pairs[ri]=j;offset.append(int(pp[j]-t))
   for name,pred in [('V11',sc11>=.8),('V6',sc6>=.87)]:
    tp=fp=tn=fn=0;missN=missV=0
    for ri,(t,c) in enumerate(refs):
     if c not in {'N','V'}:continue
     if ri not in pairs:fn+=int(c=='V');missV+=int(c=='V');missN+=int(c=='N');continue
     p=pred[pairs[ri]];tp+=int(c=='V' and p);fp+=int(c=='N' and p);fn+=int(c=='V' and not p);tn+=int(c=='N' and not p)
    fp+=sum(int(pred[j]) for j in range(len(pp)) if j not in used)
    rows.append(dict(dataset=ds,record=rec,group=group,stage=stage,model=name,reference_N=n,peakTP=len(pairs),peakFP=len(pp)-len(used),peakFN=len(refs)-len(pairs),timing_abs_mean_samples=float(np.mean(abs(np.array(offset)))),missingN=missN,missingV=missV,**score(tp,fp,fn,tn,n)))
  print(ds,rec,'done',flush=True)
 result={'scope':'Original Development only, final locked V11 and final V6; in-development comparison, not OOF. No Test. Candidate is offline causal post-window confirmation; unchanged native peak stream precedes gate. Rejected peak still affected original detector refractory, so this is not a retrained or reimplemented detector.','rule':'RR<150 samples and max raw difference in peak +/-8 samples <0.5 previous detected peak slope; available before window completion','records':rows,'summary':{}}
 for ds in ['MITBIH','INCART']:
  result['summary'][ds]={}
  for stage in ['old','candidate']:
   for model in ['V6','V11']:
    a=[r for r in rows if r['dataset']==ds and r['stage']==stage and r['model']==model];v={k:sum(r[k] for r in a) for k in ['TP','FP','FN','TN','peakTP','peakFP','peakFN','missingN','missingV']};v.update(score(v['TP'],v['FP'],v['FN'],v['TN'],sum(r['reference_N'] for r in a)));v['peak_sensitivity']=v['peakTP']/(v['peakTP']+v['peakFN']);v['peak_ppv']=v['peakTP']/(v['peakTP']+v['peakFP']);result['summary'][ds][stage+'_'+model]=v
 (OUT/'evaluation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
