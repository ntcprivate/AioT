"""Exactly one V2 fit. No Test or historical Validation access; no firmware writes."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
from pathlib import Path
import json,time,hashlib,importlib.util
import numpy as np
import tensorflow as tf
from cnn_v2_common import metrics,lite_scores
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v2';MODELS=ROOT/'models/v2'
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False))
def main():
    cfg=json.loads((OUT/'config.json').read_text());MODELS.mkdir(exist_ok=True)
    if (MODELS/'ecg_cnn_v2_best.keras').exists():raise RuntimeError('Refusing another fit over saved V2')
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.keras.utils.set_random_seed(cfg['seed']);tf.config.experimental.enable_op_determinism()
    z=np.load(OUT/'train_only.npz',allow_pickle=False);X=z['X'];y=z['y'];hard=z['hard'];fit=z['fit'];dev=z['development'];ids=z['ids']
    v1=tf.keras.models.load_model(ROOT/'models/ecg_cnn_best.keras',compile=False)
    assert v1.count_params()==849 and v1.input_shape==(None,256,1)
    v1s=v1.predict(X[dev],batch_size=128,verbose=0).reshape(-1)
    baseline={'float32':metrics(y[dev],v1s,hard[dev]),'int8':metrics(y[dev],lite_scores(tf,ROOT/'models/ecg_cnn_int8.tflite',X[dev]),hard[dev])}
    save('development_v1.json',baseline)
    model=tf.keras.models.clone_model(v1) # Fresh weights, no V1 development leakage.
    model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy')
    counts=np.bincount(y[fit],minlength=2);cw=len(fit)/(2*counts)
    epoch=np.concatenate([fit,np.repeat(fit[hard[fit]],3)])
    weights=cw[y[epoch]].astype(np.float32)
    ds=tf.data.Dataset.from_tensor_slices((X[epoch],y[epoch].astype(np.float32),weights)).shuffle(len(epoch),seed=42,reshuffle_each_iteration=True).batch(64)
    options=tf.data.Options();options.threading.private_threadpool_size=1;ds=ds.with_options(options).prefetch(1)
    history=[];start=time.perf_counter()
    class Development(tf.keras.callbacks.Callback):
        def on_epoch_end(self,epoch,logs=None):
            s=self.model.predict(X[dev],batch_size=128,verbose=0).reshape(-1);m=metrics(y[dev],s,hard[dev]);logs['val_pvc_f1']=m['f1']
            history.append(dict(epoch=epoch+1,loss=float(logs['loss']),development=m));save('history.json',history)
            print(f"Epoch {epoch+1} dev F1={m['f1']:.6f} P={m['precision']:.6f} R={m['recall']:.6f}",flush=True)
    callbacks=[Development(),tf.keras.callbacks.ModelCheckpoint(str(MODELS/'ecg_cnn_v2_best.keras'),monitor='val_pvc_f1',mode='max',save_best_only=True),tf.keras.callbacks.EarlyStopping(monitor='val_pvc_f1',mode='max',patience=5,restore_best_weights=True),tf.keras.callbacks.TerminateOnNaN()]
    model.fit(ds,epochs=30,callbacks=callbacks,verbose=2)
    model=tf.keras.models.load_model(MODELS/'ecg_cnn_v2_best.keras',compile=False)
    s=model.predict(X[dev],batch_size=128,verbose=0).reshape(-1);m=metrics(y[dev],s,hard[dev]);b=baseline['float32']
    improved=m['f1']>b['f1'] and m['precision']>=b['precision'] and m['recall']>=b['recall']-.02
    result=dict(tensorflow=tf.__version__,numpy=np.__version__,seed=42,best_epoch=int(np.argmax([r['development']['f1'] for r in history]))+1,epochs_run=len(history),seconds=time.perf_counter()-start,parameters=model.count_params(),class_weights=cw.tolist(),epoch_samples=len(epoch),hard_occurrences=int(sum(hard[epoch])),V1=baseline,V2={'float32':m},export_selected=bool(improved),selection_uses='original Train development only',export_rule=cfg['export_rule'])
    np.savez_compressed(OUT/'development_predictions.npz',indices=z['global_indices'][dev],y=y[dev],hard=hard[dev],v1_float=v1s,v2_float=s)
    save('training.json',result)
    if improved:
        for quant,name in [(False,'ecg_cnn_v2_float32.tflite'),(True,'ecg_cnn_v2_int8.tflite')]:
            conv=tf.lite.TFLiteConverter.from_keras_model(model)
            if quant:
                # Reuse original Train-only record/class/amplitude-stratified sampler on FIT only.
                spec=importlib.util.spec_from_file_location('conversion',ROOT/'python/07_convert_tinyml.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.np=np
                rep=mod.representative_indices(X,y,ids,fit)
                assert np.isin(rep,fit).all();np.save(OUT/'calibration_global_indices.npy',z['global_indices'][rep])
                conv.optimizations=[tf.lite.Optimize.DEFAULT];conv.representative_dataset=lambda:([X[k:k+1]] for k in rep)
                conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8];conv.inference_input_type=tf.int8;conv.inference_output_type=tf.int8
            else:conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS]
            (MODELS/name).write_bytes(conv.convert())
        fs=lite_scores(tf,MODELS/'ecg_cnn_v2_float32.tflite',X[dev]);qs,codes,clips,i,o=lite_scores(tf,MODELS/'ecg_cnn_v2_int8.tflite',X[dev],True)
        result['V2']['int8']=metrics(y[dev],qs,hard[dev]);result['V2']['tflite_float32']=metrics(y[dev],fs,hard[dev])
        result['quantization']=dict(float_lite_max_absolute_error=float(np.max(abs(fs-s))),float_int8_mean_absolute_error=float(np.mean(abs(qs-s))),class_changes=int(sum((qs>=.52)!=(s>=.52))),input_clipped_windows=int(sum(clips)),input_quantization=list(i['quantization']),output_quantization=list(o['quantization']),sizes={p.name:p.stat().st_size for p in MODELS.glob('*.tflite')})
        np.savez_compressed(OUT/'development_int8.npz',scores=qs,codes=codes,clipped=clips)
        save('training.json',result)
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
