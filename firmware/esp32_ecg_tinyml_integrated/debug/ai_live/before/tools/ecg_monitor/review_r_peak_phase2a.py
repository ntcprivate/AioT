"""Same frozen Validation inputs and historical scorer; phase2A queue-only review."""
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from audit_r_peaks import ROOT,FW,TRACE,score,assignment,rows_from,run_native,reasons,dump_csv,summary_metrics

OUT=FW/'debug/r_peak_phase2a'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    phase1=json.loads((FW/'debug/r_peak_detector_audit.json').read_text(encoding='utf-8'))
    before=json.loads((OUT/'baseline_reproduced.json').read_text())
    results=[];fn_before=[];fn_after=[];by_before=defaultdict(Counter);by_after=defaultdict(Counter)
    fn_reasons_before=Counter();fn_reasons_after=Counter()
    snapshots=json.loads((FW/'debug/r_peak_phase2a_before/sha256.json').read_text())
    for old in phase1['per_record']:
        rid=old['record'];path=FW/f'debug/r_peak_audit/{rid}_adc.bin';z=np.load(FW/f'debug/r_peak_audit/{rid}_detections.npz')
        frozen=next(r for r in before['records'] if r['record']==rid)
        assert sha(path)==frozen['adc_sha256']
        for extension,digest in phase1['input_sha256'][rid].items():
            assert sha(ROOT/f'mit-bih-arrhythmia-database-1.0.0/{rid}.{extension}')==digest
        start=time.perf_counter();text=run_native(OUT/'current_audit.exe',path,OUT/f'{rid}_after_trace.bin')
        (OUT/f'{rid}_after_events.csv').write_text(text)
        rows=rows_from(text);native=rows_from((OUT/f'{rid}_before_events.csv').read_text())
        ref=z['reference'];syms=z['symbols'];det=np.array([int(r[1]) for r in rows if r[0]=='peak'],dtype=np.int64)
        gated=np.array([int(r[1]) for r in rows if r[0]=='gated_peak'],dtype=np.int64)
        previous=np.array([int(r[1]) for r in native if r[0]=='peak'],dtype=np.int64)
        metric=score(ref,det,syms);assert score(ref,previous,syms)==frozen['metrics']
        old_matches,old_fp=assignment(ref,previous);matches,fp=assignment(ref,det)
        assert np.all(np.diff(det)>0),'Duplicate/out-of-order emitted centers'
        trace=np.fromfile(OUT/f'{rid}_after_trace.bin',dtype=TRACE)
        original_trace=np.fromfile(OUT/f'{rid}_before_trace.bin',dtype=TRACE)
        # Bit16 now means benign overlap, NOT a reset. Old helper's reset classification
        # is only applied after clearing that bit; actual issue/reset rows remain unchanged.
        explanatory=trace.copy();explanatory['flags'] &= np.uint32(0xffffffef)
        new_fn=reasons(ref,matches,explanatory,det,rows)
        old_fn=reasons(ref,old_matches,original_trace,previous,native)
        for collection in (new_fn,old_fn):
            for r in collection:r.update(record=rid,label=str(syms[r['reference_index']]))
        fn_before.extend(old_fn);fn_after.extend(new_fn)
        fn_reasons_before.update(r['reason'] for r in old_fn);fn_reasons_after.update(r['reason'] for r in new_fn)
        stats={}
        keys=['samples','candidates','warmup_samples','no_peak_resets','external_resets','enqueued','completed','dropped_full','dropped_reset','duplicate','out_of_order','overwritten','high_water','pending']
        for r in rows:
            if r[0]=='stats':stats[r[1]]=dict(zip(keys,map(int,r[2:]),strict=True))
        assert stats['candidate']['completed']==len(det)
        assert stats['candidate']['enqueued']==stats['candidate']['completed']+stats['candidate']['dropped_reset']+stats['candidate']['pending']
        for label in sorted(set(syms.tolist())):
            keep=syms==label
            for group,indices in ((by_before,old_matches),(by_after,matches)):
                group[label].update(reference=int(np.sum(keep)),tp=int(np.sum(keep&(indices>=0))),fn=int(np.sum(keep&(indices<0))))
        issues=Counter(r[2] for r in rows if r[0]=='issue')
        old_issues=Counter(r[2] for r in native if r[0]=='issue')
        prefix=None
        first_reset=next((int(r[1]) for r in native if r[0]=='issue' and r[2]=='AMBIGUOUS_CLOSE_PEAKS'),len(trace))
        # Before the old first ambiguity the actual QRS arithmetic should be bit-identical.
        prefix=all(np.array_equal(trace[k][:first_reset],original_trace[k][:first_reset]) for k in ('baseline','magnitude','envelope','threshold','age','last_global'))
        assert prefix,'QRS rule changed before queue behavior diverged'
        result=dict(record=rid,reference=len(ref),before=frozen['metrics'],after=metric,quality_gated_after=score(ref,gated,syms),
            before_issues=dict(old_issues),after_issues=dict(issues),stats=stats,
            before_completed=len(previous),after_completed=len(det),overlap_enqueues=int(np.sum((trace['flags']&16)!=0)),
            fn_evidence_before=dict(Counter(r['reason'] for r in old_fn)),fn_evidence_after=dict(Counter(r['reason'] for r in new_fn)),
            before_warmup_samples=int(np.sum(original_trace['age']<500)),after_warmup_samples=int(np.sum(trace['age']<500)),
            duplicate_emitted=int(np.sum(np.diff(det)==0)),out_of_order_emitted=int(np.sum(np.diff(det)<0)),
            fp_before_exact_samples=previous[old_fp].tolist(),fp_after_exact_samples=det[fp].tolist(),
            recovered_reference=int(np.sum((old_matches<0)&(matches>=0))),lost_reference=int(np.sum((old_matches>=0)&(matches<0))),
            recovered_reference_by_label=dict(Counter(syms[(old_matches<0)&(matches>=0)].tolist())),
            lost_reference_by_label=dict(Counter(syms[(old_matches>=0)&(matches<0)].tolist())),
            qrs_arithmetic_identical_before_first_conflict=prefix,elapsed_host_seconds=time.perf_counter()-start,
            adc_sha256=sha(path))
        results.append(result)
        np.savez_compressed(OUT/f'{rid}_after_detections.npz',reference=ref,symbols=syms,detected=det,gated=gated,matches=matches,fp_indices=fp)
        print(rid,metric['tp'],metric['fp'],metric['fn'],metric['sensitivity'],metric['ppv'],stats['candidate'],flush=True)
    for group in (by_before,by_after):
        for v in group.values():v['sensitivity']=v['tp']/v['reference']
    aggregate=summary_metrics([r['after'] for r in results]);b=phase1['baseline']
    criteria=phase1['criteria']
    passes={r['record']:r['after']['sensitivity']>=.99 and r['after']['ppv']>=.99 and r['after']['timing_p95_abs_ms']<=40 for r in results}
    controls={}
    for name in ('no_peaks','pure50Hz'):
        rows=rows_from(run_native(OUT/'current_audit.exe',FW/f'debug/r_peak_audit/{name}.bin',OUT/f'{name}_after_trace.bin'))
        controls[name]=dict(candidate_peaks=sum(r[0]=='peak' for r in rows),gated_peaks=sum(r[0]=='gated_peak' for r in rows))
    allowed={str((FW/'main/signal.h').relative_to(ROOT)),str((FW/'main/signal.cpp').relative_to(ROOT))}
    preserved={p:sha(ROOT/p)==digest for p,digest in snapshots.items() if p not in allowed}
    assert all(preserved.values()),[p for p,v in preserved.items() if not v]
    report=dict(status='QUEUE_FUNCTIONAL_CHECKS_PASS_DETECTOR_VALIDATION_FAIL_AI_LIVE_LOCKED',records=phase1['records'],criteria=criteria,
        baseline=b,after=aggregate,by_annotation_before={k:dict(v) for k,v in by_before.items()},by_annotation_after={k:dict(v) for k,v in by_after.items()},
        per_record=results,record_pass=passes,controls=controls,all_detector_criteria_pass=all(passes.values()) and all(c['candidate_peaks']==0 for c in controls.values()),
        fn_evidence_before=dict(fn_reasons_before),fn_evidence_after=dict(fn_reasons_after),
        protected_checks=preserved,changed_sources=[str(p.relative_to(ROOT)) for p in (FW/'main/signal.h',FW/'main/signal.cpp')],
        input_split_sha256=sha(ROOT/'data/processed/mitbih_split_indices.npz'),
        sampling_algorithm_changed=False,qrs_rule_tuned=False,cnn_changed=False,telemetry_changed=False,ai_live_unlocked=False,com_opened=False,flashed=False,
        limitations=['Validation reused; no Test, patient-independent final claim or hardware validation',
            'Old/new same candidate rule; persistent state differs because overlap no longer resets it',
            'FP increased and failing records retained; no threshold/refractory/filter retuning in2A',
            'Timing and data checks cover raw windows; host gated mirror is not full RTOS/generation simulation'])
    dump_csv(OUT/'false_negatives_before.csv',fn_before);dump_csv(OUT/'false_negatives_after.csv',fn_after)
    (OUT/'metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(before=b,after=aggregate,reasons=report['fn_evidence_after']),indent=2))

if __name__=='__main__':main()
