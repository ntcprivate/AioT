import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,hashlib,math
from pathlib import Path
import numpy as np
import tensorflow as tf
from run_v10_step0_step1 import compute_metrics
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/int8_conversion'
SOURCE=ROOT/'models/v11/v11_final_best.keras';EXPECTED='61909ec7f93e3d8823627a0127422aefdd098f92a9c95619073968c7a3eb3601'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else x))
def data():
    # Reuse the RR alignment already verified during V11 evaluation; same
    # dataset -> sorted record -> original per-record row order as run_v11_rr.load.
    m=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');s=np.load(ROOT/'data/processed/mitbih_split_indices.npz');i=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
    xs=[];ys=[];gs=[];ds=[];records=[];splits=[];indices=[]
    for name,z,train,dev in [('MITBIH',m,s['train_indices'],s['validation_indices']),('INCART',i,np.flatnonzero(i['split']=='train'),np.flatnonzero(i['split']=='validation'))]:
        allx=z['X'];ally=z['y'];allrec=z['record_ids'];allpatient=z['patient_ids'] if name=='INCART' else None
        idx=np.concatenate([train,dev]) if name=='MITBIH' else np.flatnonzero(np.isin(i['split'],['train','validation']))
        istrain=set(map(int,train))
        for rec in sorted(set(allrec[idx].astype(str))):
            ix=idx[allrec[idx]==rec];xs.append(allx[ix]);ys.append(ally[ix]);records.extend([rec]*len(ix));ds.extend([name]*len(ix));gs.extend([rec if name=='MITBIH' else str(allpatient[ix[0]])]*len(ix));splits.extend(['train' if int(j) in istrain else 'development' for j in ix]);indices.extend(map(int,ix))
    rr=np.load(ROOT/'results/cnn_v11/rr_detector_validation/rr_features.npz')['annotation']
    x=np.concatenate(xs);y=np.concatenate(ys);assert rr.shape==(len(y),4) and np.isfinite(rr).all() and np.isfinite(x).all()
    return x,y,rr,np.array(ds),np.array(gs),np.array(records),np.array(splits),np.array(indices)
