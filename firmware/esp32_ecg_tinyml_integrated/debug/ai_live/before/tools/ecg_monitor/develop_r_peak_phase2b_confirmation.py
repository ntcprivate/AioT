"""Second development-only trial after curvature localization regressed Train records.
No Validation run or Test tuning; freeze the selected configuration before final review.
"""
import json,subprocess
import numpy as np
import wfdb
from develop_r_peak_phase2b import ROOT,FW,OUT,BEFORE,RECORDS
from audit_r_peaks import BEATS,score,rows_from,run_native
CONFIGS=[dict(name='hold_only',alpha=.01,factor=2.5),dict(name='fast_baseline',alpha=.025,factor=2.5),dict(name='fast_lower_envelope',alpha=.025,factor=2.0)]
def source(config):
    h=(BEFORE/'main/signal.h').read_text().replace('    BeatWindowStats windows={};','    BeatWindowStats windows={};\n    uint64_t no_peak_events=0;')
    h=h.replace('    float baseline_ = 0, envelope_ = 0, prev_abs_ = 0, before_abs_ = 0;',
        '    float baseline_=0,envelope_=0,prev_abs_=0,before_abs_=0;\n    float candidate_strength_=0;\n    int64_t candidate_start_=0,candidate_center_=0,last_timestamp_=0;\n    uint64_t no_peak_events_=0;\n    bool candidate_active_=false,no_peak_reported_=false;')
    c=(BEFORE/'main/signal.cpp').read_text();c=c[:c.index('bool BeatDetector::push(')]
    c=c.replace('    baseline_=envelope_=prev_abs_=before_abs_=0;','    baseline_=envelope_=prev_abs_=before_abs_=0;\n    candidate_active_=false;last_timestamp_=0;no_peak_reported_=false;')
    c=c.replace('counters_.no_peak_resets,counters_.external_resets,windows_.stats()};','counters_.no_peak_resets,counters_.external_resets,windows_.stats(),no_peak_events_};')
    c+='''bool BeatDetector::push(int raw,int64_t timestamp,float* beat,const char*& issue) {
    issue=nullptr;const int64_t sample=next_sample_++;const int64_t current=count_++;
    ++counters_.samples;if(current<500)++counters_.warmup_samples;
    if(raw<0 || raw>4095 || timestamp<0) {issue="INVALID_ADC_SAMPLE";reset_state();return false;}
    if(current>0 && (timestamp-last_timestamp_<2000 || timestamp-last_timestamp_>6000)) {
        issue="BEAT_TIMING_GAP";reset_state();return false;
    }
    last_timestamp_=timestamp;
    if(!windows_.append(raw,sample,timestamp,issue)) {reset_state();return false;}
    if(current==0)baseline_=raw;
    baseline_+=ALPHAf*(raw-baseline_);
    const float magnitude=std::abs(raw-baseline_);
    envelope_+=0.01f*(magnitude-envelope_);
    const float threshold=std::max(static_cast<float>(CONFIG_ECG_QRS_MIN_COUNTS),FACTORf*envelope_);
    if(current>=500 && prev_abs_>before_abs_ && prev_abs_>=magnitude && prev_abs_>threshold) {
        const int64_t center=sample-1;
        if(last_center_<0 || center-last_center_>=75) {
            if(!candidate_active_) {candidate_active_=true;candidate_start_=sample;candidate_center_=center;candidate_strength_=prev_abs_;}
            else if(prev_abs_>candidate_strength_) {candidate_center_=center;candidate_strength_=prev_abs_;}
        }
    }
    before_abs_=prev_abs_;prev_abs_=magnitude;
    if(candidate_active_ && sample-candidate_start_>=50) {
        candidate_active_=false;++counters_.candidates;last_center_=candidate_center_;no_peak_reported_=false;
        if(!windows_.enqueue(candidate_center_,issue))return false;
    }
    if(windows_.pop_ready(beat,last_window_,issue))return true;
    if(issue) {reset_state();return false;}
    if(current>1000 && (last_center_<0 || sample-last_center_>500) && !no_peak_reported_) {
        issue="NO_RELIABLE_R_PEAK";no_peak_reported_=true;++no_peak_events_;
    }
    return false;
}
'''.replace('ALPHA',str(config['alpha'])).replace('FACTOR',str(config['factor']))
    return h,c
def main():
    plan=dict(records=RECORDS,candidates=CONFIGS,hold_samples=50,selection='macro F1 on Train; tie min sensitivity, then declaration order',
        reason='Curvature trial rejected on development due major localization FP/FN; preserve original magnitude fiducial and confirm a stronger peak within200ms')
    (OUT/'confirmation_plan.json').write_text(json.dumps(plan,indent=2))
    corpus=[]
    for rid in RECORDS:
        a=wfdb.rdann(str(ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid),'atr');m=np.array([s in BEATS for s in a.symbol]);corpus.append((rid,(a.sample[m]*25+18)//36,np.asarray(a.symbol)[m]))
    results=[]
    for config in CONFIGS:
        proto=OUT/config['name'];proto.mkdir(exist_ok=True);h,c=source(config);(proto/'signal.h').write_text(h);(proto/'signal.cpp').write_text(c)
        exe=proto/'detector.exe';subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(proto),'-I',str(FW/'tests'),str(proto/'signal.cpp'),str(FW/'tests/detector_replay.cpp'),'-o',str(exe)],check=True)
        rows=[]
        for rid,ref,syms in corpus:
            events=rows_from(run_native(exe,OUT/f'development_{rid}.bin'));m=score(ref,[int(r[1]) for r in events if r[0]=='peak'],syms);rows.append(dict(record=rid,**m,f1=2*m['tp']/(2*m['tp']+m['fp']+m['fn'])))
        result=dict(config=config,per_record=rows,macro_f1=float(np.mean([r['f1'] for r in rows])),minimum_sensitivity=min(r['sensitivity'] for r in rows));results.append(result)
        print(config['name'],[(r['record'],r['tp'],r['fp'],r['fn']) for r in rows],result['macro_f1'],flush=True)
    best=max(results,key=lambda r:(r['macro_f1'],r['minimum_sensitivity']))
    (OUT/'confirmation_development.json').write_text(json.dumps(dict(plan=plan,results=results,selected=best['config'],frozen_before_validation=True),indent=2));print('SELECTED',best['config'])
if __name__=='__main__':main()
