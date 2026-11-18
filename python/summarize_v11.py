import json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1]
r=json.loads((root/'results/cnn_v11/evaluation.json').read_text())
old=json.loads((root/'results/v10_research/step1_5fold_cv/cv_evaluation.json').read_text())
lines=['# V11 CNN + causal RR', '', 'Annotation-derived RR; timing oracle, not detector end-to-end evidence. Adaptive research CV; outer groups have been inspected in previous experiments. No Test used.', '', '| Dataset | Model | Precision | Recall | F1 | AP | FP/1000 N | Worst F1 |','|---|---|---:|---:|---:|---:|---:|---:|']
for row in r['folds']:
    p=root/f"models/v11/v11_fold{row['fold_index']}_best.keras"
    assert hashlib.sha256(p.read_bytes()).hexdigest()==row['checkpoint_sha256']
for ds in ['MITBIH','INCART']:
    for name in ['V4','V6','V11']:
        s=r['summary'][ds] if name=='V11' else old['models'][name]['summary'][ds]
        vals=[f"{100*s[k]['mean']:.2f} ± {100*s[k]['std']:.2f}%" for k in ['precision','recall','f1','pr_auc']]
        vals += [f"{s['fp_per_1000_normal']['mean']:.2f} ± {s['fp_per_1000_normal']['std']:.2f}",f"{100*s['worst_fold_by_f1']['f1']:.2f}%"]
        lines.append('| '+' | '.join([ds,name]+vals)+' |')
lines += ['', '## Fixed RR perturbations', '', 'These perturbations isolate model dependence on RR; they do not simulate the full set of missed/extra detector peaks.']
for ds in ['MITBIH','INCART']:
    for kind in ['missing','jitter']:
        import numpy as np
        vals=[row['robustness'][ds][kind] for row in r['folds']]
        lines.append(f"{ds} {kind}: mean F1={100*np.mean([v['f1'] for v in vals]):.2f}%, recall={100*np.mean([v['recall'] for v in vals]):.2f}%, FP/1000 N={np.mean([v['fp_per_1000_normal'] for v in vals]):.2f}")
(root/'results/cnn_v11/report.md').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines))
