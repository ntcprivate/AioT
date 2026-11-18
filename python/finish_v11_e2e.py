import json
import numpy as np
import wfdb
from evaluate_v11_e2e import ROOT,OUT,score
from run_v11_rr import BEATS
records=[];totals={};ns={}
for file in sorted(OUT.glob('*_predictions.npz')):
    ds,rec=file.stem.replace('_predictions','').split('_');data=np.load(file);peaks=data['peaks'];emits=data['emits']
    base=ROOT/('mit-bih-arrhythmia-database-1.0.0' if ds=='MITBIH' else 'files')/rec
    h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS]
    used=set();pairs={};offset=[];late=0
    for ri,(t,c) in enumerate(refs):
        cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
        if cand:
            j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);pairs[ri]=j;offset.append(int(peaks[j]-t));late+=int(c in {'N','V'} and emits[j]>t+128)
    n=sum(c=='N' for t,c in refs);v=sum(c=='V' for t,c in refs);mn=sum(c=='N' and i not in pairs for i,(t,c) in enumerate(refs));mv=sum(c=='V' and i not in pairs for i,(t,c) in enumerate(refs))
    row=dict(dataset=ds,record=rec,reference_N=n,reference_V=v,missed_N=mn,missed_V=mv,all_beat_FN=len(refs)-len(pairs),extra_peaks=len(peaks)-len(used),offset_samples=offset,old_deadline_rejected_NV=late,metrics={})
    totals.setdefault(ds,{m:np.zeros(4,dtype=np.int64) for m in ['V6','V11','fallback']});ns[ds]=ns.get(ds,0)+n
    for name,pred in [('V6',data['pred6']),('V11',data['pred11']),('fallback',np.where(data['fallback'],data['pred6'],data['pred11']))]:
        tp=fp=tn=0;fn=mv
        for i,j in pairs.items():
            c=refs[i][1]
            if c not in {'N','V'}:continue
            tp+=int(c=='V' and pred[j]);fn+=int(c=='V' and not pred[j]);fp+=int(c=='N' and pred[j]);tn+=int(c=='N' and not pred[j])
        fp+=sum(int(pred[j]) for j in range(len(peaks)) if j not in used)
        totals[ds][name]+=np.array([tp,fp,fn,tn]);row['metrics'][name]=score(tp,fp,fn,tn,n)
    records.append(row)
result={'scope':'Original Development only. Ungated detector windows; no firmware safety gate. Missing V counts FN; missing N reported separately, never counted TN. OTHER excluded, not relabeled N. Pooled micro metrics, not comparable directly with prior fold means. Fixed fallback: fewer than 2 RR intervals or absolute Fit z-score >3 on timing features.','records':records,'pooled':{ds:{m:score(*map(int,v),ns[ds]) for m,v in ms.items()} for ds,ms in totals.items()}}
(OUT/'evaluation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result['pooled'],indent=2))
for ds in totals:
    rr=[r for r in records if r['dataset']==ds];print(ds,{k:sum(r[k] for r in rr) for k in ['reference_N','reference_V','missed_N','missed_V','all_beat_FN','extra_peaks','old_deadline_rejected_NV']})
