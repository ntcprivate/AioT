import json
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly
from run_v11_rr import BEATS
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/rpeak_optimization'
def main():
 OUT.mkdir(exist_ok=True,parents=True);rows=[]
 for log in sorted((ROOT/'results/cnn_v11/rr_detector_validation').glob('*.csv')):
  ds,rec=log.stem.split('_',1);base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec
  h=wfdb.rdheader(str(base));a=wfdb.rdann(str(base),'atr');refs=np.array([int(np.floor(s*250/h.fs+.5)) for s,c in zip(a.sample,a.symbol) if c in BEATS]);symbols=[c for c in a.symbol if c in BEATS]
  peaks=np.array([int(v[1]) for s in log.read_text().splitlines() if (v:=s.split(','))[0]=='peak']);used=set();match={}
  for ri,t in enumerate(refs):
   cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
   if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);match[j]=symbols[ri]
  ch=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII');sig=wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0];sig=resample_poly(sig,250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*sig),0,4095)
  slopes=np.array([np.max(abs(np.diff(raw[max(0,p-8):p+9]))) for p in peaks]);ratio=np.divide(slopes[1:],np.maximum(slopes[:-1],1e-8));short=np.diff(peaks)<150;gate=np.r_[False,short&(ratio<.5)]
  fp=[j for j in range(len(peaks)) if j not in used];other=sum(c not in {'N','V'} for c in match.values());distance=[int(min(abs(refs-peaks[j]))) for j in fp]
  rows.append(dict(dataset=ds,record=rec,reference=len(refs),TP=len(match),FP=len(fp),FN=len(refs)-len(match),matched_OTHER=other,fp_within_75_samples=sum(t<=75 for t in distance),gate_rejected_FP=int(sum(gate[j] for j in fp)),gate_rejected_true=int(sum(gate[j] for j in used)),gate_rejected_PVC=int(sum(gate[j] and match[j]=='V' for j in used))))
 result={'records':rows,'summary':{}}
 for ds in ['MITBIH','INCART']:
  rr=[r for r in rows if r['dataset']==ds];result['summary'][ds]={k:sum(r[k] for r in rr) for k in rr[0] if k not in ['dataset','record']}
 (OUT/'diagnosis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
