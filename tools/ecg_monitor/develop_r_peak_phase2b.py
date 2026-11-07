"""Predeclared tiny development comparison on Train only. Never reads Test signals."""
from pathlib import Path
import hashlib,json,subprocess
import numpy as np
import wfdb
from scipy.signal import resample_poly
from audit_r_peaks import score,BEATS,rows_from,run_native
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/r_peak_phase2b';BEFORE=FW/'debug/r_peak_phase2b_before'
RECORDS=['105','106','114','119','208','219']

PUSH='''bool BeatDetector::push(int raw,int64_t timestamp,float* beat,const char*& issue) {
    issue=nullptr;const int64_t sample=next_sample_++;const int64_t current=count_++;
    ++counters_.samples;if(current<500)++counters_.warmup_samples;
    if(raw<0 || raw>4095 || timestamp<0) {issue="INVALID_ADC_SAMPLE";reset_state();return false;}
    if(current>0 && (timestamp-last_timestamp_<2000 || timestamp-last_timestamp_>6000)) {
        issue="BEAT_TIMING_GAP";reset_state();return false;
    }
    last_timestamp_=timestamp;
    if(!windows_.append(raw,sample,timestamp,issue)) {reset_state();return false;}
    if(current==0)baseline_=raw;
    baseline_+=0.01f*(raw-baseline_);
    int64_t center=-1;float strength=0;
    const bool proposed=feature_.push(raw,sample,baseline_,center,strength);
    if(current>=500 && proposed && (last_center_<0 || center-last_center_>=75)) {
        ++counters_.candidates;last_center_=center;no_peak_reported_=false;
        if(!windows_.enqueue(center,issue))return false;
    }
    if(windows_.pop_ready(beat,last_window_,issue))return true;
    if(issue) {reset_state();return false;}
    if(current>1000 && (last_center_<0 || sample-last_center_>500) && !no_peak_reported_) {
        // Still surface invalid/stale signal to the existing safety path, but do not
        // destroy the adaptive detector history solely for lack of a peak.
        issue="NO_RELIABLE_R_PEAK";no_peak_reported_=true;++no_peak_events_;
    }
    return false;
}
'''
def source(gap):
    h=(BEFORE/'main/signal.h').read_text()
    h=h.replace('#include <cstdint>','#include <cstdint>\n#include "qrs_feature.h"')
    h=h.replace('    float baseline_ = 0, envelope_ = 0, prev_abs_ = 0, before_abs_ = 0;',f'    float baseline_=0;\n    CausalQrsFeature<{gap}> feature_;\n    int64_t last_timestamp_=0;\n    uint64_t no_peak_events_=0;\n    bool no_peak_reported_=false;')
    h=h.replace('    BeatWindowStats windows={};','    BeatWindowStats windows={};\n    uint64_t no_peak_events=0;')
    c=(BEFORE/'main/signal.cpp').read_text()
    c=c[:c.index('bool BeatDetector::push(')]+PUSH
    c=c.replace('    baseline_=envelope_=prev_abs_=before_abs_=0;','    baseline_=0;feature_.reset();last_timestamp_=0;no_peak_reported_=false;')
    c=c.replace('counters_.no_peak_resets,counters_.external_resets,windows_.stats()};','counters_.no_peak_resets,counters_.external_resets,windows_.stats(),no_peak_events_};')
    return h,c
def main():
    with np.load(ROOT/'data/processed/mitbih_split_indices.npz') as s,np.load(ROOT/'data/processed/mitbih_nv_250hz.npz') as d:
        train=set(d['record_ids'][s['train_indices']].tolist());val=set(d['record_ids'][s['validation_indices']].tolist())
    assert set(RECORDS)<=train and not set(RECORDS)&val
    manifest=dict(records=RECORDS,candidates=[6,8,10],selection='Maximize macro F1 on these Train records only; tie higher min sensitivity, then smaller gap',source='Phase2A plus causal curvature/confirmation and non-destructive no-peak event')
    (OUT/'development_plan.json').write_text(json.dumps(manifest,indent=2))
    corpus=[]
    for rid in RECORDS:
        base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid;header=wfdb.rdheader(str(base));ch=[s.upper().strip() for s in header.sig_name].index('MLII')
        adc=np.clip(np.rint(2048+200*resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],25,36)),0,4095).astype('<i2')
        path=OUT/f'development_{rid}.bin';adc.tofile(path)
        ann=wfdb.rdann(str(base),'atr');mask=np.array([s in BEATS for s in ann.symbol]);ref=(ann.sample[mask]*25+18)//36;symbols=np.asarray(ann.symbol)[mask]
        corpus.append((rid,path,ref,symbols))
    results=[]
    for gap in manifest['candidates']:
        proto=OUT/f'prototype_gap{gap}';proto.mkdir(exist_ok=True)
        h,c=source(gap);(proto/'signal.h').write_text(h);(proto/'signal.cpp').write_text(c)
        (proto/'qrs_feature.h').write_bytes((OUT/'rejected_qrs_feature.h').read_bytes())
        exe=proto/'detector.exe'
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(proto),'-I',str(FW/'tests'),str(proto/'signal.cpp'),str(FW/'tests/detector_replay.cpp'),'-o',str(exe)],check=True)
        rows=[]
        for rid,path,ref,syms in corpus:
            events=rows_from(run_native(exe,path));det=[int(r[1]) for r in events if r[0]=='peak'];m=score(ref,det,syms)
            f1=2*m['tp']/(2*m['tp']+m['fp']+m['fn']);rows.append(dict(record=rid,**m,f1=f1))
        result=dict(gap=gap,per_record=rows,macro_f1=float(np.mean([r['f1'] for r in rows])),minimum_sensitivity=min(r['sensitivity'] for r in rows))
        results.append(result);print(json.dumps(result),flush=True)
    selected=max(results,key=lambda x:(x['macro_f1'],x['minimum_sensitivity'],-x['gap']))
    report=dict(plan=manifest,results=results,selected_gap=selected['gap'],frozen_before_validation=True,
        corpus_sha256={rid:hashlib.sha256(path.read_bytes()).hexdigest() for rid,path,_,_ in corpus})
    (OUT/'development_results.json').write_text(json.dumps(report,indent=2));print('SELECTED GAP',selected['gap'])
if __name__=='__main__':main()
