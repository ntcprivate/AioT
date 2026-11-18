"""Shared fixed-threshold metrics and unchanged INT8 contract for V2 offline work."""
import numpy as np
THRESHOLD=.52
def metrics(y,scores,hard=None):
    y=np.asarray(y);scores=np.asarray(scores);assert y.shape==scores.shape and np.isfinite(scores).all()
    pred=scores>=THRESHOLD;cm=np.zeros((2,2),dtype=np.int64)
    np.add.at(cm,(y,pred.astype(int)),1);tn,fp,fn,tp=map(int,cm.ravel())
    divide=lambda a,b:a/b if b else 0.
    r=dict(confusion_rows_N_V=cm.tolist(),N_to_PVC=fp,PVC_to_N=fn,precision=divide(tp,tp+fp),recall=divide(tp,tp+fn),f1=divide(2*tp,2*tp+fp+fn),normal_recall=divide(tn,tn+fp))
    if hard is not None:
        hard=np.asarray(hard,dtype=bool);r['normal_neighbor_pvc']=dict(samples=int(hard.sum()),false_positive=int(np.sum(pred&hard)),normal_recall=divide(int(np.sum(~pred&hard)),int(hard.sum())))
    return r
def lite_scores(tf,path,X,return_codes=False):
    it=tf.lite.Interpreter(model_path=str(path),num_threads=1,experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
    it.allocate_tensors();i=it.get_input_details()[0];o=it.get_output_details()[0]
    assert tuple(i['shape'])==(1,256,1) and tuple(o['shape'])==(1,1)
    scores=np.empty(len(X));codes=np.empty(len(X),dtype=np.int8);clips=np.zeros(len(X),dtype=bool)
    for j,x in enumerate(X):
        if i['dtype']==np.int8:
            s,z=i['quantization'];q=np.rint(x.astype(np.float64)/s)+z;clips[j]=np.any((q<-128)|(q>127));v=np.clip(q,-128,127).astype(np.int8)
        else:v=x.astype(np.float32)
        it.set_tensor(i['index'],v[None]);it.invoke();value=it.get_tensor(o['index']).item()
        if o['dtype']==np.int8:
            codes[j]=value;s,z=o['quantization'];scores[j]=(value-z)*s
        else:scores[j]=value
    return (scores,codes,clips,i,o) if return_codes else scores
