import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,random,subprocess
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
from run_v11_rr import load,build,Sequence,rr_at,BEATS
from run_v10_step0_step1 import CheckpointAPSelector,select_threshold_on_cal_fold,compute_metrics,sha256_file
from evaluate_v11_e2e import score as count_metrics
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/final_test';MODEL=ROOT/'models/v11/v11_final_best.keras'
def write(p,v):p.write_text(json.dumps(v,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else x))
def train():
    lock=OUT/'locked.json'
    if lock.exists():
        saved=json.loads(lock.read_text());assert saved['sha256']==sha256_file(MODEL);return saved
    if MODEL.exists():raise RuntimeError('Unfinished final training: best checkpoint is not full resume state')
    x,y,rr,g,d=load()
    partition=json.loads((ROOT/'results/cnn_v6/config.json').read_text())['development_partition']
    cp=((d=='MITBIH')&np.isin(g,partition['MITBIH_checkpoint_records']))|((d=='INCART')&np.isin(g,partition['INCART_checkpoint_patients']))
    cal=((d=='MITBIH')&np.isin(g,partition['MITBIH_threshold_records']))|((d=='INCART')&np.isin(g,partition['INCART_threshold_patients']))
    fit=~(cp|cal);assert not np.any(cp&cal)
    mean=rr[fit].mean(0);std=np.maximum(rr[fit].std(0),1e-8);r=(rr-mean)/std
    random.seed(42);np.random.seed(42);tf.keras.utils.set_random_seed(42)
    model=build();assert model.count_params()==2017
    model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy')
    inp=lambda m:{'ecg_256':x[m],'rr_features':r[m]}
    selector=CheckpointAPSelector(inp(cp),y[cp],MODEL);counts=np.bincount(y[fit],minlength=2);w=len(y[fit])/(2*counts)
    model.fit(Sequence(x[fit],r[fit],y[fit],w,42),epochs=20,verbose=0,callbacks=[selector,tf.keras.callbacks.TerminateOnNaN()])
    model=tf.keras.models.load_model(MODEL,compile=False);scores=model.predict(inp(cal),batch_size=512,verbose=0).ravel();t=select_threshold_on_cal_fold(y[cal],scores)
    saved={'sha256':sha256_file(MODEL),'threshold':t['threshold'],'rr_fit_mean':mean.tolist(),'rr_fit_std':std.tolist(),'best_epoch':selector.best_epoch,'epochs_run':len(selector.history),'parameters':2017,'seed':42,'partition':partition,'fit_groups':{ds:sorted(set(g[fit&(d==ds)])) for ds in ['MITBIH','INCART']},'loss':'binary_crossentropy','class_weight':w.tolist(),'augmentation':False,'preprocessing':'250Hz,256 samples,per-window z-score','RR_features':['current RR','median preceding up to7 RR','ratio current/prior median','history fraction up to8'],'missing_history':[1,1,1,0],'tensorflow':tf.__version__,'onednn':'0','test_accessed_before_lock':False,'retrospective_test':True}
    write(lock,saved);return saved

