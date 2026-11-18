"""V3 on cached Train-development end-to-end windows; reuse V1/V2 scores."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
from pathlib import Path
import json,hashlib
import numpy as np
import tensorflow as tf
from cnn_v2_common import metrics,lite_scores
from review_cnn_v2_threshold import at
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/cnn_v2';CACHE=BASE/'threshold_review';OUT=ROOT/'results/cnn_v3'
def main():
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    training=json.loads((OUT/'training.json').read_text());meta=json.loads((CACHE/'development_e2e_metadata.json').read_text())
    z=np.load(CACHE/'development_e2e_windows.npz');X=z['X'];y=z['y'];ids=z['ids'];keep=y>=0
    cached=np.load(CACHE/'development_e2e_scores.npz');scores={n:cached[n] for n in ('V1','V2')}
    model=tf.keras.models.load_model(ROOT/'models/v3/ecg_cnn_v3_best.keras',compile=False)
    scores['V3']=model.predict(X,batch_size=128,verbose=0).reshape(-1)
    # Recover neighboring-PVC flags for detector-centered windows without rereading signals.
    import csv
    with np.load(BASE/'train_only.npz') as train:
        annotation_v={rid:train['centers'][(train['ids']==rid)&(train['y']==1)] for rid in sorted(set(ids))}
    hard=np.zeros(len(y),dtype=bool);offset=0
    for rid in sorted(set(ids)):
        with (CACHE/f'{rid}_events.csv').open() as f:centers=np.array([int(r[1]) for r in csv.reader(f) if r and r[0]=='safe_peak'])
        local=np.flatnonzero(ids==rid);assert len(local)==len(centers)
        pvc=annotation_v[rid];neighbors=np.searchsorted(pvc,centers+128)-np.searchsorted(pvc,centers-128)
        hard[local]=(y[local]==0)&(neighbors>0)
    result={'scope':'Same six original-Train development records. No old Validation/Test. Fixed threshold .52; no threshold tuning.', 'reference':meta,'models':{}}
    for name,s in scores.items():
        m=metrics(y[keep],s[keep],hard[keep]);p=s>=.52;cm=np.array(m['confusion_rows_N_V']);tp=int(cm[1,1]);unmatched=int(sum((y==-2)&p));fp=m['N_to_PVC']+unmatched;fn=m['PVC_to_N']+sum(r['miss_V'] for r in meta['records'])
        per=[]
        for rid in sorted(set(ids)):
            k=keep&(ids==rid);per.append(dict(record=rid,**metrics(y[k],s[k],hard[k])))
        result['models'][name]=dict(conditional=m,end_to_end=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn),f1=2*tp/(2*tp+fp+fn)),miss_before_CNN_N=sum(r['miss_N'] for r in meta['records']),miss_before_CNN_V=sum(r['miss_V'] for r in meta['records']),unmatched_PVC=unmatched,matched_NV=int(sum(keep)),windows=len(X),other_annotation_windows=int(sum(y==-1)),other_annotation_PVC=int(sum((y==-1)&p)),per_record=per)
    old=json.loads((CACHE/'end_to_end.json').read_text())
    for name in ('V1','V2'):assert result['models'][name]['end_to_end']==old['models'][name+'_0.52']['end_to_end']
    if training['int8_export_selected']:
        s,c,clips,i,o=lite_scores(tf,ROOT/'models/v3/ecg_cnn_v3_int8.tflite',X,True)
        result['int8_candidate']=dict(conditional=metrics(y[keep],s[keep],hard[keep]),input_clipped_windows=int(sum(clips)),note='Not a board test or proof of compatibility with current resolver; no board model replaced')
        np.savez_compressed(OUT/'end_to_end_int8_predictions.npz',scores=s,codes=c,clipped=clips)
    # Test exact architectural isolation AFTER existing full-window normalization.
    samples=X[:16].copy();changed=samples.copy();changed[:,:96]=123;changed[:,160:]=-123
    a=model(samples,training=False).numpy();b=model(changed,training=False).numpy();np.testing.assert_array_equal(a,b)
    it=tf.lite.Interpreter(model_path=str(ROOT/'models/v3/ecg_cnn_v3_float32.tflite'),experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
    it.allocate_tensors();ops=[r['op_name'] for r in it._get_ops_details()]
    result['architecture_checks']=dict(outside_crop_invariance_samples=16,maximum_score_change=float(np.max(abs(a-b))),float_tflite_operators=ops,new_resolver_requirements=sorted(set(ops)-{'CONV_2D','EXPAND_DIMS','FULLY_CONNECTED','LOGISTIC','MAX_POOL_2D','MEAN','RESHAPE'}),arena='Not measured. Different graph/ops require a separate TFLM allocation/parity check before any deployment; none run on board.')
    protected=json.loads((OUT/'protected_sha256.json').read_text());assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in protected.items())
    result['protected_files_unchanged']=len(protected)
    np.savez_compressed(OUT/'end_to_end_predictions.npz',v3=scores['V3'],y=y,hard=hard,ids=ids)
    (OUT/'evaluation.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({n:dict(conditional=r['conditional'],end_to_end=r['end_to_end'],unmatched_PVC=r['unmatched_PVC']) for n,r in result['models'].items()},indent=2))
if __name__=='__main__':main()
