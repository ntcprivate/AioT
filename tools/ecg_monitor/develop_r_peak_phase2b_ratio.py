"""Train-only refinement: avoid moving a valid first QRS to a slightly larger late lobe."""
import json,subprocess
import numpy as np,wfdb
from develop_r_peak_phase2b_confirmation import ROOT,FW,OUT,RECORDS,source
from audit_r_peaks import BEATS,score,rows_from,run_native
def main():
    configs=[1.5,2.0,3.0];results=[]
    (OUT/'replacement_plan.json').write_text(json.dumps(dict(records=RECORDS,ratios=configs,selection='macro F1 on Train; tie min sensitivity, smaller ratio'),indent=2))
    corpus=[]
    for rid in RECORDS:
        ann=wfdb.rdann(str(ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid),'atr');m=np.array([s in BEATS for s in ann.symbol]);corpus.append((rid,(ann.sample[m]*25+18)//36,np.asarray(ann.symbol)[m]))
    for ratio in configs:
        proto=OUT/f'replace_{ratio}';proto.mkdir(exist_ok=True)
        h,c=source(dict(alpha=.025,factor=2.5));c=c.replace('prev_abs_>candidate_strength_',f'prev_abs_>{ratio}f*candidate_strength_')
        (proto/'signal.h').write_text(h);(proto/'signal.cpp').write_text(c);exe=proto/'detector.exe'
        subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(proto),'-I',str(FW/'tests'),str(proto/'signal.cpp'),str(FW/'tests/detector_replay.cpp'),'-o',str(exe)],check=True)
        rows=[]
        for rid,ref,syms in corpus:
            events=rows_from(run_native(exe,OUT/f'development_{rid}.bin'));m=score(ref,[int(r[1]) for r in events if r[0]=='peak'],syms);rows.append(dict(record=rid,**m,f1=2*m['tp']/(2*m['tp']+m['fp']+m['fn'])))
        result=dict(ratio=ratio,per_record=rows,macro_f1=float(np.mean([r['f1'] for r in rows])),minimum_sensitivity=min(r['sensitivity'] for r in rows));results.append(result);print(ratio,[(r['record'],r['tp'],r['fp'],r['fn']) for r in rows],result['macro_f1'],flush=True)
    selected=max(results,key=lambda r:(r['macro_f1'],r['minimum_sensitivity'],-r['ratio']))
    (OUT/'replacement_development.json').write_text(json.dumps(dict(results=results,selected_ratio=selected['ratio'],selection_uses_train_only=True,validation_reuse_disclosed=True),indent=2));print('SELECTED',selected['ratio'])
if __name__=='__main__':main()
