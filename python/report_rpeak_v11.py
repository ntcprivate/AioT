import json
from pathlib import Path
from evaluate_v11_e2e import score
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/rpeak_optimization'
r=json.loads((OUT/'evaluation.json').read_text());folds=json.loads((ROOT/'results/v10_research/step1_5fold_cv/folds_split.json').read_text())
foldmetrics=[]
for ds in ['MITBIH','INCART']:
 for stage in ['old','candidate']:
  for k in range(5):
   groups=folds[k]['outer_MITBIH_records' if ds=='MITBIH' else 'outer_INCART_patients']
   a=[v for v in r['records'] if v['dataset']==ds and v['stage']==stage and v['model']=='V11' and v['group'] in groups]
   if not a:continue
   counts={key:sum(v[key] for v in a) for key in ['TP','FP','FN','TN','reference_N']}
   foldmetrics.append(dict(dataset=ds,stage=stage,fold=k,**score(counts['TP'],counts['FP'],counts['FN'],counts['TN'],counts['reference_N'])))
(OUT/'development_fold_metrics.json').write_text(json.dumps(foldmetrics,indent=2))
lines=['# Controlled detector confirmation experiment', '', 'No Test accessed. Firmware unchanged. Final V11 threshold 0.80; V6 threshold 0.87. Old/new share current native peak stream. New is a causal slope confirmation gate after window completion; RR recomputed from accepted peaks. Only one candidate, rejected. Training traces were used for diagnosis; final end-to-end uses original Development only, with final models selected on these Development groups, not OOF or independent evidence.', '', '| Dataset | Stage/model | Precision | Recall | F1 | TP | FP | FN | TN | Peak sensitivity | Peak PPV |', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for ds,ss in r['summary'].items():
 for key,v in ss.items():
  lines.append(f"| {ds} | {key} | {100*v['precision']:.2f}% | {100*v['recall']:.2f}% | {100*v['f1']:.2f}% | {v['TP']} | {v['FP']} | {v['FN']} | {v['TN']} | {100*v['peak_sensitivity']:.3f}% | {100*v['peak_ppv']:.3f}% |")
lines+=['', '## Evidence and limits', '', 'Across Train+Development traces, 18,775 MIT-BIH and 4,761 INCART detected matches are OTHER beats, not unmatched false peaks. Matching includes all BEATS symbols, tolerance 38 samples. There are 483/8,319 unmatched peaks; 189/4,265 lie within 75 samples of a reference. Temporal proximity is evidence of nearby mislocalization/secondary events, not proof of double detection or T/P morphology. Native detector uses absolute baseline-removed magnitude and no explicit QRS slope confirmation. The slope gate rejects many true PVCs, so low-slope candidates cannot safely be called T waves.', '', 'Unmatched peaks may include unlabeled genuine beats; they are scoring-unmatched, not adjudicated noise. Distinguishing noise/T/P requires waveform adjudication not established here. Historical 22.96% missing RR was inflated by annotation-relative completion gating, as already documented. Final Test figures were not rerun or used for tuning.', '', 'All missed V included FN; missed N separately retained in record JSON and never counted TN. Unmatched PVC predictions count FP; OTHER matches excluded from N/V labels. Ungated synthetic ADC replay is not a complete firmware safety-gate or hardware validation.', '', '## Worst available Development fold (not a new full 5-fold evaluation)']
for ds in ['MITBIH','INCART']:
 for stage in ['old','candidate']:
  a=[v for v in foldmetrics if v['dataset']==ds and v['stage']==stage];w=min(a,key=lambda v:v['f1']);lines.append(f"{ds} {stage}: fold {w['fold']}, F1 {100*w['f1']:.2f}%.")
lines+=['', '## Decision', '', 'Reject candidate: PPV improves marginally while sensitivity and PVC recall worsen. No improved detector is accepted or ready for deployment. Keep original detector and model artifacts. Current evidence does not justify further parameter search or deployment claims; morphology adjudication and separate development for QRS/T rejection are required before proposing another change.']
(OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines[-9:]))
