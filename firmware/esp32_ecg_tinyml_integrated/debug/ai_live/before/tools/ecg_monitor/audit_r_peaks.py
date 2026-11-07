"""Stage 1 only: unchanged C++ detector, historical Validation matching, offline XQRS.

Run from any directory with this tool's existing .venv. No COM, model, Test or firmware writes.
Generated artifacts live only in firmware debug/r_peak_audit and the requested report JSON.
"""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import scipy
from scipy.signal import resample_poly
import wfdb
from wfdb.processing import xqrs_detect
from validate_offline import BEATS, score

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / 'firmware/esp32_ecg_tinyml_integrated'
OUT = FW / 'debug/r_peak_audit'
TRACE = np.dtype([(k,'<f4') for k in ('baseline','magnitude','envelope','threshold')]
    + [(k,'<i4') for k in ('age','last_global','pending_global')] + [('flags','<u4')])
TOLERANCE = 12

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def assignment(ref, detected):
    """Exact same greedy ±12 matching and tie order as validate_offline.score."""
    detected = np.asarray(detected, dtype=np.int64)
    used = set(); matches = np.full(len(ref), -1, dtype=np.int64)
    for j, center in enumerate(ref):
        at = int(np.searchsorted(detected, center))
        candidates = [i for i in (at-1, at) if 0 <= i < len(detected)
            and i not in used and abs(int(detected[i])-int(center)) <= TOLERANCE]
        if candidates:
            chosen = min(candidates, key=lambda i: abs(int(detected[i])-int(center)))
            used.add(chosen); matches[j] = chosen
    fp = np.array([i for i in range(len(detected)) if i not in used], dtype=np.int64)
    return matches, fp

def detailed_score(ref, detected, symbols):
    metrics = score(ref, detected, symbols)
    matches, fp = assignment(ref, detected)
    assert np.sum(matches >= 0) == metrics['tp'] and len(fp) == metrics['fp']
    metrics['reference_beats'] = len(ref)
    metrics['by_annotation'] = {
        label: dict(reference=int(np.sum(symbols == label)),
            tp=int(np.sum((symbols == label) & (matches >= 0))),
            fn=int(np.sum((symbols == label) & (matches < 0))),
            sensitivity=float(np.mean(matches[symbols == label] >= 0)))
        for label in sorted(set(symbols.tolist()))}
    return metrics, matches, fp

def run_native(exe, path, trace_path=None):
    args = [str(exe), str(path)] + ([str(trace_path)] if trace_path else [])
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout

def rows_from(text):
    return [line.split(',') for line in text.splitlines()]

