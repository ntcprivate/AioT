import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json, random, math, hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
from run_v10_step0_step1 import build_v6_baseline, CheckpointAPSelector, compute_metrics, select_threshold_on_cal_fold, summarize_across_folds, sha256_file

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/cnn_v11'; MODELS=ROOT/'models/v11'
BEATS=set('NLRBAaJSVrFejnE/fQ?')

def rr_at(times, t):
    # Current and preceding intervals only. Annotation symbols never enter features.
    k=np.searchsorted(times,t)
    assert k<len(times) and abs(times[k]-t)<1e-6
    history=np.diff(times[max(0,k-8):k+1])
    current=history[-1] if len(history) else 1.0
    previous=history[:-1]
    median=float(np.median(previous)) if len(previous) else 1.0
    return [current,median,current/max(median,1e-8),min(len(history),8)/8]

def load():
    mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz')
    split=np.load(ROOT/'data/processed/mitbih_split_indices.npz')
    inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
    ids=np.concatenate([split['train_indices'],split['validation_indices']])
    keep=np.isin(inc['split'],['train','validation'])
    xs=[];ys=[];gs=[];ds=[];rs=[]
    for dataset,data,indices in [('MITBIH',mit,ids),('INCART',inc,np.flatnonzero(keep))]:
        records=data['record_ids'][indices].astype(str)
        for record in sorted(set(records)):
            ix=indices[records==record]
            base=ROOT/('mit-bih-arrhythmia-database-1.0.0' if dataset=='MITBIH' else 'files')/record
            h=wfdb.rdheader(str(base)); ann=wfdb.rdann(str(base),'atr')
            times=np.asarray([s/h.fs for s,c in zip(ann.sample,ann.symbol) if c in BEATS])
            if dataset=='INCART':
                centers=data['centers_250hz'][ix]
                mapping={int(np.floor(s*250/h.fs+0.5)):s/h.fs for s,c in zip(ann.sample,ann.symbol) if c in {'N','V'}}
                features=[rr_at(times,mapping[int(c)]) for c in centers]
            else:
                # MIT artifact has no centers: reconstruct extraction order and
                # verify every retained waveform before assigning RR metadata.
                leads=[s.upper().strip() for s in h.sig_name]
                sig=wfdb.rdrecord(str(base),channels=[leads.index('MLII')]).p_signal[:,0]
                sig=resample_poly(sig,25,36)
                features=[]; labels=[]; waves=[]
                for s,c in zip(ann.sample,ann.symbol):
                    center=(int(s)*25+18)//36
                    if c not in {'N','V'} or center<128 or center+128>len(sig): continue
                    wave=sig[center-128:center+128].astype(np.float64)
                    if not np.isfinite(wave).all(): continue
                    wave=((wave-wave.mean())/max(wave.std(),1e-8)).astype(np.float32)
                    waves.append(wave);labels.append(int(c=='V'));features.append(rr_at(times,s/h.fs))
                assert np.array_equal(data['y'][ix],labels),f'label alignment {record}'
                assert np.allclose(data['X'][ix,:,0],np.asarray(waves),atol=1e-5),f'wave alignment {record}'
            xs.append(data['X'][ix]);ys.append(data['y'][ix]);rs.append(np.asarray(features,dtype=np.float32))
            group=record if dataset=='MITBIH' else str(data['patient_ids'][ix[0]])
            gs.extend([group]*len(ix));ds.extend([dataset]*len(ix))
    return np.concatenate(xs),np.concatenate(ys),np.concatenate(rs),np.asarray(gs),np.asarray(ds)

class Sequence(tf.keras.utils.Sequence):
    def __init__(self,x,r,y,w,seed):
        super().__init__();self.x=x;self.r=r;self.y=y;self.w=w;self.seed=seed;self.epoch=0;self.on_epoch_end()
    def __len__(self):return math.ceil(len(self.y)/128)
    def on_epoch_end(self):
        self.epoch+=1;self.order=np.random.default_rng(self.seed+self.epoch).permutation(len(self.y))
    def __getitem__(self,k):
        i=self.order[k*128:(k+1)*128]
        return {'ecg_256':self.x[i],'rr_features':self.r[i]},self.y[i],self.w[self.y[i]]

def build():
    base=build_v6_baseline()
    rr=tf.keras.layers.Input((4,),name='rr_features')
    r=tf.keras.layers.Dense(8,activation='relu',name='rr_dense')(rr)
    z=tf.keras.layers.Concatenate()([base.get_layer('fusion_dense').output,r])
    out=tf.keras.layers.Dense(1,activation='sigmoid')(z)
    return tf.keras.Model([base.input,rr],out)

