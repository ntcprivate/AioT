import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json, subprocess, hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
from run_v11_rr import load, rr_at, BEATS
from run_v10_step0_step1 import compute_metrics, summarize_across_folds

ROOT=Path(__file__).resolve().parents[1]; FW=ROOT/'firmware/esp32_ecg_tinyml_integrated'
OUT=ROOT/'results/cnn_v11/rr_detector_validation'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'evaluation.json').exists():raise RuntimeError('Completed evaluation exists')
    exe=OUT/'detector.exe'
    subprocess.run(['g++','-std=c++17','-O2','-I',str(FW/'main'),'-I',str(FW/'tests'),str(FW/'main/signal.cpp'),str(FW/'tests/detector_phase2b_replay.cpp'),'-o',str(exe)],check=True)
    x,y,oracle,g,d=load();features=[];record_rows=[]
    folds=json.loads((ROOT/'results/v10_research/step1_5fold_cv/folds_split.json').read_text())
    inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');spl=np.load(ROOT/'data/processed/mitbih_split_indices.npz')
    for ds in ['MITBIH','INCART']:
        data=mit if ds=='MITBIH' else inc
        ix=np.concatenate([spl['train_indices'],spl['validation_indices']]) if ds=='MITBIH' else np.flatnonzero(np.isin(inc['split'],['train','validation']))
        for rec in sorted(set(data['record_ids'][ix].astype(str))):
            base=ROOT/('mit-bih-arrhythmia-database-1.0.0' if ds=='MITBIH' else 'files')/rec
            h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');ch=[s.strip().upper() for s in h.sig_name].index('MLII' if ds=='MITBIH' else 'II')
            sig=wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0]
            sig=resample_poly(sig,25 if ds=='MITBIH' else 250,36 if ds=='MITBIH' else 257)
            raw=np.clip(np.rint(2048+200*sig),0,4095).astype('<i2');raw.tofile(OUT/'input.bin')
            log=OUT/f'{ds}_{rec}.csv'
            with log.open('w') as f:subprocess.run([str(exe),str(OUT/'input.bin'),str(OUT/'windows.bin'),str(OUT/'safe.bin')],stdout=f,check=True)
            events=[line.strip().split(',') for line in log.read_text().splitlines()]
            peaks=np.asarray([int(v[1]) for v in events if v[0]=='peak'],dtype=np.int64)
            emitted=np.asarray([int(v[2]) for v in events if v[0]=='peak'],dtype=np.int64)
            refs=np.asarray([int(np.floor(s*250/h.fs+.5)) for s,c in zip(ann.sample,ann.symbol) if c in BEATS])
            used=set();matches={};errors=[]
            for i,t in enumerate(refs):
                candidates=np.flatnonzero((abs(peaks-t)<=38)&(emitted<=t+128))
                candidates=[int(j) for j in candidates if int(j) not in used]
                if candidates:
                    j=min(candidates,key=lambda j:abs(peaks[j]-t));used.add(j);matches[int(t)]=j;errors.append(int(peaks[j]-t))
            if ds=='INCART':
                positions=inc['centers_250hz'][ix[inc['record_ids'][ix]==rec]]
            else:
                positions=np.asarray([int((int(s)*25+18)//36) for s,c in zip(ann.sample,ann.symbol) if c in {'N','V'} and (int(s)*25+18)//36>=128 and (int(s)*25+18)//36+128<=len(sig)])
            rr_errors=[];missing=0
            for t in positions:
                j=matches.get(int(t))
                if j is None:features.append([1,1,1,0]);missing+=1;continue
                # Only preceding detector peaks; never a subsequent peak or label.
                times=peaks[:j+1]/250.
                f=rr_at(times,times[-1]);features.append(f)
                ref_times=refs/250.;a=rr_at(ref_times,t/250.)
                rr_errors.append(float(f[0]-a[0]))
            record_rows.append({'dataset':ds,'record':rec,'reference_beats':len(refs),'TP':len(matches),'FP':len(peaks)-len(matches),'FN':len(refs)-len(matches),'nv_beats':len(positions),'missing':missing,'rr_error_seconds':rr_errors,'peak_errors_samples':errors})
            print(ds,rec,'completed',flush=True)
    features=np.asarray(features,dtype=np.float32);assert features.shape==oracle.shape
    np.savez_compressed(OUT/'rr_features.npz',detector=features,annotation=oracle)
    prior=json.loads((ROOT/'results/cnn_v11/evaluation.json').read_text());rows=[]
    for spec in folds:
        k=spec['fold_index'];saved=prior['folds'][k];path=ROOT/f'models/v11/v11_fold{k}_best.keras'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==saved['checkpoint_sha256']
        model=tf.keras.models.load_model(path,compile=False);mean=np.asarray(saved['rr_fit_mean']);std=np.asarray(saved['rr_fit_std']);row={'fold_index':k}
        for ds in ['MITBIH','INCART']:
            groups=spec['outer_MITBIH_records' if ds=='MITBIH' else 'outer_INCART_patients'];m=(d==ds)&np.isin(g,groups)
            scores=model.predict({'ecg_256':x[m],'rr_features':(features[m]-mean)/std},batch_size=512,verbose=0).ravel();row[ds]=compute_metrics(y[m],scores,saved['threshold'])
        rows.append(row)
    result={'scope':'RR-only substitution on fixed annotation-centered ECG windows; not detector end-to-end. All Train+Development records evaluated only by their outer model. Synthetic ADC mapping 2048+200 counts/mV; no hardware calibration. Matching 38 samples, completion available by center+128. Missing current peak uses fixed missing-history features.','records':record_rows,'folds':rows,'summary':{ds:summarize_across_folds(rows,ds) for ds in ['MITBIH','INCART']}}
    (OUT/'evaluation.json').write_text(json.dumps(result,indent=2))
    for ds in ['MITBIH','INCART']:
        s=result['summary'][ds];r=[v for v in record_rows if v['dataset']==ds];err=np.concatenate([v['rr_error_seconds'] for v in r]);print(ds,json.dumps({'f1':s['f1']['mean'],'precision':s['precision']['mean'],'recall':s['recall']['mean'],'fp1000':s['fp_per_1000_normal']['mean'],'missing_fraction':sum(v['missing'] for v in r)/sum(v['nv_beats'] for v in r),'rr_abs_error_median_ms':float(np.median(abs(err))*1000),'rr_abs_error_p95_ms':float(np.percentile(abs(err),95)*1000),'TP':sum(v['TP'] for v in r),'FP':sum(v['FP'] for v in r),'FN':sum(v['FN'] for v in r)}))

if __name__=='__main__':main()
