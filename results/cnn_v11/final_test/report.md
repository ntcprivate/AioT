# V11 final FP32 retrospective Test

One final V11 was trained with seed 42, 20-epoch cap, early stopping patience 5,
Adam 0.001, BCE, Fit class weights, no augmentation. Fit used original Train;
checkpoint and calibration used the saved disjoint V6 Development groups.
Best epoch 5, stopped at epoch 10. No Test accessed for checkpoint or threshold.

Threshold: 0.80. Model SHA-256:
61909ec7f93e3d8823627a0127422aefdd098f92a9c95619073968c7a3eb3601

Model, RR scaling and preprocessing were frozen in locked.json before Test.
Each record has separate offline and detector score files. No old-model
inference was rerun; V4/V6 values below come from
results/cnn_v6/main_dataset_comparison/report.md. Tests had already informed
earlier research, so all comparisons here are retrospective, not independent.

## Offline: annotation-centered windows and annotation RR

| Dataset | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MIT-BIH | V4 | 96.06% | 69.82% | 89.72% | 78.53% | 812 | 351 | 93 | 10023 |
| MIT-BIH | V6 | 92.95% | 53.66% | 89.17% | 67.00% | 807 | 697 | 98 | 9677 |
| MIT-BIH | V11 | 97.98% | 82.96% | 94.14% | 88.20% | 852 | 175 | 53 | 10199 |
| INCART | V4 | 95.68% | 86.55% | 77.85% | 81.97% | 2594 | 403 | 738 | 22678 |
| INCART | V6 | 96.71% | 87.03% | 86.82% | 86.93% | 2893 | 431 | 439 | 22650 |
| INCART | V11 | 98.35% | 98.92% | 87.88% | 93.07% | 2928 | 32 | 404 | 23049 |

Same retained N/V windows as prior models. V11 has extra reference timing
information; this is an offline oracle-RR comparison, not deployment accuracy.

## Detector windows and detector RR

| Dataset | Ledger accuracy | Precision | Recall | F1 | TP | FP | FN | TN | FP/1000 reference N |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MIT-BIH | 80.38% | 24.96% | 90.06% | 39.09% | 815 | 2450 | 90 | 9592 | 236.17 |
| INCART | 86.73% | 45.41% | 82.84% | 58.67% | 2762 | 3320 | 572 | 22682 | 143.84 |

All missed PVC count FN. Missing Normal beats remain abstentions, not TN.
PVC predictions on unmatched peaks count FP; OTHER matches are excluded, never
converted to N. Consequently ledger accuracy=(TP+TN)/(TP+FP+FN+TN) includes
extra detected events but excludes missing N and is not a conventional fixed
reference binary accuracy. N/V reference counts also include boundary beats
not retained in offline extraction (INCART V=3334 versus offline 3332).

Detector missed 688 N/56 V on MIT-BIH, with 2955 unmatched peaks; INCART missed
361 N/366 V, with 3443 unmatched peaks. These are host replay results using
current existing detector executable, synthetic ADC mapping 2048+200 counts/mV,
one-to-one 38-sample matching, and ungated windows. Full firmware quality gates
and hardware performance are not evaluated. No annotation RR or following
detector peak is used in detector-model inputs.

## Decision

V11 exceeds V4 and V6 offline F1 on both sources but detector-window performance
does not support final deployment selection. The large number of extra detector
events and RR/window mismatch must be resolved and validated independently.
Keep V11 as a promising research candidate, not a locked deployment winner.
No tuning, retraining, or V12 work followed Test.