def main():
    OUT.mkdir(exist_ok=True,parents=True);MODELS.mkdir(exist_ok=True,parents=True)
    tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.experimental.enable_op_determinism()
    folds=json.loads((ROOT/'results/v10_research/step1_5fold_cv/folds_split.json').read_text())
    config={'seed':42,'features':['current_RR_seconds','median_previous_up_to_7_RR','current_over_previous_median','history_fraction_up_to_8'], 'missing_history':'1 second; prior median 1 second; explicit history fraction','rr_scaling':'Fit mean/std, epsilon 1e-8; no clipping','annotation_symbols':'beat-position filtering only; no class labels used as features','epochs':20,'patience':5,'batch':128,'augmentation':False,'onednn':'0','tensorflow':tf.__version__,'adaptive_limit':'Architecture motivated by previously viewed outer results; not independent confirmation','splits_sha256':sha256_file(ROOT/'results/v10_research/step1_5fold_cv/folds_split.json')}
    (OUT/'config.json').write_text(json.dumps(config,indent=2))
    x,y,rr,g,d=load();rows=[]
    assert np.isfinite(rr).all()
    for spec in folds:
        k=spec['fold_index'];cache=OUT/f'fold{k}.json';path=MODELS/f'v11_fold{k}_best.keras'
        if cache.exists():
            row=json.loads(cache.read_text());assert row['checkpoint_sha256']==sha256_file(path);rows.append(row);continue
        masks={}
        for role in ['fit','checkpoint','threshold','outer']:
            masks[role]=((d=='MITBIH')&np.isin(g,spec[f'{role}_MITBIH_records']))|((d=='INCART')&np.isin(g,spec[f'{role}_INCART_patients']))
        roles=list(masks)
        assert all(not np.any(masks[a]&masks[b]) for i,a in enumerate(roles) for b in roles[i+1:])
        mean=rr[masks['fit']].mean(0);std=np.maximum(rr[masks['fit']].std(0),1e-8);r=(rr-mean)/std
        seed=42+k*1000;tf.keras.backend.clear_session();random.seed(seed);np.random.seed(seed);tf.keras.utils.set_random_seed(seed)
        model=build();model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy')
        inp=lambda mask:{'ecg_256':x[mask],'rr_features':r[mask]}
        cp=masks['checkpoint'];fit=masks['fit'];th=masks['threshold']
        selector=CheckpointAPSelector(inp(cp),y[cp],path)
        counts=np.bincount(y[fit],minlength=2);w=len(y[fit])/(2*counts)
        model.fit(Sequence(x[fit],r[fit],y[fit],w,seed),epochs=20,verbose=0,callbacks=[selector,tf.keras.callbacks.TerminateOnNaN()])
        model=tf.keras.models.load_model(path,compile=False)
        score=model.predict(inp(th),batch_size=512,verbose=0).ravel();t=select_threshold_on_cal_fold(y[th],score)['threshold']
        row={'fold_index':k,'seed':seed,'parameters':model.count_params(),'best_epoch':selector.best_epoch,'epochs_run':len(selector.history),'threshold':t,'rr_fit_mean':mean.tolist(),'rr_fit_std':std.tolist(),'checkpoint_sha256':sha256_file(path),'robustness':{}}
        for dataset in ['MITBIH','INCART']:
            m=masks['outer']&(d==dataset);scores=model.predict(inp(m),batch_size=512,verbose=0).ravel();row[dataset]=compute_metrics(y[m],scores,t)
            # Fixed perturbations, evaluation only: missing history and timing jitter.
            row['robustness'][dataset]={}
            for kind in ['missing','jitter']:
                pert=rr[m].copy()
                if kind=='missing':pert[:]=[1,1,1,0]
                else:
                    rng=np.random.default_rng(seed);pert[:,0]=np.maximum(.01,pert[:,0]+rng.normal(0,.04,len(pert)));pert[:,2]=pert[:,0]/np.maximum(pert[:,1],1e-8)
                scores=model.predict({'ecg_256':x[m],'rr_features':(pert-mean)/std},batch_size=512,verbose=0).ravel()
                row['robustness'][dataset][kind]=compute_metrics(y[m],scores,t)
        cache.write_text(json.dumps(row,indent=2));rows.append(row);print(f'V11 fold {k} complete, params={model.count_params()}',flush=True)
    result={'config':config,'folds':rows,'summary':{ds:summarize_across_folds(rows,ds) for ds in ['MITBIH','INCART']}}
    (OUT/'evaluation.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':main()
