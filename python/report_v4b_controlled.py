import json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v4/v4b_hard_example_training';STEP=ROOT/'results/v10_research/step1_5fold_cv'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def agg(a):
 keys=['TP','FP','FN','TN','N','V','missingN','missingV','FP_matched_N','FP_unmatched_alarm'];r={k:sum(int(v[k]) for v in a) for k in keys};p=r['TP']/(r['TP']+r['FP']) if r['TP']+r['FP'] else 0;rec=r['TP']/(r['TP']+r['FN']) if r['TP']+r['FN'] else 0;r.update(precision=p,recall=rec,f1=2*p*rec/(p+rec) if p+rec else 0,fp_per_1000_N=1000*r['FP']/r['N'] if r['N'] else 0);return r
def main():
 r=read(OUT/'evaluation.json');old=read(STEP/'cv_evaluation.json');checks=[];groups=[]
 mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');split=np.load(ROOT/'data/processed/mitbih_split_indices.npz');inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');mi=np.concatenate([split['train_indices'],split['validation_indices']]);ii=np.flatnonzero(np.isin(inc['split'],['train','validation']));g=np.concatenate([mit['record_ids'][mi].astype(str),inc['patient_ids'][ii].astype(str)]);d=np.array(['MITBIH']*len(mi)+['INCART']*len(ii));specs=read(STEP/'folds_split.json')
 for fold in r['folds']:
  k=fold['fold_index'];assert sha(OUT/f'checkpoints/v4b_fold{k}_best.keras')==fold['v4b_sha256'];spec=specs[k];fit=((d=='MITBIH')&np.isin(g,spec['fit_MITBIH_records']))|((d=='INCART')&np.isin(g,spec['fit_INCART_patients']));mine=np.load(OUT/f'fold{k}_Fit_mining.npz');np.testing.assert_array_equal(mine['global_indices'],np.flatnonzero(fit))
  for label in [0,1]:assert np.isclose(mine['weights'][mine['labels']==label].sum(),len(mine['labels'])/2,rtol=1e-5)
  orig=next(x for x in old['models']['V4']['folds'] if x['fold_index']==k)
  for ds in ['MITBIH','INCART']:
   for key in ['TP','FP','FN','TN']:assert fold['CNN_only']['V4'][ds][key]==orig[ds][key],(k,ds,key)
  checks.append(dict(fold=k,baseline_counts_reproduced=True,hash_verified=True,mining_Fit_only=True,within_class_weight_totals_preserved=True))
 for ds in ['MITBIH','INCART']:
  for fold in r['folds']:
   for name in ['V4','V4-B']:
    rows=[x for x in fold['end_to_end'][name] if x['dataset']==ds]
    for group in sorted(set(x['group'] for x in rows)):
     a=[x for x in rows if x['group']==group];groups.append(dict(dataset=ds,fold=fold['fold_index'],model=name,group=group,records=[x['record'] for x in a],**agg(a)))
 outcome={};passing=[]
 for ds in ['MITBIH','INCART']:
  a=r['summary']['end_to_end'][ds]['V4'];b=r['summary']['end_to_end'][ds]['V4-B'];paired=[]
  for x in [v for v in groups if v['dataset']==ds and v['model']=='V4' and v['V']>0]:
   y=next(v for v in groups if v['dataset']==ds and v['model']=='V4-B' and v['group']==x['group']);paired.append(y['f1']-x['f1'])
  p={'mean_f1_noninferior':b['mean']['f1']>=a['mean']['f1'],'recall_rule':b['mean']['recall']>a['mean']['recall'] if ds=='INCART' else b['mean']['recall']>=a['mean']['recall']-.01,'FP_rule':b['mean']['fp_per_1000_N']<=a['mean']['fp_per_1000_N']+max(1,.1*a['mean']['fp_per_1000_N']),'worst_fold_rule':b['worst_fold_f1']>=a['worst_fold_f1'],'group_stability_fraction':sum(v>=-.02 for v in paired)/len(paired),'groups_improved':sum(v>1e-12 for v in paired),'groups_worsened':sum(v< -1e-12 for v in paired),'groups_with_PVC':len(paired)};p['group_stability_rule']=p['group_stability_fraction']>=.6;outcome[ds]=p;passing.extend([p[key] for key in ['mean_f1_noninferior','recall_rule','FP_rule','worst_fold_rule','group_stability_rule']])
 decision={'status':'PASS' if all(passing) else 'FAIL','criteria':outcome,'recommendation':'keep original V4; no Test evaluation or extra variants' if not all(passing) else 'promising research candidate; no deployment/generalization claim and no automatic Test','baseline_reuse':'exact old CNN-only confusion counts reproduced in all5 folds, supporting same splits/calibration; historical training runtime not fully recorded'}
 (OUT/'verification.json').write_text(json.dumps(checks,indent=2));(OUT/'group_metrics.json').write_text(json.dumps(groups,indent=2));(OUT/'decision.json').write_text(json.dumps(decision,indent=2))
 lines=['# V4-B controlled hard-example training','','Decision: **'+decision['status']+'**. '+decision['recommendation']+'.','','## Protocol and isolation','','Original V4 model/checkpoint/threshold0.88 untouched. One V4-B configuration: identical849-parameter ECG-only architecture, no RR. Fit-only baseline scoring ranks hardest10% per class;2x difficulty weights normalized within class, then original class weight. Hard cases carry ~18.18% effective class weight, preserving ordinary cases. No focal loss or augmentation; one joint hardness factor, so positive and negative contributions cannot be causally separated. Fit scores are in-sample mining signals, never OOF claims.','','Same5 locked group folds, seed42+1000*k, BCE,Adam.001,batch128,max20,patience5. Baseline Step1 V4 checkpoints reused rather than retrained; all old baseline CNN-only confusion counts and calibration thresholds reproduced exactly. Historical runtime not completely logged. Checkpoint maxPR-AUC on Checkpoint groups; threshold maxF1 on disjoint Calibration, .05.. .95 by.01, tie precision then smaller threshold. No fixed0.88 assumption for newly trained fold models. All outer Evaluation groups disjoint from Fit/Checkpoint/Calibration per fold; INC groups patient, MIT record proxies not proven unique patients. Earlier research examined these groups; adaptive internal CV, not new independent evidence.','','V4-B initialized from scratch with same seed, not fine-tuned baseline. Learned hardness is one controlled change. Mining metadata/global indices and weights retained for audit.5 models only; no post-result extra variants.','','## CNN-only (annotation-centered, mean fold metrics)','', '| Dataset | Model | Precision | Recall | F1 ± SD | Worst fold F1 |','|---|---|---:|---:|---:|---:|']
 for ds in ['MITBIH','INCART']:
  for name in ['V4','V4-B']:
   x=r['summary']['CNN_only'][ds][name];m=x['mean'];lines.append(f"| {ds} | {name} | {100*m['precision']:.3f}% | {100*m['recall']:.3f}% | {100*m['f1']:.3f} ± {100*x['std_f1']:.3f}% | {100*x['worst_fold_f1']:.3f}% |")
 lines+=['','## Detector-centered end-to-end (mean folds)','', '| Dataset | Model | Precision | Recall | F1 ± SD | FP/1000 N | Worst fold F1 |','|---|---|---:|---:|---:|---:|---:|---:|']
 for ds in ['MITBIH','INCART']:
  for name in ['V4','V4-B']:
   x=r['summary']['end_to_end'][ds][name];m=x['mean'];lines.append(f"| {ds} | {name} | {100*m['precision']:.3f}% | {100*m['recall']:.3f}% | {100*m['f1']:.3f} ± {100*x['std_f1']:.3f}% | {m['fp_per_1000_N']:.3f} | {100*x['worst_fold_f1']:.3f}% |")
 lines+=['','## Pooled end-to-end counts across outer folds','', '| Dataset | Model | TP | FP | FN | TN | Precision | Recall | F1 | FP/1000 N |','|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
 for ds in ['MITBIH','INCART']:
  for name in ['V4','V4-B']:
   a=[x for f in r['folds'] for x in f['end_to_end'][name] if x['dataset']==ds];m=agg(a);lines.append(f"| {ds} | {name} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} | {100*m['precision']:.3f}% | {100*m['recall']:.3f}% | {100*m['f1']:.3f}% | {m['fp_per_1000_N']:.3f} |")
 lines+=['','Native detector peaks/windows reused unchanged: same synthetic ADC,250Hz,256 samples,float32 zscore; no QRS gate. Matching greedy one-to-one +/-38samples with all BEATS references. MissingV=FN, missingN abstention not TN; unmatched PVC alarms=FP, matched OTHER not relabeled N. Ungated stream, not complete firmware quality gates. No Test data or Test hard examples.','', '## Fold checkpoint/threshold/mining log','', '| Fold | V4 threshold | V4-B threshold | B best epoch/run | Hard N / Fit N | Hard V / Fit V |','|---|---:|---:|---|---|---|']
 for f in r['folds']:
  t=f['training'];mi=t['mining'];lines.append(f"| {f['fold_index']} | {f['thresholds']['V4']} | {f['thresholds']['V4-B']} | {t['best_epoch']}/{t['epochs_run']} | {mi['0']['hard_samples']}/{mi['0']['Fit_samples']} | {mi['1']['hard_samples']}/{mi['1']['Fit_samples']} |")
 lines+=['','## Acceptance criteria and stability','',json.dumps(decision,indent=2),'','## ESP32 feasibility','','Architecture/operator family remains original V4: Conv1D/ReLU,MaxPool,GAP,Dense/sigmoid; expected TFLM lowering Conv2D,ExpandDims,Reshape,MaxPool2D,Mean,FullyConnected,Logistic as existing V4. No new runtime feature/history or custom loss operator. Raw FP32 parameter payload3396bytes; input1024bytes; largest early Conv activation8064bytes FP32. These are logical sizes, not measured arena/Flash. Keras archive includes metadata/optimizer; compiled storage, Tensor Arena, stack/latency require actual conversion/build/board measurement. No INT8 conversion, firmware change, flash or deployment claims.','', '## Per-record/patient end-to-end','', '| Dataset | Fold | Record | Group | Model | Precision | Recall | F1 | TP | FP | FN |','|---|---|---|---|---|---:|---:|---:|---:|---:|---:|']
 for f in r['folds']:
  for name in ['V4','V4-B']:
   for x in f['end_to_end'][name]:
    m=agg([x]);lines.append(f"| {x['dataset']} | {f['fold_index']} | {x['record']} | {x['group']} | {name} | {100*m['precision']:.2f}% | {100*m['recall']:.2f}% | {100*m['f1']:.2f}% | {m['TP']} | {m['FP']} | {m['FN']} |")
 lines+=['','Full patient-group aggregation is in group_metrics.json. Group F1 with no referencePVC is not a meaningful sensitivity estimate; acceptance group criterion includes only groups containingPVC. CNN-only counts/FP1000N per fold are retained in evaluation.json. No global final V4-B is trained or selected from outer results. Stop after this report.']
 (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8');print(json.dumps({'decision':decision,'end_to_end_mean':{ds:{m:x['mean'] for m,x in ms.items()} for ds,ms in r['summary']['end_to_end'].items()}},indent=2))
if __name__=='__main__':main()
