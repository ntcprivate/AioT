import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,hashlib,subprocess
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
from run_v11_rr import rr_at,BEATS

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/end_to_end_detector';FW=ROOT/'firmware/esp32_ecg_tinyml_integrated'
def score(tp,fp,fn,tn,n):
    p=tp/(tp+fp) if tp+fp else 0;r=tp/(tp+fn) if tp+fn else 0
    return dict(TP=tp,FP=fp,FN=fn,TN=tn,precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,fp_per_1000_N=1000*fp/n if n else 0)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'evaluation.json').exists():raise RuntimeError('Completed artifact exists')
    folds=json.loads((ROOT/'results/v10_research/step1_5fold_cv/folds_split.json').read_text());old=json.loads((ROOT/'results/v10_research/step1_5fold_cv/cv_evaluation.json').read_text());v11=json.loads((ROOT/'results/cnn_v11/evaluation.json').read_text())
    # Fixed before inference: fallback for fewer than 2 RR intervals or any
    # timing feature beyond 3 Fit standard deviations. No annotation matching.
    config={'fallback':'history_fraction < 2/8 OR any abs(Fit-zscore timing features[0:3]) > 3','matching_tolerance_samples':38,'scope':'original Development/Validation only; detector-generated windows; ungated detector stream, not full firmware quality gate; synthetic ADC mapping 2048+200counts/mV','missing_N':'not counted TN; separately reported missed_N; all missed V count FN','OTHER':'excluded from N/V classification, never relabeled N','adaptive_limit':'development previously examined; exploratory result'}
    (OUT/'config.json').write_text(json.dumps(config,indent=2))
    mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');split=np.load(ROOT/'data/processed/mitbih_split_indices.npz');inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
    lists={'MITBIH':sorted(set(mit['record_ids'][split['validation_indices']].astype(str))),'INCART':sorted(set(inc['record_ids'][inc['split']=='validation'].astype(str)))}
    exe=ROOT/'results/cnn_v11/rr_detector_validation/detector.exe'
    records=[];totals={ds:{m:np.zeros(4,dtype=np.int64) for m in ['V6','V11','fallback']} for ds in lists};normals={ds:0 for ds in lists}
    for ds,recs in lists.items():
      for rec in recs:
        base=ROOT/('mit-bih-arrhythmia-database-1.0.0' if ds=='MITBIH' else 'files')/rec
        h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');names=[s.strip().upper() for s in h.sig_name];ch=names.index('MLII' if ds=='MITBIH' else 'II')
        group=rec if ds=='MITBIH' else str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==rec)[0]])
        k=next(f['fold_index'] for f in folds if group in f['outer_MITBIH_records' if ds=='MITBIH' else 'outer_INCART_patients'])
        sig=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],25 if ds=='MITBIH' else 250,36 if ds=='MITBIH' else 257)
        raw=np.clip(np.rint(2048+200*sig),0,4095).astype('<i2');raw.tofile(OUT/'input.bin')
        log=OUT/f'{ds}_{rec}.csv';win=OUT/'windows.bin'
        with log.open('w') as f:subprocess.run([str(exe),str(OUT/'input.bin'),str(win),str(OUT/'safe.bin')],stdout=f,check=True)
        events=[s.split(',') for s in log.read_text().splitlines()];peaks=np.asarray([int(v[1]) for v in events if v[0]=='peak']);emits=np.asarray([int(v[2]) for v in events if v[0]=='peak'])
        windows=np.fromfile(win,dtype=np.float32).reshape(-1,256,1);assert len(windows)==len(peaks)
        std=windows.std(1,keepdims=True);valid=np.isfinite(windows).all((1,2))&(std[:,0,0]>1e-8);x=(windows-windows.mean(1,keepdims=True))/np.maximum(std,1e-8)
        rr=np.asarray([rr_at(peaks[:j+1]/250.,peaks[j]/250.) for j in range(len(peaks))],dtype=np.float32)
        saved=v11['folds'][k];mean=np.asarray(saved['rr_fit_mean']);sd=np.asarray(saved['rr_fit_std']);z=(rr-mean)/sd
        fallback=(rr[:,3]<.25)|(abs(z[:,:3])>3).any(1)
        s6=old['models']['V6']['folds'][k];p6=ROOT/f'results/v10_research/step1_5fold_cv/checkpoints/v6_fold{k}_best.keras';p11=ROOT/f'models/v11/v11_fold{k}_best.keras'
        assert hashlib.sha256(p6.read_bytes()).hexdigest()==s6['checkpoint_sha256'];assert hashlib.sha256(p11.read_bytes()).hexdigest()==saved['checkpoint_sha256']
        m6=tf.keras.models.load_model(p6,compile=False);m11=tf.keras.models.load_model(p11,compile=False)
        a=m6.predict(x,batch_size=512,verbose=0).ravel()>=s6['calibrated_threshold'];b=m11.predict({'ecg_256':x,'rr_features':z},batch_size=512,verbose=0).ravel()>=saved['threshold'];preds={'V6':a,'V11':b,'fallback':np.where(fallback,a,b)}
        refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS];used=set();pairs={};offset=[]
        for ri,(t,c) in enumerate(refs):
            cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
            if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);pairs[ri]=j;offset.append(int(peaks[j]-t))
        missingN=sum(c=='N' and ri not in pairs for ri,(t,c) in enumerate(refs));missingV=sum(c=='V' and ri not in pairs for ri,(t,c) in enumerate(refs));n=sum(c=='N' for t,c in refs);normals[ds]+=n
        row={'dataset':ds,'record':rec,'fold':k,'reference_N':n,'reference_V':sum(c=='V' for t,c in refs),'missed_N':missingN,'missed_V':missingV,'all_beat_FN':len(refs)-len(pairs),'extra_peaks':len(peaks)-len(used),'offset_samples':offset,'fallback_fraction':float(fallback.mean()),'no_peak_resets':sum(v[0]=='issue' and 'NO' in ','.join(v) for v in events),'quality_reasons':{},'metrics':{}}
        for v in events:
            if v[0]=='quality':row['quality_reasons'][v[2]]=row['quality_reasons'].get(v[2],0)+1
        for name,pred in preds.items():
            tp=fp=tn=0;fn=missingV
            for ri,j in pairs.items():
                c=refs[ri][1]
                if c not in {'N','V'}:continue
                if not valid[j]:fn+=int(c=='V');continue
                tp+=int(c=='V' and pred[j]);fn+=int(c=='V' and not pred[j]);fp+=int(c=='N' and pred[j]);tn+=int(c=='N' and not pred[j])
            fp+=sum(bool(pred[j]) and valid[j] for j in range(len(peaks)) if j not in used)
            totals[ds][name]+=np.asarray([tp,fp,fn,tn]);row['metrics'][name]=score(tp,fp,fn,tn,n)
        np.savez_compressed(OUT/f'{ds}_{rec}_predictions.npz',peaks=peaks,emits=emits,pred6=a,pred11=b,fallback=fallback)
        records.append(row);print(ds,rec,'done',flush=True)
    result={'config':config,'records':records,'pooled':{ds:{m:score(*map(int,v),normals[ds]) for m,v in ms.items()} for ds,ms in totals.items()}}
    (OUT/'evaluation.json').write_text(json.dumps(result,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else v));print(json.dumps(result['pooled'],indent=2))
if __name__=='__main__':main()