def test(saved):
    model=tf.keras.models.load_model(MODEL,compile=False);mean=np.asarray(saved['rr_fit_mean']);std=np.asarray(saved['rr_fit_std']);threshold=saved['threshold']
    # Test arrays/record IDs are first accessed after lock exists above.
    mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');sp=np.load(ROOT/'data/processed/mitbih_split_indices.npz');inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
    rows=[]
    for ds,data,ix in [('MITBIH',mit,sp['test_indices']),('INCART',inc,np.flatnonzero(inc['split']=='test'))]:
      for rec in sorted(set(data['record_ids'][ix].astype(str))):
        cache=OUT/f'{ds}_{rec}.json'
        if cache.exists():rows.append(json.loads(cache.read_text()));continue
        marker=OUT/f'{ds}_{rec}.started'
        if marker.exists():raise RuntimeError(f'Partial inference needs recovery, refusing repeat: {marker}')
        marker.touch()
        idx=ix[data['record_ids'][ix]==rec];base=ROOT/('mit-bih-arrhythmia-database-1.0.0' if ds=='MITBIH' else 'files')/rec
        h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');names=[n.strip().upper() for n in h.sig_name];channel=names.index('MLII' if ds=='MITBIH' else 'II')
        signal=wfdb.rdrecord(str(base),channels=[channel],**({'return_res':32} if ds=='INCART' else {})).p_signal[:,0]
        signal=resample_poly(signal,25 if ds=='MITBIH' else 250,36 if ds=='MITBIH' else 257)
        if ds=='INCART':signal=signal.astype(np.float32)
        times=np.array([s/h.fs for s,c in zip(ann.sample,ann.symbol) if c in BEATS]);features=[];labels=[];centers=[]
        for s,c in zip(ann.sample,ann.symbol):
            center=int(np.floor(s*250/h.fs+.5))
            if c not in {'N','V'} or center<128 or center+128>len(signal):continue
            wave=signal[center-128:center+128].astype(np.float64)
            if not np.isfinite(wave).all() or (ds=='INCART' and wave.std()<=1e-8):continue
            features.append(rr_at(times,s/h.fs));labels.append(int(c=='V'));centers.append(center)
        assert np.array_equal(data['y'][idx],labels),rec
        if ds=='INCART':assert np.array_equal(data['centers_250hz'][idx],centers)
        refscore=model.predict({'ecg_256':data['X'][idx],'rr_features':(np.asarray(features)-mean)/std},batch_size=512,verbose=0).ravel()
        np.savez_compressed(OUT/f'{ds}_{rec}_offline.npz',y=labels,scores=refscore)
        raw=np.clip(np.rint(2048+200*signal),0,4095).astype('<i2');raw.tofile(OUT/'input.bin')
        log=OUT/f'{ds}_{rec}_detector.csv';windows=OUT/'windows.bin'
        exe=ROOT/'results/cnn_v11/rr_detector_validation/detector.exe'
        with log.open('w') as f:subprocess.run([str(exe),str(OUT/'input.bin'),str(windows),str(OUT/'safe.bin')],stdout=f,check=True)
        events=[s.split(',') for s in log.read_text().splitlines()];peaks=np.array([int(e[1]) for e in events if e[0]=='peak'])
        x=np.fromfile(windows,dtype=np.float32).reshape(-1,256,1);x=(x-x.mean(1,keepdims=True))/np.maximum(x.std(1,keepdims=True),1e-8)
        rr=np.asarray([rr_at(peaks[:j+1]/250.,peaks[j]/250.) for j in range(len(peaks))]);scores=model.predict({'ecg_256':x,'rr_features':(rr-mean)/std},batch_size=512,verbose=0).ravel();pred=scores>=threshold
        np.savez_compressed(OUT/f'{ds}_{rec}_detector.npz',peaks=peaks,scores=scores)
        refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS];used=set();tp=fp=fn=tn=missn=missv=0
        for t,c in refs:
            cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
            if not cand:
                missn+=int(c=='N');missv+=int(c=='V');fn+=int(c=='V');continue
            j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j)
            if c not in {'N','V'}:continue
            tp+=int(c=='V' and pred[j]);fp+=int(c=='N' and pred[j]);fn+=int(c=='V' and not pred[j]);tn+=int(c=='N' and not pred[j])
        fp+=sum(int(pred[j]) for j in range(len(peaks)) if j not in used)
        row={'dataset':ds,'record':rec,'offline':compute_metrics(np.asarray(labels),refscore,threshold),'detector':count_metrics(tp,fp,fn,tn,sum(c=='N' for t,c in refs)),'missing_N':missn,'missing_V':missv,'extra_peaks':len(peaks)-len(used)}
        write(cache,row);rows.append(row);print(ds,rec,'complete',flush=True)
    result={'locked':saved,'records':rows,'summary':{}}
    for ds in ['MITBIH','INCART']:
        result['summary'][ds]={}
        for mode in ['offline','detector']:
            vals=[r[mode] for r in rows if r['dataset']==ds];counts={k:sum(int(v[k]) for v in vals) for k in ['TP','FP','FN','TN']};m=count_metrics(counts['TP'],counts['FP'],counts['FN'],counts['TN'],sum(r['offline']['TN']+r['offline']['FP'] for r in rows if r['dataset']==ds));m['accuracy']=(m['TP']+m['TN'])/sum(counts.values());result['summary'][ds][mode]=m
    write(OUT/'evaluation.json',result);print(json.dumps(result['summary'],indent=2))

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'evaluation.json').exists():raise RuntimeError('Test completed; no rerun')
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.experimental.enable_op_determinism()
    test(train())
