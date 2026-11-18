"""Only required Float32 inference on new development detector windows; no tuning."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
from pathlib import Path
import json,hashlib
import numpy as np
import tensorflow as tf
from review_cnn_v2_threshold import at
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/cnn_v2';OUT=BASE/'threshold_review'
def main():
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    selection=json.loads((OUT/'selection.json').read_text());meta=json.loads((OUT/'development_e2e_metadata.json').read_text())
    z=np.load(OUT/'development_e2e_windows.npz');X=z['X'];y=z['y'];keep=y>=0
    result={'protocol':meta,'models':{},'scope':'same Train-development records; threshold selected beforehand on annotation-centered scores, no end-to-end threshold retuning'};all_scores={}
    for name,path in [('V1',ROOT/'models/ecg_cnn_best.keras'),('V2',ROOT/'models/v2/ecg_cnn_v2_best.keras')]:
        model=tf.keras.models.load_model(path,compile=False);s=model.predict(X,batch_size=128,verbose=0).reshape(-1);all_scores[name]=s
        for t in ([.52] if name=='V1' else [.52,selection['selected_threshold']]):
            m=at(y[keep],s[keep],t);p=s>=t;unmatched=int(sum((y==-2)&p));miss=sum(r['miss_V'] for r in meta['records']);tp=m['tp'];fp=m['fp']+unmatched;fn=m['fn']+miss
            result['models'][f'{name}_{t:.2f}']=dict(conditional=m,end_to_end=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else 0,recall=tp/(tp+fn) if tp+fn else 0,f1=2*tp/(2*tp+fp+fn) if tp+fp+fn else 0),unmatched_PVC=unmatched,miss_before_CNN_N=sum(r['miss_N'] for r in meta['records']),miss_before_CNN_V=miss,other_annotation_windows=int(sum(y==-1)),other_annotation_PVC=int(sum((y==-1)&p)))
    np.savez_compressed(OUT/'development_e2e_scores.npz',**all_scores)
    protected=json.loads((BASE/'protected_sha256.json').read_text());assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in protected.items())
    result['protected_files_unchanged']=len(protected)
    (OUT/'end_to_end.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['models'],indent=2))
if __name__=='__main__':main()
