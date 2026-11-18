"""Train-development cached Float32 scores only; no inference, fit or old holdouts."""
from pathlib import Path
import csv,hashlib,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/cnn_v2';OUT=BASE/'threshold_review'
def at(y,s,t):
    p=s>=t;tp=int(sum((y==1)&p));fp=int(sum((y==0)&p));fn=int(sum((y==1)&~p));tn=int(sum((y==0)&~p))
    return dict(threshold=float(t),precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn),f1=2*tp/(2*tp+fp+fn),fp=fp,fn=fn,tp=tp,tn=tn)
def pr_auc(y,s):
    order=np.argsort(-s,kind='stable');a=s[order];truth=y[order];end=np.r_[np.flatnonzero(np.diff(a)),len(a)-1]
    tp=np.cumsum(truth)[end];precision=tp/(end+1);recall=tp/sum(y)
    return dict(trapezoidal_pr_auc=float(np.trapezoid(np.r_[1.,precision],np.r_[0.,recall])),average_precision=float(np.sum(np.diff(np.r_[0.,recall])*precision)),positive_class='PVC',tie_policy='all identical scores grouped')
def main():
    OUT.mkdir(exist_ok=True)
    z=np.load(BASE/'development_predictions.npz');d=np.load(BASE/'train_only.npz');cfg=json.loads((BASE/'config.json').read_text())
    np.testing.assert_array_equal(z['indices'],d['global_indices'][d['development']]);np.testing.assert_array_equal(z['y'],d['y'][d['development']])
    assert not set(d['global_indices'][d['fit']])&set(z['indices'])
    y=z['y'];result={'records':cfg['development_records'],'samples':len(y),'N':int(sum(y==0)),'V':int(sum(y==1)),'models':{},'source_sha256':hashlib.sha256((BASE/'development_predictions.npz').read_bytes()).hexdigest(),'selection':'max V2 F1 on66 grid thresholds .30..95; tie higher precision then smaller threshold','limitations':['V2 development excluded from weight fitting but already used for early stopping and now threshold selection; not independent.','V1 previously fitted these original Train records; comparison optimistic for V1.','No old Validation/Test data used for threshold selection.']}
    rows=[]
    for name,key in [('V1','v1_float'),('V2','v2_float')]:
        s=z[key];assert np.isfinite(s).all() and np.all((s>=0)&(s<=1))
        local=[at(y,s,k/100) for k in range(30,96)];best=max(local,key=lambda r:(r['f1'],r['precision'],-r['threshold']))
        result['models'][name]=dict(at_052=at(y,s,.52),best=best,pr=pr_auc(y,s),all_best_f1_thresholds=[r['threshold'] for r in local if r['f1']==best['f1']])
        for r in local:rows.append(dict(model=name,**r))
    t=result['models']['V2']['best']['threshold'];result['models']['V1']['at_v2_selected']=at(y,z['v1_float'],t)
    result['selected_threshold']=t
    with (OUT/'threshold_sweep.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (OUT/'selection.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