def reasons(ref, matches, trace, detected, events):
    """Descriptive blocking evidence, NOT a counterfactual causal attribution."""
    all_rows = []
    flags = trace['flags']
    resets = [(int(r[1]),r[2]) for r in events if r[0]=='issue']
    reset_indices = np.array([r[0] for r in resets],dtype=np.int64)
    for j, center in enumerate(ref):
        if matches[j] >= 0:
            continue
        center = int(center)
        # local maximum centered at k is tested at input k+1.
        candidates = np.arange(max(1,center-TOLERANCE+1), min(len(trace),center+TOLERANCE+2))
        local = candidates[(flags[candidates] & 1) != 0]
        above = local[(flags[local] & 2) != 0]
        ready = above[(flags[above] & 4) != 0]
        eligible = ready[(flags[ready] & 8) != 0]
        conflict = eligible[(flags[eligible] & 16) != 0]
        accepted = eligible[(flags[eligible] & 16) == 0]
        if center+127 >= len(trace): reason = 'END_WINDOW_UNAVAILABLE'
        elif trace['age'][center] < 500:
            reason = 'INITIAL_WARMUP' if center < 500 else 'RESET_WARMUP'
        elif len(accepted):
            aborted=any(np.any((flags[k:min(len(trace),k+127)]&64)!=0) for k in accepted)
            reason = 'ACCEPTED_THEN_RESET_BEFORE_WINDOW' if aborted else 'ACCEPTED_BUT_MATCHING_OR_ALIGNMENT'
        elif len(conflict): reason = 'PENDING_CONFLICT_RESET'
        elif len(ready): reason = 'REFRACTORY_BLOCK'
        elif len(above): reason = 'LOCAL_PEAK_DURING_WARMUP'
        elif len(local):
            k = max(local, key=lambda i: trace['magnitude'][i-1])
            reason = 'BELOW_ABSOLUTE_FLOOR' if trace['threshold'][k] <= 30.00001 else 'BELOW_ADAPTIVE_THRESHOLD'
        else: reason = 'NO_MAGNITUDE_LOCAL_MAX_WITHIN_TOLERANCE'
        at = int(np.searchsorted(detected,center))
        near = [int(detected[i]) for i in (at-1,at) if 0 <= i < len(detected)]
        nearest = min(near,key=lambda x:abs(x-center)) if near else None
        k = int(local[np.argmax(trace['magnitude'][np.maximum(local-1,0)])]) if len(local) else center
        reset_at = int(np.searchsorted(reset_indices,center,side='right'))-1
        last_reset = resets[reset_at] if reset_at >= 0 else None
        all_rows.append(dict(reference_index=j, sample=center, seconds=center/250,
            reason=reason, detector_age_samples=int(trace['age'][center]),
            nearest_emitted_delta_ms=None if nearest is None else (nearest-center)*4,
            nearby_max_magnitude_counts=float(trace['magnitude'][max(0,k-1)]),
            threshold_at_max_counts=float(trace['threshold'][k]),
            previous_reference_rr_ms=None if j == 0 else int(ref[j]-ref[j-1])*4,
            last_reset_reason=last_reset[1] if last_reset else None,
            last_reset_seconds=last_reset[0]/250 if last_reset else None))
    return all_rows

def dump_csv(path, rows):
    if not rows:return
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def summary_metrics(rows):
    tp=sum(r['tp'] for r in rows);fp=sum(r['fp'] for r in rows);fn=sum(r['fn'] for r in rows)
    return dict(reference_beats=tp+fn,tp=tp,fp=fp,fn=fn,sensitivity=tp/(tp+fn),ppv=tp/(tp+fp))

