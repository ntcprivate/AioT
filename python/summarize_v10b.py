import json
from pathlib import Path
from run_v10_step2_v10a import sha256_file

root = Path(__file__).resolve().parents[1] / 'results/v10_research'
dest = root / 'step3_consistent_runtime'
b = json.loads((dest / 'evaluation.json').read_text())
a = json.loads((root / 'step2/evaluation.json').read_text())
models = {'V6': b['V6_step1'], 'V10-A': a['V10-A']['summary'], 'V10-B': b['V10-B']['summary']}
for row in b['V10-B']['folds']:
    p = dest / 'checkpoints' / f"v10a_fold{row['fold_index']}_best.keras"
    assert sha256_file(p) == row['checkpoint_sha256']
splits = json.loads((root / 'step1_5fold_cv/folds_split.json').read_text())
for fold in splits:
    for dataset in ('MITBIH_records', 'INCART_patients'):
        groups = [set(fold[f'{role}_{dataset}']) for role in ('fit', 'checkpoint', 'threshold', 'outer')]
        assert all(not groups[i] & groups[j] for i in range(4) for j in range(i+1,4))
lines = ['# V10-B Dual-Scale Normalization', '', 'All five checkpoint hashes and all group-role intersections verified. Runtime: see runtime.json. Outer results were previously inspected to motivate this experiment; adaptive evaluation, not independent confirmation.', '', '| Dataset | Model | Precision | Recall | F1 | PR-AUC (AP) | FP/1000 N | Worst fold F1 |', '|---|---|---:|---:|---:|---:|---:|---:|']
for ds in ('MITBIH', 'INCART'):
    for name, summary in models.items():
        s = summary[ds]
        cells = [f"{100*s[k]['mean']:.2f} ± {100*s[k]['std']:.2f}%" for k in ('precision','recall','f1','pr_auc')]
        cells += [f"{s['fp_per_1000_normal']['mean']:.2f} ± {s['fp_per_1000_normal']['std']:.2f}", f"{100*s['worst_fold_by_f1']['f1']:.2f}% (fold {s['worst_fold_by_f1']['fold_index']})"]
        lines.append('| ' + ' | '.join([ds,name]+cells) + ' |')
(dest / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(lines))
