import json, hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'results/v10_research'
def read(p): return json.loads((root/p).read_text())
old=read('step1_5fold_cv/cv_evaluation.json')
new=read('step4_hybrid/evaluation.json')
models={m:old['models'][m]['summary'] for m in ('V4','V6')}
models['V10-A']=read('step2/evaluation.json')['V10-A']['summary']
models['V10-B']=read('step3_consistent_runtime/evaluation.json')['V10-B']['summary']
models['V10-C']=new['V10-C']['summary']
for row in new['V10-C']['folds']:
    p=root/'step4_hybrid/checkpoints'/f"v10a_fold{row['fold_index']}_best.keras"
    assert hashlib.sha256(p.read_bytes()).hexdigest()==row['checkpoint_sha256']
lines=['# V10-C Hybrid CV', '', 'Adaptive evaluation: previous outer CV results influenced this architecture. Not independent confirmation. Five checkpoint hashes verified. Only Train+Validation used.', '', '| Dataset | Model | Precision | Recall | F1 | PR-AUC (AP) | FP/1000 N | Worst F1 |','|---|---|---:|---:|---:|---:|---:|---:|']
for ds in ('MITBIH','INCART'):
    for model,summ in models.items():
        s=summ[ds]
        vals=[f"{100*s[k]['mean']:.2f} ± {100*s[k]['std']:.2f}%" for k in ('precision','recall','f1','pr_auc')]
        vals += [f"{s['fp_per_1000_normal']['mean']:.2f} ± {s['fp_per_1000_normal']['std']:.2f}",f"{100*s['worst_fold_by_f1']['f1']:.2f}% (fold {s['worst_fold_by_f1']['fold_index']})"]
        lines.append('| '+' | '.join([ds,model]+vals)+' |')
(root/'step4_hybrid/report.md').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines))
