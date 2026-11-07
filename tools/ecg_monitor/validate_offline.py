"""Exploratory Validation records only; native actual detector and CNN; no Test.

This command never writes original data/splits/models and never changes firmware configuration.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import wfdb
from scipy.signal import resample_poly
from ecg_monitor.offline import display_filter

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
FIRMWARE=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=HERE/'reports/offline'
BEATS=set('NLRBAaJSVrFejnE/fQ?')


def score(reference,detected,symbols):
    detected=np.asarray(detected,dtype=int);used=set();errors=[];by_class=Counter();miss=Counter()
    for center,symbol in zip(reference,symbols):
        at=int(np.searchsorted(detected,center));candidates=[i for i in (at-1,at) if 0<=i<len(detected) and i not in used and abs(detected[i]-center)<=12]
        if not candidates:miss[symbol]+=1;continue
        chosen=min(candidates,key=lambda i:abs(detected[i]-center));used.add(chosen);errors.append(int(detected[chosen]-center)*4);by_class[symbol]+=1
    tp=len(used);fp=len(detected)-tp;fn=len(reference)-tp
    return dict(tp=tp,fp=fp,fn=fn,sensitivity=tp/(tp+fn) if tp+fn else None,ppv=tp/(tp+fp) if tp+fp else None,
        timing_median_abs_ms=float(np.median(np.abs(errors))) if errors else None,
        timing_p95_abs_ms=float(np.percentile(np.abs(errors),95)) if errors else None,
        matched_by_annotation=dict(by_class),missed_by_annotation=dict(miss))


def native(path):
    r=subprocess.run([str(FIRMWARE/'tests/detector_replay.exe'),str(path)],text=True,capture_output=True,check=True)
    rows=[line.split(',') for line in r.stdout.splitlines()]
    return rows


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    split=ROOT/'data/processed/mitbih_split_indices.npz';dataset=ROOT/'data/processed/mitbih_nv_250hz.npz'
    with np.load(split,allow_pickle=False) as parts,np.load(dataset,allow_pickle=False) as data:
        records=sorted(set(data['record_ids'][parts['validation_indices']].tolist()))
    results=[];windows=[];labels=[];metadata=[];filter_corr=[];filter_peak_shift=[]
    for record in records:
        base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/record;header=wfdb.rdheader(str(base))
        channel=[s.strip().upper() for s in header.sig_name].index('MLII')
        signal=wfdb.rdrecord(str(base),channels=[channel]).p_signal[:,0]
        if header.fs!=360:raise ValueError('Expected local360Hz record')
        resampled=resample_poly(signal,25,36)
        # Explicit bench ADC representation; no claim of hardware calibration.
        adc=np.clip(np.rint(2048+200*resampled),0,4095).astype('<i2')
        path=OUT/f'{record}_adc.bin';adc.tofile(path);rows=native(path)
        detected=[int(r[1]) for r in rows if r[0]=='peak'];gated=[int(r[1]) for r in rows if r[0]=='gated_peak']
        ann=wfdb.rdann(str(base),'atr');symbols=np.asarray(ann.symbol)
        mask=np.array([s in BEATS for s in symbols]);centers=np.floor(ann.sample[mask]*25/36+.5).astype(int);syms=symbols[mask]
        filtered=display_filter(adc)
        for center,sym in zip(centers,syms):
            if sym not in ('N','V') or center<128 or center+128>len(adc):continue
            a=adc[center-128:center+128].astype(float);b=filtered[center-128:center+128]
            if a.std()>1e-8 and b.std()>1e-8:
                filter_corr.append(float(np.corrcoef(a,b)[0,1]));filter_peak_shift.append(int(np.argmax(np.abs(b-b.mean()))-np.argmax(np.abs(a-a.mean()))))
        for center in gated:
            at=int(np.searchsorted(centers,center));candidates=[i for i in (at-1,at) if 0<=i<len(centers) and abs(centers[i]-center)<=12]
            if not candidates or center<128 or center+128>len(adc):continue
            i=min(candidates,key=lambda i:abs(centers[i]-center))
            if syms[i] not in ('N','V'):continue
            windows.append(adc[center-128:center+128].astype('<f4'));labels.append(int(syms[i]=='V'))
            metadata.append(dict(record=record,annotation_center=int(centers[i]),detected_center=center,label=str(syms[i])))
        result=dict(record=record,samples=len(adc),candidate=score(centers,detected,syms),quality_gated=score(centers,gated,syms),
            quality_blocks=dict(Counter(r[2] for r in rows if r[0]=='quality')),detector_issues=dict(Counter(r[2] for r in rows if r[0]=='issue')))
        results.append(result);print(record,result['candidate'],flush=True)
    # Pure50Hz and flat controls: no annotations. Any detected peaks are FP.
    controls={}
    for name,raw in [('no_peaks',np.full(7500,2048)),('pure50Hz',2048+100*np.sin(2*np.pi*50*np.arange(7500)/250))]:
        path=OUT/f'{name}.bin';np.rint(raw).astype('<i2').tofile(path);rows=native(path)
        controls[name]=dict(candidate_peaks=sum(r[0]=='peak' for r in rows),quality_gated_peaks=sum(r[0]=='gated_peak' for r in rows))
    # Labeled ECG plus artificial interference: assess rejection rather than
    # treating a visually periodic waveform as proof of real mains coupling.
    base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/records[0]
    header=wfdb.rdheader(str(base));channel=[s.strip().upper() for s in header.sig_name].index('MLII')
    short=resample_poly(wfdb.rdrecord(str(base),channels=[channel],sampto=360*120).p_signal[:,0],25,36)
    noisy=short+.5*np.sin(2*np.pi*50*np.arange(len(short))/250)
    path=OUT/'labeled_ecg_plus50Hz.bin';np.clip(np.rint(2048+200*noisy),0,4095).astype('<i2').tofile(path);rows=native(path)
    ann=wfdb.rdann(str(base),'atr',sampto=360*120);mask=np.array([s in BEATS for s in ann.symbol])
    refs=np.floor(ann.sample[mask]*25/36+.5).astype(int);syms=np.asarray(ann.symbol)[mask]
    noisy_review=dict(source=f'Validation record{records[0]} first120s + synthetic0.5mV50Hz',
        candidate=score(refs,[int(r[1]) for r in rows if r[0]=='peak'],syms),
        quality_gated=score(refs,[int(r[1]) for r in rows if r[0]=='gated_peak'],syms),
        quality_blocks=dict(Counter(r[2] for r in rows if r[0]=='quality')))
    tp=sum(r['candidate']['tp'] for r in results);fp=sum(r['candidate']['fp'] for r in results);fn=sum(r['candidate']['fn'] for r in results)
    criteria=dict(sensitivity_min=.99,ppv_min=.99,timing_p95_max_ms=40,noise_false_peaks_max=0,matching_tolerance_samples=12)
    detector_pass=all(r['candidate']['sensitivity']>=.99 and r['candidate']['ppv']>=.99 and r['candidate']['timing_p95_abs_ms']<=40 for r in results) and all(c['candidate_peaks']==0 for c in controls.values())
    chain={'status':'NO_ELIGIBLE_BEATS','scope':'Host component chain; not hardware/freeRTOS pipeline certification'}
    if windows:
        raw=np.stack(windows);raw_path=OUT/'detected_windows_f32.bin';raw.tofile(raw_path)
        q_path=OUT/'native_input_int8.bin'
        subprocess.run([str(FIRMWARE/'tests/preprocess_host.exe'),str(raw_path),str(q_path)],check=True)
        double=raw.astype(np.float64);z=((double-double.mean(axis=1,keepdims=True))/double.std(axis=1,keepdims=True)).astype(np.float32)
        unclipped=np.rint(z.astype(np.float64)/np.float32(.053921569138765335))-27
        clipped=np.any((unclipped<-128)|(unclipped>127),axis=1);eligible=~clipped
        python_q=np.clip(unclipped,-128,127).astype(np.int8)
        cpp_q=np.fromfile(q_path,dtype=np.int8).reshape(-1,256)
        mismatches=int(np.count_nonzero(cpp_q!=python_q))
        native_codes=OUT/'native_codes.bin';reference_codes=OUT/'reference_codes.bin';model=FIRMWARE/'main/model/ecg_cnn_int8.tflite'
        subprocess.run([str(FIRMWARE/'debug/host_mode2/full_chain.exe'),str(model),str(q_path),str(native_codes),'--batch'],check=True)
        ref_run=subprocess.run([str(HERE/'.venv_reference/Scripts/python.exe'),str(HERE/'validate_reference.py'),str(model),str(q_path),str(reference_codes)],text=True,capture_output=True)
        (OUT/'tensorflow_reference.log').write_text(ref_run.stdout+ref_run.stderr,encoding='utf-8')
        actual=np.fromfile(native_codes,dtype=np.int8);reference=np.fromfile(reference_codes,dtype=np.int8) if ref_run.returncode==0 else None
        if reference is not None and actual.shape!=reference.shape:raise ValueError('Native/reference output count mismatch')
        predicted=(actual.astype(float)+128)/256>=.52;truth=np.asarray(labels)
        chain=dict(status='REFERENCE_BLOCKED' if reference is None else 'COMPONENT_PARITY_PASS' if not mismatches and np.array_equal(actual,reference) else 'COMPONENT_PARITY_FAIL',
            scope='Exploratory matched N/V detections on Validation; excludes missed/false/other-label peaks; NOT end-to-end clinical accuracy',
            beats=len(windows),preprocessing_mismatched_bytes=mismatches,cnn_mismatched_codes=int(np.count_nonzero(actual!=reference)) if reference is not None else None,
            quantization_clipped_beats=int(np.sum(clipped)),runtime_eligible_beats=int(np.sum(eligible)),
            classification_metrics_scope='Matched N/V windows only, additionally exclude quantization clipping as firmware would; not full pipeline accuracy',
            matched_pvc_tp=int(np.sum(predicted&(truth==1)&eligible)),matched_pvc_fn=int(np.sum(~predicted&(truth==1)&eligible)),
            matched_normal_fp=int(np.sum(predicted&(truth==0)&eligible)),matched_normal_tn=int(np.sum(~predicted&(truth==0)&eligible)))
        (OUT/'detected_windows_metadata.json').write_text(json.dumps(metadata,indent=2))
    report=dict(status='PASS' if detector_pass else 'DETECTOR_CRITERIA_FAIL',source='LocalMITBIH_MLII_VALIDATION_ONLY',
        records=records,criteria=criteria,aggregate=dict(tp=tp,fp=fp,fn=fn,sensitivity=tp/(tp+fn),ppv=tp/(tp+fp)),
        per_record=results,controls=controls,noisy_ecg=noisy_review,chain=chain,
        filter_review=dict(annotation_windows=len(filter_corr),median_raw_filtered_correlation=float(np.median(filter_corr)),
            p95_absolute_peak_displacement_samples=float(np.percentile(np.abs(filter_peak_shift),95)),
            decision='NOT_APPROVED_FOR_CNN: causal filter alters morphology/alignment; existing unfiltered preprocessing unchanged'),
        limitations=['Validation reused: exploratory, no held-out final claim','Candidate detector standalone and host quality-gated mirror, not real-time firmware scheduler',
            'ADC mapping2048+200counts/mV is an explicit synthetic bench representation, not calibration','Warm-up and end-boundary missed beats counted as FN',
            'Golden inference PASS does not establish peak-detector or live system validity','Hardware/simulator validation BLOCKED until user flashes/tests'],
        input_split_sha256=hashlib.sha256(split.read_bytes()).hexdigest(),live_unlocked=False)
    (HERE/'reports/offline_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['aggregate'],indent=2))


if __name__=='__main__':main()
