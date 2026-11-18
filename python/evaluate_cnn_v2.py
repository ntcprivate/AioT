"""Frozen V2 assessment on cached old Validation, never used for model selection."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
from pathlib import Path
import json,time,hashlib
import numpy as np
import tensorflow as tf
from cnn_v2_common import metrics,lite_scores
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v2';MODELS=ROOT/'models/v2'
def main():
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    training=json.loads((OUT/'training.json').read_text());meta=json.loads((OUT/'cached_validation_metadata.json').read_text())
    z=np.load(OUT/'cached_validation_windows.npz');X=z['X'];y=z['y'];hard=z['hard'];ids=z['ids'];keep=y>=0
    result={'scope':'Historical Validation, exploratory only. Checkpoint and export decision frozen before this inference. No Test.','models':{}}
    scores={'V1_INT8':z['v1_int8_scores']};latency={}
    for name,path in [('V1_FLOAT32',ROOT/'models/ecg_cnn_best.keras'),('V2_FLOAT32',MODELS/'ecg_cnn_v2_best.keras')]:
        model=tf.keras.models.load_model(path,compile=False);start=time.perf_counter();scores[name]=model.predict(X,batch_size=128,verbose=0).reshape(-1);latency[name]=(time.perf_counter()-start)*1000/len(X)
    if training['export_selected']:
        start=time.perf_counter();s,c,clipped,i,o=lite_scores(tf,MODELS/'ecg_cnn_v2_int8.tflite',X,True);scores['V2_INT8']=s;latency['V2_INT8']=(time.perf_counter()-start)*1000/len(X)
        result['v2_input_clip_count']=int(sum(clipped));np.save(OUT/'validation_v2_clipped.npy',clipped)
    for name,s in scores.items():
        # Same frozen safety-admitted windows for direct model comparison.
        pred=s>=.52;m=metrics(y[keep],s[keep],hard[keep]);cm=np.array(m['confusion_rows_N_V']);strict={}
        for label,cls in enumerate(('N','V')):
            tp=int(cm[label,label]);fp=int(cm[:,label].sum()-tp)+int(sum((y==-2)&(pred==bool(label))))
            fn=int(cm[label,:].sum()-tp)+sum(r['miss_'+cls] for r in meta['records'])
            strict[cls]=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn),f1=2*tp/(2*tp+fp+fn))
        per_record=[]
        for rid in sorted(set(ids)):
            k=keep&(ids==rid);per_record.append(dict(record=rid,**metrics(y[k],s[k],hard[k])))
        result['models'][name]=dict(conditional=m,end_to_end=strict,matched_windows=int(sum(keep)),classified_windows=len(X),miss_before_cnn={'N':66,'V':24},unmatched_PVC=int(sum((y==-2)&pred)),other_annotation_windows=int(sum(y==-1)),other_annotation_PVC=int(sum((y==-1)&pred)),per_record=per_record,host_batch_ms_per_window=latency.get(name),latency_limit='Host batch processing including prediction IO, not ESP32 single-beat latency; detector/window delay unchanged and inherited from original replay')
    assert result['models']['V1_INT8']['conditional']['confusion_rows_N_V']==[[10673,428],[136,1141]]
    assert abs(result['models']['V1_INT8']['end_to_end']['V']['f1']-meta['baseline']['end_to_end_metrics_with_misses_and_unmatched']['V']['f1'])<1e-12
    np.savez_compressed(OUT/'historical_validation_scores.npz',**scores)
    result['deploy_recommendation']='KEEP_V1; no firmware/model replacement authorized by this run'
    result['v2_int8_status']='EXPORTED_FOR_OFFLINE_CHECKS_ONLY' if training['export_selected'] else 'NOT_EXPORTED: development selection rule not met; quantization/parity/arena checks not applicable'
    protected=json.loads((OUT/'protected_sha256.json').read_text());assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in protected.items())
    result['protected_files_unchanged']=len(protected)
    (OUT/'evaluation.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({n:{'conditional':r['conditional'],'end_to_end':r['end_to_end']['V']} for n,r in result['models'].items()},indent=2))
if __name__=='__main__':main()
