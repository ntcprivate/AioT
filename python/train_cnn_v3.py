"""One central-QRS Tiny CNN configuration. Train-only development, no board IO."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
from pathlib import Path
import hashlib,importlib.util,json,time
import numpy as np
import tensorflow as tf
from cnn_v2_common import metrics,lite_scores
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/cnn_v2';OUT=ROOT/'results/cnn_v3';MODELS=ROOT/'models/v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')
def build_model():
    return tf.keras.Sequential([
        tf.keras.layers.Input((256,1)),
        tf.keras.layers.Cropping1D((96,96),name='central_qrs_64'),
        tf.keras.layers.Conv1D(8,5,activation='relu'),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(16,5,activation='relu'),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Flatten(),
        tf.keras.layers.Dense(8,activation='relu'),
        tf.keras.layers.Dense(1,activation='sigmoid'),
    ],name='ecg_center_v3')
def main():
    OUT.mkdir(exist_ok=True);MODELS.mkdir(exist_ok=True)
    if (OUT/'config.json').exists():raise RuntimeError('V3 already started; no second configuration or overwrite')
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.keras.utils.set_random_seed(42);tf.config.experimental.enable_op_determinism()
    z=np.load(BASE/'train_only.npz');X=z['X'];y=z['y'];hard=z['hard'];fit=z['fit'];dev=z['development'];ids=z['ids']
    prior=json.loads((BASE/'config.json').read_text());cached=np.load(BASE/'development_predictions.npz')
    np.testing.assert_array_equal(cached['indices'],z['global_indices'][dev]);np.testing.assert_array_equal(cached['y'],y[dev])
    group=lambda r:'patient_201_202' if r in ('201','202') else str(r)
    assert not {group(r) for r in ids[fit]}&{group(r) for r in ids[dev]}
    v1=metrics(y[dev],cached['v1_float'],hard[dev]);v2=metrics(y[dev],cached['v2_float'],hard[dev])
    counts=np.bincount(y[fit],minlength=2);cw=len(fit)/(2*counts)
    model=build_model();assert model.count_params()==2385
    protected=list((ROOT/'models').rglob('*'))+list((BASE).rglob('*'))+list((ROOT/'firmware/esp32_ecg_tinyml_integrated/main').rglob('*'))+list((ROOT/'tools/ecg_monitor/ecg_monitor').glob('*.py'))
    protected+=[ROOT/'data/processed/mitbih_split_indices.npz',ROOT/'data/processed/mitbih_nv_250hz.npz',ROOT/'results/optimized_threshold.json']
    save('protected_sha256.json',{str(p.relative_to(ROOT)):sha(p) for p in protected if p.is_file()})
    config=dict(seed=42,threshold=.52,epochs=30,patience=5,batch_size=64,optimizer='Adam .001',parameters=2385,input=[256,1],central_slice=[96,160],sampling='each fit sample exactly once per epoch; no hard-negative oversampling',class_weights=cw.tolist(),fit_records=prior['fit_records'],development_records=prior['development_records'],counts=prior['counts'],preprocessing='unchanged full-window per-beat z-score; central crop is inside model',monitor='max development PVC F1 at .52; patience5',int8_export_rule='V3 development F1 strictly exceeds both V1/V2 Float32@.52 and recall within2 percentage points of V1; not independent acceptance',limitations=['V1 fitted these development records. V2 and V3 exclude them from weight fitting.','Development reused for prior V2 stopping/threshold review and V3 stopping; not independent.','Known shared patient201/202 kept together; remaining patient groups are existing record proxies.'],source_sha256=sha(Path(__file__)),train_cache_sha256=sha(BASE/'train_only.npz'))
    save('config.json',config) # Freeze architecture/protocol before fit.
    model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy')
    ds=tf.data.Dataset.from_tensor_slices((X[fit],y[fit].astype(np.float32),cw[y[fit]].astype(np.float32))).shuffle(len(fit),seed=42,reshuffle_each_iteration=True).batch(64)
    options=tf.data.Options();options.threading.private_threadpool_size=1;ds=ds.with_options(options).prefetch(1)
    history=[];start=time.perf_counter()
    class Development(tf.keras.callbacks.Callback):
        def on_epoch_end(self,epoch,logs=None):
            s=self.model.predict(X[dev],batch_size=128,verbose=0).reshape(-1);m=metrics(y[dev],s,hard[dev]);logs['val_pvc_f1']=m['f1']
            history.append(dict(epoch=epoch+1,loss=float(logs['loss']),development=m));save('history.json',history)
            print(f"Epoch {epoch+1} dev F1={m['f1']:.6f} P={m['precision']:.6f} R={m['recall']:.6f} hardFP={m['normal_neighbor_pvc']['false_positive']}",flush=True)
    model.fit(ds,epochs=30,verbose=2,callbacks=[Development(),tf.keras.callbacks.ModelCheckpoint(str(MODELS/'ecg_cnn_v3_best.keras'),monitor='val_pvc_f1',mode='max',save_best_only=True),tf.keras.callbacks.EarlyStopping(monitor='val_pvc_f1',mode='max',patience=5,restore_best_weights=True),tf.keras.callbacks.TerminateOnNaN()])
    model=tf.keras.models.load_model(MODELS/'ecg_cnn_v3_best.keras',compile=False)
    scores=model.predict(X[dev],batch_size=128,verbose=0).reshape(-1);m=metrics(y[dev],scores,hard[dev])
    improved=m['f1']>max(v1['f1'],v2['f1']) and m['recall']>=v1['recall']-.02
    np.savez_compressed(OUT/'development_predictions.npz',indices=z['global_indices'][dev],y=y[dev],hard=hard[dev],scores=scores)
    result=dict(parameters=model.count_params(),best_epoch=int(np.argmax([r['development']['f1'] for r in history]))+1,epochs_run=len(history),seconds=time.perf_counter()-start,epoch_samples=len(fit),hard_occurrences=int(sum(hard[fit])),V1_float32=v1,V2_float32=v2,V3_float32=m,int8_export_selected=bool(improved),tensorflow=tf.__version__,numpy=np.__version__)
    save('training.json',result)
    conv=tf.lite.TFLiteConverter.from_keras_model(model);conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS]
    (MODELS/'ecg_cnn_v3_float32.tflite').write_bytes(conv.convert())
    fs=lite_scores(tf,MODELS/'ecg_cnn_v3_float32.tflite',X[dev]);result['float_tflite_max_score_error']=float(np.max(abs(fs-scores)))
    assert np.max(abs(fs-scores))<1e-4
    if improved:
        spec=importlib.util.spec_from_file_location('conversion',ROOT/'python/07_convert_tinyml.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.np=np
        rep=mod.representative_indices(X,y,ids,fit);assert np.isin(rep,fit).all()
        np.save(OUT/'calibration_global_indices.npy',z['global_indices'][rep])
        conv=tf.lite.TFLiteConverter.from_keras_model(model);conv.optimizations=[tf.lite.Optimize.DEFAULT]
        conv.representative_dataset=lambda:([X[k:k+1]] for k in rep);conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        conv.inference_input_type=tf.int8;conv.inference_output_type=tf.int8
        (MODELS/'ecg_cnn_v3_int8.tflite').write_bytes(conv.convert())
        qs,codes,clipped,i,o=lite_scores(tf,MODELS/'ecg_cnn_v3_int8.tflite',X[dev],True)
        result['V3_int8']=metrics(y[dev],qs,hard[dev]);result['quantization']=dict(input_quantization=list(i['quantization']),output_quantization=list(o['quantization']),score_mae=float(np.mean(abs(qs-scores))),class_changes=int(sum((qs>=.52)!=(scores>=.52))),input_clipped_windows=int(sum(clipped)))
        np.savez_compressed(OUT/'development_int8.npz',scores=qs,codes=codes,clipped=clipped)
    result['model_files']={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in MODELS.iterdir() if p.is_file()}
    assert all(sha(ROOT/p)==digest for p,digest in json.loads((OUT/'protected_sha256.json').read_text()).items())
    save('training.json',result);print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