def main():
    OUT.mkdir(exist_ok=True,parents=True)
    if (OUT/'conversion.json').exists() or (OUT/'ecg_cnn_v11_int8.tflite').exists():raise RuntimeError('Artifacts exist; refusing overwrite')
    assert sha(SOURCE)==EXPECTED
    lock=json.loads((ROOT/'results/cnn_v11/final_test/locked.json').read_text());assert lock['threshold']==.8
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    model=tf.keras.models.load_model(SOURCE,compile=False);assert model.count_params()==2017
    print('inputs',[(t.name,t.shape) for t in model.inputs],flush=True)
    x,y,rr,ds,groups,records,splits,sourceidx=data();mean=np.asarray(lock['rr_fit_mean'],np.float32);std=np.asarray(lock['rr_fit_std'],np.float32);r=(rr-mean)/std
    train=splits=='train';dev=splits=='development'
    assert np.allclose(rr[train].mean(0),mean,rtol=1e-5,atol=1e-6)
    rng=np.random.default_rng(42);chosen=[]
    for name in ['MITBIH','INCART']:
        for label in [0,1]:
            at=np.flatnonzero(train&(ds==name)&(y==label));chosen.extend(rng.choice(at,min(256,len(at)),replace=False).tolist())
    # Include real Train startup/history cases, not fabricated RR vectors.
    chosen=np.unique(chosen+np.flatnonzero(train&(rr[:,3]<1)).tolist())
    assert np.all(train[chosen]);assert set(model.input_names if hasattr(model,'input_names') else [t.name.split(':')[0] for t in model.inputs])=={'ecg_256','rr_features'}
    def representative():
        for j in chosen:
            yield {'ecg_256':x[j:j+1].astype(np.float32),'rr_features':r[j:j+1].astype(np.float32)}
    converter=tf.lite.TFLiteConverter.from_keras_model(model);converter.optimizations=[tf.lite.Optimize.DEFAULT];converter.representative_dataset=representative;converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8];converter.inference_input_type=tf.int8;converter.inference_output_type=tf.int8
    path=OUT/'ecg_cnn_v11_int8.tflite';path.write_bytes(converter.convert())
    lite=tf.lite.Interpreter(model_path=str(path),num_threads=1,experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES);lite.allocate_tensors();inputs=lite.get_input_details();output=lite.get_output_details()[0]
    assert len(inputs)==2 and all(t['dtype']==np.int8 and t['quantization'][0]>0 for t in inputs) and output['dtype']==np.int8
    ecg=next(t for t in inputs if tuple(t['shape'])==(1,256,1));rrin=next(t for t in inputs if tuple(t['shape'])==(1,4));scale,zero=output['quantization']
    # Exact decision: smallest representable q whose dequantized value >=0.80.
    codes=np.arange(-128,128);eligible=codes[(codes-zero)*scale>=.8];threshold_code=int(eligible[0]) if len(eligible) else 128
    def quant(a,t):
        s,z=t['quantization'];v=np.rint(a.astype(np.float64)/s)+z;return np.clip(v,-128,127).astype(np.int8),int(np.sum((v<-128)|(v>127)))
    idx=np.flatnonzero(dev);fp=model.predict({'ecg_256':x[idx],'rr_features':r[idx]},batch_size=512,verbose=0).ravel();qc=[];qe=[];qr=[];clipe=clipr=0
    for j in idx:
        a,ce=quant(x[j:j+1],ecg);b,cr=quant(r[j:j+1],rrin);clipe+=ce;clipr+=cr;lite.set_tensor(ecg['index'],a);lite.set_tensor(rrin['index'],b);lite.invoke();qc.append(int(lite.get_tensor(output['index']).ravel()[0]));qe.append(a[0]);qr.append(b[0])
    qc=np.array(qc,np.int8);scores=(qc.astype(np.float64)-zero)*scale;assert np.array_equal(scores>=.8,qc.astype(int)>=threshold_code)
    np.savez_compressed(OUT/'development_predictions.npz',indices=idx,dataset=ds[idx],record=records[idx],source_indices=sourceidx[idx],y=y[idx],fp32=fp,int8_codes=qc,int8_scores=scores)
    result={'source_sha256':EXPECTED,'int8_sha256':sha(path),'model_bytes':path.stat().st_size,'parameters':2017,'runtime':{'tensorflow':tf.__version__,'onednn':'0','host_reference':'TFLite CPU without default delegates; TFLM/ESP32 parity not yet measured'},'calibration':{'samples':len(chosen),'seed':42,'source':'Train only, stratified dataset/class plus real missing-history Train samples','source_rr_sha256':sha(ROOT/'results/cnn_v11/rr_detector_validation/rr_features.npz')},'inputs':[],'output':{'name':output['name'],'index':output['index'],'scale':scale,'zero_point':zero},'threshold':{'fp32':.8,'int8_code_min':threshold_code,'rule':'code >= int8_code_min; no tuning','first_positive_probability':(threshold_code-zero)*scale},'rr_fit_mean':mean.tolist(),'rr_fit_std':std.tolist(),'development':{},'golden_status':'TFLite-host reference; exact TFLM/ESP32 parity pending'}
    for t in inputs:result['inputs'].append({'name':t['name'],'index':t['index'],'shape':t['shape'].tolist(),'dtype':str(t['dtype']),'scale':t['quantization'][0],'zero_point':t['quantization'][1]})
    for name in ['MITBIH','INCART']:
        mask=ds[idx]==name;delta=abs(fp[mask]-scores[mask]);result['development'][name]={'samples':int(mask.sum()),'FP32':compute_metrics(y[idx][mask],fp[mask],.8),'INT8':compute_metrics(y[idx][mask],scores[mask],.8),'prediction_changes':int(sum((fp[mask]>=.8)!=(scores[mask]>=.8))),'score_mae':float(delta.mean()),'score_max_abs':float(delta.max()),'score_p99_abs':float(np.percentile(delta,99))}
    ops=lite._get_ops_details();result['operators']=[o['op_name'] for o in ops];tensors=lite.get_tensor_details();assert all(t['dtype'] not in [np.float32,np.float64,np.float16] for t in tensors)
    result['memory']={'tensor_arena_bytes':None,'arena_status':'NOT MEASURED; tensor sizes are not allocator usage','sum_tensor_shape_bytes_including_constants_and_aliases':sum(int(np.prod(t['shape']))*np.dtype(t['dtype']).itemsize for t in tensors),'largest_tensor_bytes':max(int(np.prod(t['shape']))*np.dtype(t['dtype']).itemsize for t in tensors)}
    result['input_clipping_development']={'ECG_values':clipe,'RR_values':clipr}
    selected=[]
    for name in ['MITBIH','INCART']:
        for label in [0,1]:
            at=np.flatnonzero((ds[idx]==name)&(y[idx]==label));selected.extend(at[:2]);selected.extend(at[np.argsort(abs(scores[at]-.8))[:2]])
    selected=np.unique(selected);rows=[];goldidx=idx[selected]
    np.savez_compressed(OUT/'golden_fixtures.npz',ecg=x[goldidx],rr_raw=rr[goldidx],rr_normalized=r[goldidx],ecg_int8=np.asarray(qe)[selected],rr_int8=np.asarray(qr)[selected],output_int8=qc[selected],probability=scores[selected],prediction=(scores[selected]>=.8).astype(np.int32),true_label=y[goldidx],dataset=ds[goldidx],record=records[goldidx],source_indices=sourceidx[goldidx])
    np.asarray(qe,dtype=np.int8)[selected].tofile(OUT/'golden_ecg_int8.bin');np.asarray(qr,dtype=np.int8)[selected].tofile(OUT/'golden_rr_int8.bin');qc[selected].tofile(OUT/'golden_output_int8.bin')
    for i,j in enumerate(selected):rows.append({'fixture':i,'dataset':str(ds[idx[j]]),'record':str(records[idx[j]]),'source_index':int(sourceidx[idx[j]]),'label':int(y[idx[j]]),'ecg':x[idx[j]].ravel().tolist(),'rr_raw':rr[idx[j]].tolist(),'rr_normalized':r[idx[j]].tolist(),'ecg_int8':np.asarray(qe)[j].ravel().tolist(),'rr_int8':np.asarray(qr)[j].tolist(),'output_int8':int(qc[j]),'probability':float(scores[j]),'prediction':int(scores[j]>=.8)})
    write(OUT/'golden_fixtures.json',{'model_sha256':sha(path),'quantization_rounding':'round nearest ties to even, then saturate [-128,127]','fixtures':rows});write(OUT/'calibration_manifest.json',[{'dataset':str(ds[j]),'record':str(records[j]),'source_index':int(sourceidx[j]),'split':str(splits[j]),'label':int(y[j])} for j in chosen]);write(OUT/'conversion.json',result)
    print(json.dumps({k:result[k] for k in ['model_bytes','operators','inputs','output','threshold','development','memory','input_clipping_development']},indent=2))
if __name__=='__main__':main()