def plot_case(record, base, adc, trace, ref, syms, detections, xqrs, start, end, filename):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    original = wfdb.rdrecord(str(base), channels=[record['channel_index']],
        sampfrom=max(0,int(start*360)), sampto=min(record['original_samples'],int(end*360)))
    fig, axes = plt.subplots(4,1,figsize=(14,10),sharex=True,layout='constrained')
    original_t = np.arange(len(original.p_signal))/360 + max(0,int(start*360))/360
    axes[0].plot(original_t,original.p_signal[:,0],lw=.75,color='black',label='Original MLII 360 Hz (mV)')
    original_ann = wfdb.rdann(str(base),'atr',sampfrom=max(0,int(start*360)),sampto=int(end*360))
    for sample, symbol in zip(original_ann.sample,original_ann.symbol):
        if symbol in BEATS:axes[0].axvline(sample/360,color='gray',alpha=.5,lw=.6)
    axes[0].legend(loc='upper right');axes[0].set_ylabel('mV')
    a=max(0,int(start*250));b=min(len(adc),int(end*250));t=np.arange(a,b)/250
    for ax, det, title in ((axes[1],detections,'Production C++ emitted windows'),(axes[2],xqrs,'Offline WFDB XQRS; same quantized waveform')):
        ax.plot(t,adc[a:b],lw=.65,color='black',label='Detector input 250 Hz (ADC bench counts)')
        matched, fp = assignment(ref,det)
        for ok, marker, color, label in ((True,'o','green','TP annotation'),(False,'x','red','FN annotation')):
            keep=(ref>=a)&(ref<b)&((matched>=0)==ok);ids=np.flatnonzero(keep)
            ax.scatter(ref[ids]/250,adc[ref[ids]],marker=marker,color=color,s=42,label=label,zorder=4,facecolors='none' if ok else None)
            for j in ids:ax.annotate(str(syms[j]),(ref[j]/250,adc[ref[j]]),xytext=(2,9),textcoords='offset points',fontsize=7)
        d=det[(det>=a)&(det<b)];ax.scatter(d/250,adc[d],marker='|',color='blue',s=130,label='Detected center',zorder=5)
        f=det[fp];f=f[(f>=a)&(f<b)];ax.scatter(f/250,adc[f],marker='v',color='purple',s=48,label='FP detection',zorder=6)
        ax.set_title(title,fontsize=10);ax.set_ylabel('counts');ax.legend(loc='upper right',fontsize=7,ncol=3)
    axes[3].plot(t,trace['magnitude'][a:b],lw=.75,label='|raw - EMA baseline|')
    axes[3].plot(t,trace['threshold'][a:b],lw=.9,label='max(30, 2.5 x envelope)')
    axes[3].fill_between(t,0,1,where=trace['age'][a:b]<500,transform=axes[3].get_xaxis_transform(),color='orange',alpha=.2,label='Warm-up: age <500')
    conflicts=np.flatnonzero((trace['flags'][a:b]&16)!=0)+a
    for k in conflicts:axes[3].axvline(k/250,color='red',ls='--',lw=.8)
    axes[3].legend(fontsize=8,loc='upper right');axes[3].set(xlabel='Record time (seconds)',ylabel='counts',xlim=(start,end))
    fig.suptitle(f"Record {record['record']} MLII / {start:.3f}–{end:.3f}s / ±12 samples matching; no diagnosis")
    fig.savefig(filename,dpi=130);plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    before=json.loads((OUT/'before_sha256.json').read_text())
    historical=json.loads((ROOT/'tools/ecg_monitor/reports/offline_validation.json').read_text())
    split=ROOT/'data/processed/mitbih_split_indices.npz';dataset=ROOT/'data/processed/mitbih_nv_250hz.npz'
    with np.load(split,allow_pickle=False) as parts,np.load(dataset,allow_pickle=False) as data:
        records=sorted(set(data['record_ids'][parts['validation_indices']].tolist()))
    assert records == historical['records']
    per_record=[];all_fn=[];all_worst=[];all_examples=[];inputs={};class_totals=defaultdict(Counter);class_xqrs=defaultdict(Counter)
    for rid in records:
        start_time=time.perf_counter();base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid
        header=wfdb.rdheader(str(base));assert header.fs==360
        channel=[s.strip().upper() for s in header.sig_name].index('MLII')
        ecg=wfdb.rdrecord(str(base),channels=[channel]).p_signal[:,0]
        resampled=resample_poly(ecg,25,36)
        adc=np.clip(np.rint(2048+200*resampled),0,4095).astype('<i2')
        path=OUT/f'{rid}_adc.bin';adc.tofile(path)
        old_path=ROOT/f'tools/ecg_monitor/reports/offline/{rid}_adc.bin'
        assert sha(path)==sha(old_path),f'ADC input differs from historical replay: {rid}'
        text=run_native(OUT/'detector_baseline.exe',path)
        audited=run_native(OUT/'detector_audit.exe',path,OUT/f'{rid}_trace.bin')
        assert text==audited,'Diagnostic harness altered native events'
        (OUT/f'{rid}_native_events.csv').write_text(text,encoding='utf-8')
        rows=rows_from(text);det=np.array([int(r[1]) for r in rows if r[0]=='peak'],dtype=np.int64)
        gated=np.array([int(r[1]) for r in rows if r[0]=='gated_peak'],dtype=np.int64)
        trace=np.fromfile(OUT/f'{rid}_trace.bin',dtype=TRACE);assert len(trace)==len(adc)
        ann=wfdb.rdann(str(base),'atr');mask=np.array([s in BEATS for s in ann.symbol]);syms=np.asarray(ann.symbol)[mask]
        original_ref=ann.sample[mask];ref=np.floor(original_ref*25/36+.5).astype(np.int64)
        rational=(original_ref*25+18)//36;assert np.array_equal(ref,rational)
        metric,matches,fp=detailed_score(ref,det,syms);gm,_,_=detailed_score(ref,gated,syms)
        old=next(r for r in historical['per_record'] if r['record']==rid)
        assert score(ref,det,syms)==old['candidate']
        assert score(ref,gated,syms)==old['quality_gated']
        xqrs_start=time.perf_counter()
        xp=xqrs_detect((adc.astype(float)-2048)/200,fs=250,learn=True,verbose=False)
        xm,xmatches,xfp=detailed_score(ref,xp,syms)
        xqrs_seconds=time.perf_counter()-xqrs_start
        fn=reasons(ref,matches,trace,det,rows)
        for row in fn:row.update(record=rid,label=str(syms[row['reference_index']]))
        all_fn.extend(fn)
        for label, values in metric['by_annotation'].items():class_totals[label].update({k:values[k] for k in ('reference','tp','fn')})
        for label, values in xm['by_annotation'].items():class_xqrs[label].update({k:values[k] for k in ('reference','tp','fn')})
        conflicts=np.flatnonzero((trace['flags']&16)!=0)
        conflict_rr=(conflicts-1-trace['last_global'][conflicts])*4
        quality=Counter(r[2] for r in rows if r[0]=='quality')
        issues=Counter(r[2] for r in rows if r[0]=='issue')
        reason_counts=Counter(r['reason'] for r in fn)
        # Fixed, non-overlapping ten-second bins; no record or boundary exclusions.
        worst=[]
        for window in range((len(adc)+2499)//2500):
            a=window*2500;b=min(a+2500,len(adc));keep=(ref>=a)&(ref<b)
            missed=keep&(matches<0)
            if not np.any(missed):continue
            worst.append(dict(record=rid,start_seconds=a/250,end_seconds=b/250,
                reference_beats=int(np.sum(keep)),fn=int(np.sum(missed)),
                fn_N=int(np.sum(missed&(syms=='N'))),fn_V=int(np.sum(missed&(syms=='V')))))
        worst.sort(key=lambda r:(-r['fn'],r['start_seconds']));all_worst.extend(worst[:10])
        rr=np.r_[np.nan,np.diff(ref)*4]
        rr_rows=[]
        for name,lo,hi in (('<=300ms',0,300),('300..508ms',300,508),('508..1000ms',508,1000),('>1000ms',1000,np.inf)):
            keep=(rr>lo)&(rr<=hi);n=int(np.sum(keep));miss=int(np.sum(keep&(matches<0)))
            rr_rows.append(dict(bin=name,reference=n,fn=miss,sensitivity=(n-miss)/n if n else None))
        # Morphology evidence uses baseline residual extrema within unchanged tolerance.
        morphology=[]
        for center in ref:
            a=max(0,int(center)-12);b=min(len(trace),int(center)+13)
            k=a+int(np.argmax(trace['magnitude'][a:b]));morphology.append((k,float(adc[k])-float(trace['baseline'][k])))
        residual=np.array([m[1] for m in morphology]);amplitude=np.abs(residual)
        morph={}
        for key,keep in [('positive',residual>=0),('negative',residual<0),('max_residual_below30',amplitude<30),('max_residual_atleast30',amplitude>=30)]:
            n=int(np.sum(keep));miss=int(np.sum(keep&(matches<0)))
            morph[key]=dict(reference=n,fn=miss,sensitivity=(n-miss)/n if n else None)
        record=dict(record=rid,channel_index=channel,lead=header.sig_name[channel],all_leads=header.sig_name,
            units=header.units[channel],original_fs=header.fs,original_samples=len(ecg),samples=len(adc),
            candidate=metric,quality_gated=gm,xqrs=xm,detector_issues=dict(issues),
            gated_issues=dict(Counter(r[2] for r in rows if r[0]=='gated_issue')),
            quality_blocks=dict(quality),fn_blocking_evidence=dict(reason_counts),rr_bins=rr_rows,morphology=morph,
            warmup_fn_by_preceding_reset=dict(Counter(r['last_reset_reason'] for r in fn if r['reason']=='RESET_WARMUP')),
            warmup_samples=int(np.sum(trace['age']<500)),warmup_seconds=float(np.sum(trace['age']<500)/250),
            conflict_intervals_ms=dict(count=len(conflicts),minimum=int(np.min(conflict_rr)) if len(conflicts) else None,
                maximum=int(np.max(conflict_rr)) if len(conflicts) else None),
            annotation_rounding_max_error_ms=float(np.max(np.abs(ref/250-original_ref/360))*1000),
            adc_clipped_samples=int(np.sum((adc==0)|(adc==4095))),worst_ten_second_windows=worst[:10],
            elapsed_host_seconds=time.perf_counter()-start_time,xqrs_host_seconds=xqrs_seconds)
        per_record.append(record)
        inputs[rid]={ext:sha(base.with_suffix('.'+ext)) for ext in ('hea','dat','atr')}
        np.savez_compressed(OUT/f'{rid}_detections.npz',reference=ref,symbols=syms,detected=det,gated=gated,
            xqrs=xp,native_match=matches,xqrs_match=xmatches,native_fp_indices=fp,xqrs_fp_indices=xfp)
        # Representative plots: worst segment of every record and selected blocking cases.
        examples=[(worst[0]['start_seconds'],worst[0]['end_seconds'],'worst10s')] if worst else []
        if rid in ('210','214','233'):
            for reason in ('PENDING_CONFLICT_RESET','BELOW_ABSOLUTE_FLOOR','BELOW_ADAPTIVE_THRESHOLD','REFRACTORY_BLOCK'):
                case=next((r for r in fn if r['reason']==reason),None)
                if case:examples.append((max(0,case['seconds']-3),min(len(adc)/250,case['seconds']+5),reason.lower()))
            case=next((r for r in fn if r['label']=='V' and r['reason']=='RESET_WARMUP'),None)
            if case:examples.append((max(0,case['seconds']-3),min(len(adc)/250,case['seconds']+5),'pvc_reset_warmup'))
        if rid=='115':
            case=next(r for r in fn if r['reason']=='REFRACTORY_BLOCK')
            examples.append((case['seconds']-3,case['seconds']+5,'refractory_block'))
        for a,b,name in examples:
            filename=OUT/f'{rid}_{name}.png'
            plot_case(record,base,adc,trace,ref,syms,det,xp,a,b,filename)
            all_examples.append(dict(record=rid,start_seconds=a,end_seconds=b,tag=name,path=str(filename.relative_to(FW))))
        print(json.dumps(dict(record=rid,baseline=metric['sensitivity'],xqrs=xm['sensitivity'],issues=dict(issues),fn_reasons=dict(reason_counts))),flush=True)
    controls={};xqrs_controls={}
    for name,raw in [('no_peaks',np.full(7500,2048)),('pure50Hz',2048+100*np.sin(2*np.pi*50*np.arange(7500)/250))]:
        path=OUT/f'{name}.bin';np.rint(raw).astype('<i2').tofile(path)
        rows=rows_from(run_native(OUT/'detector_baseline.exe',path))
        controls[name]=dict(candidate_peaks=sum(r[0]=='peak' for r in rows),quality_gated_peaks=sum(r[0]=='gated_peak' for r in rows))
        same=np.rint(raw).astype('<i2')
        xqrs_controls[name]=dict(candidate_peaks=len(xqrs_detect((same.astype(float)-2048)/200,250,learn=True,verbose=False)))
    assert controls==historical['controls']
    for values in (class_totals,class_xqrs):
        for v in values.values():v['sensitivity']=v['tp']/v['reference']
    unchanged={name:sha(ROOT/name)==digest for name,digest in before.items()};assert all(unchanged.values())
    baseline=summary_metrics([r['candidate'] for r in per_record]);assert {k:baseline[k] for k in historical['aggregate']}==historical['aggregate']
    criteria=historical['criteria']
    def passed(r):
        return r['sensitivity']>=criteria['sensitivity_min'] and r['ppv']>=criteria['ppv_min'] and r['timing_p95_abs_ms']<=criteria['timing_p95_max_ms']
    report=dict(status='STAGE1_ANALYSIS_COMPLETE_DETECTOR_UNCHANGED_AI_LIVE_LOCKED',records=records,
        scope='Same Validation records, beat symbols, ADC representation, greedy matching and tolerance as historical score; no Test',
        criteria=criteria,baseline=baseline,quality_gated=summary_metrics([r['quality_gated'] for r in per_record]),
        xqrs=summary_metrics([r['xqrs'] for r in per_record]),by_annotation={k:dict(v) for k,v in class_totals.items()},
        xqrs_by_annotation={k:dict(v) for k,v in class_xqrs.items()},per_record=per_record,
        current_record_criteria={r['record']:passed(r['candidate']) for r in per_record},
        xqrs_record_criteria={r['record']:passed(r['xqrs']) for r in per_record},
        controls=controls,xqrs_controls=xqrs_controls,
        candidate_all_criteria_pass=all(passed(r['candidate']) for r in per_record) and all(c['candidate_peaks']==0 for c in controls.values()),
        xqrs_all_criteria_pass=all(passed(r['xqrs']) for r in per_record) and all(c['candidate_peaks']==0 for c in xqrs_controls.values()),
        fn_blocking_evidence=dict(Counter(r['reason'] for r in all_fn)),
        worst_ten_second_windows=sorted(all_worst,key=lambda r:(-r['fn'],r['record'],r['start_seconds']))[:20],
        examples=all_examples,matching=dict(beat_symbols=''.join(sorted(BEATS)),tolerance_samples=12,tolerance_ms=48,
            algorithm='unchanged reference-ordered greedy nearest of searchsorted neighbors; detection used once; no time-shift correction',
            class_ppv_limit='Unmatched QRS has no true N/V type; per-symbol sensitivity reported; global PPV only'),
        xqrs_configuration=dict(wfdb=wfdb.__version__,fs=250,learn=True,defaults=True,
            input='(same quantized ADC -2048)/200 in mV; no peak correction, no rescore shift',
            implementation='offline noncausal filtfilt; not a drop-in streaming ESP32 detector'),
        versions=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,wfdb=wfdb.__version__),
        input_sha256=inputs,protected_checks=unchanged,
        tool_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),FW/'tests/detector_audit_replay.cpp',FW/'tests/detector_replay.cpp',FW/'tests/sdkconfig.h')},
        ai_live_unlocked=False,firmware_changed=False,com_opened=False,flashed=False,
        limitations=['Blocking labels are descriptive, overlapping upstream causes remain; no additive causal improvement claim',
            'Validation reused; not independent final assessment',
            'Host quality-gated replay is existing mirror, not full RTOS/generation/FSM simulation',
            'Fixed synthetic ADC gain200counts/mV, not AD8232 calibration',
            'No hardware/simulator/ECG-body claim; no model inference needed in this stage'])
    dump_csv(OUT/'false_negatives.csv',all_fn);dump_csv(OUT/'worst_windows.csv',all_worst)
    from r_peak_audit_report import finish
    finish(report)
    print(json.dumps(dict(baseline=report['baseline'],xqrs=report['xqrs'],quality_gated=report['quality_gated']),indent=2))

if __name__=='__main__':main()
