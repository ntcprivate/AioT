# V4-B controlled hard-example training

Decision: **FAIL**. keep original V4; no Test evaluation or extra variants.

## Protocol and isolation

Original V4 model/checkpoint/threshold0.88 untouched. One V4-B configuration: identical849-parameter ECG-only architecture, no RR. Fit-only baseline scoring ranks hardest10% per class;2x difficulty weights normalized within class, then original class weight. Hard cases carry ~18.18% effective class weight, preserving ordinary cases. No focal loss or augmentation; one joint hardness factor, so positive and negative contributions cannot be causally separated. Fit scores are in-sample mining signals, never OOF claims.

Same5 locked group folds, seed42+1000*k, BCE,Adam.001,batch128,max20,patience5. Baseline Step1 V4 checkpoints reused rather than retrained; all old baseline CNN-only confusion counts and calibration thresholds reproduced exactly. Historical runtime not completely logged. Checkpoint maxPR-AUC on Checkpoint groups; threshold maxF1 on disjoint Calibration, .05.. .95 by.01, tie precision then smaller threshold. No fixed0.88 assumption for newly trained fold models. All outer Evaluation groups disjoint from Fit/Checkpoint/Calibration per fold; INC groups patient, MIT record proxies not proven unique patients. Earlier research examined these groups; adaptive internal CV, not new independent evidence.

V4-B initialized from scratch with same seed, not fine-tuned baseline. Learned hardness is one controlled change. Mining metadata/global indices and weights retained for audit.5 models only; no post-result extra variants.

## CNN-only (annotation-centered, mean fold metrics)

| Dataset | Model | Precision | Recall | F1 ± SD | Worst fold F1 |
|---|---|---:|---:|---:|---:|
| MITBIH | V4 | 72.998% | 78.034% | 74.410 ± 13.861% | 53.695% |
| MITBIH | V4-B | 64.786% | 77.690% | 68.644 ± 12.298% | 51.599% |
| INCART | V4 | 85.549% | 68.925% | 72.415 ± 21.749% | 32.106% |
| INCART | V4-B | 78.173% | 70.124% | 69.415 ± 20.924% | 30.629% |

## Detector-centered end-to-end (mean folds)

| Dataset | Model | Precision | Recall | F1 ± SD | FP/1000 N | Worst fold F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| MITBIH | V4 | 72.523% | 76.741% | 73.511 ± 13.592% | 29.204 | 53.031% |
| MITBIH | V4-B | 64.564% | 76.354% | 67.802 ± 12.277% | 44.535 | 51.183% |
| INCART | V4 | 82.199% | 67.288% | 69.242 ± 23.828% | 22.200 | 27.403% |
| INCART | V4-B | 76.023% | 68.535% | 66.520 ± 22.310% | 32.862 | 26.303% |

## Pooled end-to-end counts across outer folds

| Dataset | Model | TP | FP | FN | TN | Precision | Recall | F1 | FP/1000 N |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | V4 | 4780 | 1902 | 1439 | 62226 | 71.535% | 76.861% | 74.103% | 29.530 |
| MITBIH | V4-B | 4760 | 2928 | 1459 | 61210 | 61.915% | 76.540% | 68.455% | 45.460 |
| INCART | V4 | 10978 | 2784 | 5701 | 121938 | 79.770% | 65.819% | 72.126% | 21.867 |
| INCART | V4-B | 11190 | 4221 | 5489 | 120575 | 72.610% | 67.090% | 69.741% | 33.153 |

Native detector peaks/windows reused unchanged: same synthetic ADC,250Hz,256 samples,float32 zscore; no QRS gate. Matching greedy one-to-one +/-38samples with all BEATS references. MissingV=FN, missingN abstention not TN; unmatched PVC alarms=FP, matched OTHER not relabeled N. Ungated stream, not complete firmware quality gates. No Test data or Test hard examples.

## Fold checkpoint/threshold/mining log

| Fold | V4 threshold | V4-B threshold | B best epoch/run | Hard N / Fit N | Hard V / Fit V |
|---|---:|---:|---|---|---|
| 0 | 0.83 | 0.79 | 2/7 | 7479/74783 | 921/9204 |
| 1 | 0.86 | 0.76 | 3/8 | 7361/73607 | 972/9713 |
| 2 | 0.72 | 0.46 | 3/8 | 7976/79756 | 957/9565 |
| 3 | 0.86 | 0.64 | 15/20 | 7960/79598 | 873/8727 |
| 4 | 0.91 | 0.88 | 12/17 | 7550/75500 | 858/8573 |

## Acceptance criteria and stability

{
  "status": "FAIL",
  "criteria": {
    "MITBIH": {
      "mean_f1_noninferior": false,
      "recall_rule": true,
      "FP_rule": false,
      "worst_fold_rule": false,
      "group_stability_fraction": 0.7419354838709677,
      "groups_improved": 13,
      "groups_worsened": 13,
      "groups_with_PVC": 31,
      "group_stability_rule": true
    },
    "INCART": {
      "mean_f1_noninferior": false,
      "recall_rule": true,
      "FP_rule": false,
      "worst_fold_rule": false,
      "group_stability_fraction": 0.7777777777777778,
      "groups_improved": 8,
      "groups_worsened": 13,
      "groups_with_PVC": 27,
      "group_stability_rule": true
    }
  },
  "recommendation": "keep original V4; no Test evaluation or extra variants",
  "baseline_reuse": "exact old CNN-only confusion counts reproduced in all5 folds, supporting same splits/calibration; historical training runtime not fully recorded"
}

## Interpretation and stopping decision

Mean end-to-end Recall changes: MIT-BIH -0.387 percentage points; INCART +1.247
points. Mean F1 decreases5.709 and2.723 points respectively. Pooled FP increases
1902→2928 on MIT-BIH and2784→4221 on INCART. More PVCs are recovered on INCART,
but at a disproportionate false-alarm cost. This single difficulty-reweighting
configuration fails the prespecified F1/FP and worst-fold criteria.

Record/patient stability is not established: among groups containingPVC,
13/31 MIT groups worsen and13/27 INC patients worsen. Worst end-to-end fold is
MIT fold1 (F1 53.031%→51.183%) and INC fold4 (27.403%→26.303%). The accepted
group-tolerance subcriterion alone does not override failed overall criteria.
Do not claim significance or new independent generalization from five adaptive
folds. Some calibration thresholds decrease substantially; the observed tradeoff
reflects the complete frozen selection procedure, not an isolated causal claim
about hard-positive versus hard-negative weighting. No second loss/augmentation
variant is attempted after this failure. Keep original V4 and stop here.

## ESP32 feasibility

Architecture/operator family remains original V4: Conv1D/ReLU,MaxPool,GAP,Dense/sigmoid; expected TFLM lowering Conv2D,ExpandDims,Reshape,MaxPool2D,Mean,FullyConnected,Logistic as existing V4. No new runtime feature/history or custom loss operator. Raw FP32 parameter payload3396bytes; input1024bytes; largest early Conv activation8064bytes FP32. These are logical sizes, not measured arena/Flash. Keras archive includes metadata/optimizer; compiled storage, Tensor Arena, stack/latency require actual conversion/build/board measurement. No INT8 conversion, firmware change, flash or deployment claims.

## Per-record/patient end-to-end

| Dataset | Fold | Record | Group | Model | Precision | Recall | F1 | TP | FP | FN |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| INCART | 0 | I01 | 1 | V4 | 9.59% | 4.07% | 5.71% | 14 | 132 | 330 |
| INCART | 0 | I02 | 1 | V4 | 7.69% | 1.75% | 2.85% | 4 | 48 | 225 |
| INCART | 0 | I12 | 6 | V4 | 50.00% | 33.33% | 40.00% | 2 | 2 | 4 |
| INCART | 0 | I13 | 6 | V4 | 100.00% | 99.57% | 99.78% | 229 | 0 | 1 |
| INCART | 0 | I14 | 6 | V4 | 96.97% | 100.00% | 98.46% | 64 | 2 | 0 |
| INCART | 0 | I16 | 8 | V4 | 0.00% | 0.00% | 0.00% | 0 | 1117 | 2 |
| INCART | 0 | I17 | 8 | V4 | 0.00% | 0.00% | 0.00% | 0 | 20 | 27 |
| INCART | 0 | I27 | 13 | V4 | 96.45% | 98.19% | 97.32% | 707 | 26 | 13 |
| INCART | 0 | I28 | 13 | V4 | 28.57% | 100.00% | 44.44% | 4 | 10 | 0 |
| INCART | 0 | I65 | 28 | V4 | 81.67% | 12.83% | 22.17% | 49 | 11 | 333 |
| INCART | 0 | I66 | 28 | V4 | 68.52% | 18.50% | 29.13% | 37 | 17 | 163 |
| INCART | 0 | I67 | 28 | V4 | 87.50% | 9.23% | 16.70% | 49 | 7 | 482 |
| INCART | 0 | I74 | 32 | V4 | 94.66% | 97.08% | 95.86% | 266 | 15 | 8 |
| INCART | 0 | I75 | 32 | V4 | 99.84% | 99.84% | 99.84% | 612 | 1 | 1 |
| MITBIH | 0 | 111 | 111 | V4 | 50.00% | 100.00% | 66.67% | 1 | 1 | 0 |
| MITBIH | 0 | 112 | 112 | V4 | 0.00% | 0.00% | 0.00% | 0 | 2 | 0 |
| MITBIH | 0 | 116 | 116 | V4 | 93.81% | 97.25% | 95.50% | 106 | 7 | 3 |
| MITBIH | 0 | 124 | 124 | V4 | 100.00% | 87.23% | 93.18% | 41 | 0 | 6 |
| MITBIH | 0 | 202 | 202 | V4 | 11.05% | 100.00% | 19.90% | 19 | 153 | 0 |
| MITBIH | 0 | 208 | 208 | V4 | 98.31% | 94.05% | 96.14% | 933 | 16 | 59 |
| MITBIH | 0 | 215 | 215 | V4 | 100.00% | 22.56% | 36.82% | 37 | 0 | 127 |
| MITBIH | 0 | 231 | 231 | V4 | 100.00% | 100.00% | 100.00% | 2 | 0 | 0 |
| INCART | 0 | I01 | 1 | V4-B | 9.68% | 4.36% | 6.01% | 15 | 140 | 329 |
| INCART | 0 | I02 | 1 | V4-B | 4.08% | 0.87% | 1.44% | 2 | 47 | 227 |
| INCART | 0 | I12 | 6 | V4-B | 50.00% | 16.67% | 25.00% | 1 | 1 | 5 |
| INCART | 0 | I13 | 6 | V4-B | 100.00% | 99.57% | 99.78% | 229 | 0 | 1 |
| INCART | 0 | I14 | 6 | V4-B | 96.97% | 100.00% | 98.46% | 64 | 2 | 0 |
| INCART | 0 | I16 | 8 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 1082 | 2 |
| INCART | 0 | I17 | 8 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 10 | 27 |
| INCART | 0 | I27 | 13 | V4-B | 75.45% | 99.03% | 85.65% | 713 | 232 | 7 |
| INCART | 0 | I28 | 13 | V4-B | 40.00% | 100.00% | 57.14% | 4 | 6 | 0 |
| INCART | 0 | I65 | 28 | V4-B | 92.04% | 27.23% | 42.02% | 104 | 9 | 278 |
| INCART | 0 | I66 | 28 | V4-B | 78.12% | 25.00% | 37.88% | 50 | 14 | 150 |
| INCART | 0 | I67 | 28 | V4-B | 94.37% | 25.24% | 39.82% | 134 | 8 | 397 |
| INCART | 0 | I74 | 32 | V4-B | 98.85% | 94.16% | 96.45% | 258 | 3 | 16 |
| INCART | 0 | I75 | 32 | V4-B | 100.00% | 99.84% | 99.92% | 612 | 0 | 1 |
| MITBIH | 0 | 111 | 111 | V4-B | 100.00% | 100.00% | 100.00% | 1 | 0 | 0 |
| MITBIH | 0 | 112 | 112 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 4 | 0 |
| MITBIH | 0 | 116 | 116 | V4-B | 93.91% | 99.08% | 96.43% | 108 | 7 | 1 |
| MITBIH | 0 | 124 | 124 | V4-B | 100.00% | 87.23% | 93.18% | 41 | 0 | 6 |
| MITBIH | 0 | 202 | 202 | V4-B | 10.67% | 100.00% | 19.29% | 19 | 159 | 0 |
| MITBIH | 0 | 208 | 208 | V4-B | 98.75% | 95.46% | 97.08% | 947 | 12 | 45 |
| MITBIH | 0 | 215 | 215 | V4-B | 93.94% | 37.80% | 53.91% | 62 | 4 | 102 |
| MITBIH | 0 | 231 | 231 | V4-B | 100.00% | 100.00% | 100.00% | 2 | 0 | 0 |
| INCART | 1 | I03 | 2 | V4 | 0.00% | 0.00% | 0.00% | 0 | 8 | 125 |
| INCART | 1 | I04 | 2 | V4 | 100.00% | 6.61% | 12.40% | 8 | 0 | 113 |
| INCART | 1 | I05 | 2 | V4 | 58.33% | 34.01% | 42.97% | 84 | 60 | 163 |
| INCART | 1 | I23 | 11 | V4 | 100.00% | 7.69% | 14.29% | 1 | 0 | 12 |
| INCART | 1 | I24 | 11 | V4 | 50.00% | 16.67% | 25.00% | 1 | 1 | 5 |
| INCART | 1 | I47 | 21 | V4 | 79.82% | 97.85% | 87.92% | 91 | 23 | 2 |
| INCART | 1 | I48 | 21 | V4 | 96.25% | 98.30% | 97.26% | 231 | 9 | 4 |
| INCART | 1 | I51 | 23 | V4 | 97.21% | 99.63% | 98.40% | 800 | 23 | 3 |
| INCART | 1 | I52 | 23 | V4 | 100.00% | 100.00% | 100.00% | 137 | 0 | 0 |
| INCART | 1 | I53 | 23 | V4 | 99.91% | 98.83% | 99.37% | 1098 | 1 | 13 |
| INCART | 1 | I54 | 24 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 22 |
| INCART | 1 | I55 | 24 | V4 | 100.00% | 11.76% | 21.05% | 2 | 0 | 15 |
| INCART | 1 | I56 | 24 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 7 |
| INCART | 1 | I72 | 31 | V4 | 79.89% | 73.06% | 76.32% | 282 | 71 | 104 |
| INCART | 1 | I73 | 31 | V4 | 65.22% | 42.86% | 51.72% | 30 | 16 | 40 |
| MITBIH | 1 | 100 | 100 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 1 |
| MITBIH | 1 | 106 | 106 | V4 | 99.39% | 62.69% | 76.89% | 326 | 2 | 194 |
| MITBIH | 1 | 109 | 109 | V4 | 100.00% | 15.79% | 27.27% | 6 | 0 | 32 |
| MITBIH | 1 | 118 | 118 | V4 | 100.00% | 25.00% | 40.00% | 4 | 0 | 12 |
| MITBIH | 1 | 121 | 121 | V4 | 0.00% | 0.00% | 0.00% | 0 | 10 | 1 |
| MITBIH | 1 | 122 | 122 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 1 | 203 | 203 | V4 | 30.89% | 78.83% | 44.39% | 350 | 783 | 94 |
| MITBIH | 1 | 210 | 210 | V4 | 93.02% | 20.62% | 33.76% | 40 | 3 | 154 |
| INCART | 1 | I03 | 2 | V4-B | 0.32% | 0.80% | 0.46% | 1 | 311 | 124 |
| INCART | 1 | I04 | 2 | V4-B | 45.00% | 7.44% | 12.77% | 9 | 11 | 112 |
| INCART | 1 | I05 | 2 | V4-B | 12.86% | 40.08% | 19.47% | 99 | 671 | 148 |
| INCART | 1 | I23 | 11 | V4-B | 100.00% | 15.38% | 26.67% | 2 | 0 | 11 |
| INCART | 1 | I24 | 11 | V4-B | 50.00% | 16.67% | 25.00% | 1 | 1 | 5 |
| INCART | 1 | I47 | 21 | V4-B | 79.13% | 97.85% | 87.50% | 91 | 24 | 2 |
| INCART | 1 | I48 | 21 | V4-B | 96.65% | 98.30% | 97.47% | 231 | 8 | 4 |
| INCART | 1 | I51 | 23 | V4-B | 97.45% | 99.75% | 98.58% | 801 | 21 | 2 |
| INCART | 1 | I52 | 23 | V4-B | 100.00% | 100.00% | 100.00% | 137 | 0 | 0 |
| INCART | 1 | I53 | 23 | V4-B | 99.91% | 99.10% | 99.50% | 1101 | 1 | 10 |
| INCART | 1 | I54 | 24 | V4-B | 100.00% | 13.64% | 24.00% | 3 | 0 | 19 |
| INCART | 1 | I55 | 24 | V4-B | 28.57% | 11.76% | 16.67% | 2 | 5 | 15 |
| INCART | 1 | I56 | 24 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 2 | 7 |
| INCART | 1 | I72 | 31 | V4-B | 78.92% | 71.76% | 75.17% | 277 | 74 | 109 |
| INCART | 1 | I73 | 31 | V4-B | 59.09% | 37.14% | 45.61% | 26 | 18 | 44 |
| MITBIH | 1 | 100 | 100 | V4-B | 100.00% | 100.00% | 100.00% | 1 | 0 | 0 |
| MITBIH | 1 | 106 | 106 | V4-B | 99.32% | 56.15% | 71.74% | 292 | 2 | 228 |
| MITBIH | 1 | 109 | 109 | V4-B | 100.00% | 21.05% | 34.78% | 8 | 0 | 30 |
| MITBIH | 1 | 118 | 118 | V4-B | 100.00% | 25.00% | 40.00% | 4 | 0 | 12 |
| MITBIH | 1 | 121 | 121 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 42 | 1 |
| MITBIH | 1 | 122 | 122 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 1 | 203 | 203 | V4-B | 31.40% | 77.03% | 44.62% | 342 | 747 | 102 |
| MITBIH | 1 | 210 | 210 | V4-B | 86.54% | 23.20% | 36.59% | 45 | 7 | 149 |
| INCART | 2 | I15 | 7 | V4 | 0.00% | 0.00% | 0.00% | 0 | 6 | 3 |
| INCART | 2 | I25 | 12 | V4 | 0.94% | 40.00% | 1.84% | 2 | 210 | 3 |
| INCART | 2 | I26 | 12 | V4 | 7.14% | 25.00% | 11.11% | 1 | 13 | 3 |
| INCART | 2 | I33 | 15 | V4 | 50.00% | 100.00% | 66.67% | 1 | 1 | 0 |
| INCART | 2 | I34 | 15 | V4 | 0.00% | 0.00% | 0.00% | 0 | 4 | 0 |
| INCART | 2 | I35 | 16 | V4 | 81.78% | 80.35% | 81.06% | 368 | 82 | 90 |
| INCART | 2 | I36 | 16 | V4 | 61.30% | 73.56% | 66.87% | 331 | 209 | 119 |
| INCART | 2 | I37 | 16 | V4 | 99.78% | 99.78% | 99.78% | 451 | 1 | 1 |
| INCART | 2 | I44 | 20 | V4 | 99.85% | 99.42% | 99.63% | 680 | 1 | 4 |
| INCART | 2 | I45 | 20 | V4 | 100.00% | 98.98% | 99.49% | 486 | 0 | 5 |
| INCART | 2 | I46 | 20 | V4 | 94.87% | 96.45% | 95.65% | 407 | 22 | 15 |
| MITBIH | 2 | 115 | 115 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 2 | 209 | 209 | V4 | 50.00% | 100.00% | 66.67% | 1 | 1 | 0 |
| MITBIH | 2 | 212 | 212 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 2 | 214 | 214 | V4 | 99.47% | 73.83% | 84.75% | 189 | 1 | 67 |
| MITBIH | 2 | 219 | 219 | V4 | 82.86% | 90.62% | 86.57% | 58 | 12 | 6 |
| MITBIH | 2 | 220 | 220 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 2 | 233 | 233 | V4 | 68.48% | 98.32% | 80.73% | 817 | 376 | 14 |
| MITBIH | 2 | 234 | 234 | V4 | 0.00% | 0.00% | 0.00% | 0 | 2 | 3 |
| INCART | 2 | I15 | 7 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 4 | 3 |
| INCART | 2 | I25 | 12 | V4-B | 0.40% | 20.00% | 0.78% | 1 | 250 | 4 |
| INCART | 2 | I26 | 12 | V4-B | 5.88% | 25.00% | 9.52% | 1 | 16 | 3 |
| INCART | 2 | I33 | 15 | V4-B | 33.33% | 100.00% | 50.00% | 1 | 2 | 0 |
| INCART | 2 | I34 | 15 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 2 | 0 |
| INCART | 2 | I35 | 16 | V4-B | 63.37% | 85.37% | 72.74% | 391 | 226 | 67 |
| INCART | 2 | I36 | 16 | V4-B | 51.04% | 76.67% | 61.28% | 345 | 331 | 105 |
| INCART | 2 | I37 | 16 | V4-B | 86.90% | 99.78% | 92.89% | 451 | 68 | 1 |
| INCART | 2 | I44 | 20 | V4-B | 99.56% | 99.71% | 99.63% | 682 | 3 | 2 |
| INCART | 2 | I45 | 20 | V4-B | 100.00% | 99.39% | 99.69% | 488 | 0 | 3 |
| INCART | 2 | I46 | 20 | V4-B | 94.47% | 97.16% | 95.79% | 410 | 24 | 12 |
| MITBIH | 2 | 115 | 115 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 1 | 0 |
| MITBIH | 2 | 209 | 209 | V4-B | 20.00% | 100.00% | 33.33% | 1 | 4 | 0 |
| MITBIH | 2 | 212 | 212 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 2 | 214 | 214 | V4-B | 99.47% | 73.44% | 84.49% | 188 | 1 | 68 |
| MITBIH | 2 | 219 | 219 | V4-B | 90.48% | 89.06% | 89.76% | 57 | 6 | 7 |
| MITBIH | 2 | 220 | 220 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 2 | 233 | 233 | V4-B | 47.83% | 98.19% | 64.33% | 816 | 890 | 15 |
| MITBIH | 2 | 234 | 234 | V4-B | 33.33% | 33.33% | 33.33% | 1 | 2 | 2 |
| INCART | 3 | I06 | 3 | V4 | 100.00% | 88.89% | 94.12% | 8 | 0 | 1 |
| INCART | 3 | I07 | 3 | V4 | 100.00% | 100.00% | 100.00% | 1 | 0 | 0 |
| INCART | 3 | I09 | 5 | V4 | 100.00% | 9.76% | 17.78% | 4 | 0 | 37 |
| INCART | 3 | I10 | 5 | V4 | 90.00% | 10.84% | 19.35% | 9 | 1 | 74 |
| INCART | 3 | I11 | 5 | V4 | 100.00% | 100.00% | 100.00% | 4 | 0 | 0 |
| INCART | 3 | I42 | 19 | V4 | 80.15% | 96.14% | 87.42% | 1494 | 370 | 60 |
| INCART | 3 | I43 | 19 | V4 | 100.00% | 94.20% | 97.01% | 1055 | 0 | 65 |
| INCART | 3 | I57 | 25 | V4 | 89.47% | 80.95% | 85.00% | 17 | 2 | 4 |
| INCART | 3 | I58 | 25 | V4 | 92.31% | 100.00% | 96.00% | 12 | 1 | 0 |
| INCART | 3 | I68 | 29 | V4 | 38.78% | 75.16% | 51.16% | 121 | 191 | 40 |
| INCART | 3 | I69 | 29 | V4 | 98.75% | 94.61% | 96.64% | 158 | 2 | 9 |
| MITBIH | 3 | 101 | 101 | V4 | 0.00% | 0.00% | 0.00% | 0 | 1 | 0 |
| MITBIH | 3 | 114 | 114 | V4 | 100.00% | 93.02% | 96.39% | 40 | 0 | 3 |
| MITBIH | 3 | 119 | 119 | V4 | 100.00% | 99.77% | 99.89% | 443 | 0 | 1 |
| MITBIH | 3 | 205 | 205 | V4 | 100.00% | 80.28% | 89.06% | 57 | 0 | 14 |
| MITBIH | 3 | 207 | 207 | V4 | 50.00% | 74.29% | 59.77% | 78 | 78 | 27 |
| MITBIH | 3 | 213 | 213 | V4 | 43.35% | 96.36% | 59.80% | 212 | 277 | 8 |
| MITBIH | 3 | 221 | 221 | V4 | 100.00% | 98.74% | 99.36% | 391 | 0 | 5 |
| INCART | 3 | I06 | 3 | V4-B | 72.73% | 88.89% | 80.00% | 8 | 3 | 1 |
| INCART | 3 | I07 | 3 | V4-B | 100.00% | 100.00% | 100.00% | 1 | 0 | 0 |
| INCART | 3 | I09 | 5 | V4-B | 100.00% | 17.07% | 29.17% | 7 | 0 | 34 |
| INCART | 3 | I10 | 5 | V4-B | 25.00% | 2.41% | 4.40% | 2 | 6 | 81 |
| INCART | 3 | I11 | 5 | V4-B | 100.00% | 50.00% | 66.67% | 2 | 0 | 2 |
| INCART | 3 | I42 | 19 | V4-B | 75.76% | 97.55% | 85.29% | 1516 | 485 | 38 |
| INCART | 3 | I43 | 19 | V4-B | 100.00% | 95.36% | 97.62% | 1068 | 0 | 52 |
| INCART | 3 | I57 | 25 | V4-B | 64.00% | 76.19% | 69.57% | 16 | 9 | 5 |
| INCART | 3 | I58 | 25 | V4-B | 92.31% | 100.00% | 96.00% | 12 | 1 | 0 |
| INCART | 3 | I68 | 29 | V4-B | 75.00% | 72.67% | 73.82% | 117 | 39 | 44 |
| INCART | 3 | I69 | 29 | V4-B | 98.80% | 98.20% | 98.50% | 164 | 2 | 3 |
| MITBIH | 3 | 101 | 101 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 1 | 0 |
| MITBIH | 3 | 114 | 114 | V4-B | 100.00% | 79.07% | 88.31% | 34 | 0 | 9 |
| MITBIH | 3 | 119 | 119 | V4-B | 99.77% | 99.77% | 99.77% | 443 | 1 | 1 |
| MITBIH | 3 | 205 | 205 | V4-B | 100.00% | 78.87% | 88.19% | 56 | 0 | 15 |
| MITBIH | 3 | 207 | 207 | V4-B | 49.43% | 81.90% | 61.65% | 86 | 88 | 19 |
| MITBIH | 3 | 213 | 213 | V4-B | 21.76% | 97.73% | 35.60% | 215 | 773 | 5 |
| MITBIH | 3 | 221 | 221 | V4-B | 99.75% | 98.99% | 99.37% | 392 | 1 | 4 |
| INCART | 4 | I08 | 4 | V4 | 96.77% | 59.83% | 73.94% | 210 | 7 | 141 |
| INCART | 4 | I29 | 14 | V4 | 98.73% | 9.96% | 18.10% | 78 | 1 | 705 |
| INCART | 4 | I30 | 14 | V4 | 100.00% | 14.02% | 24.59% | 106 | 0 | 650 |
| INCART | 4 | I31 | 14 | V4 | 83.33% | 3.30% | 6.34% | 45 | 9 | 1320 |
| INCART | 4 | I32 | 14 | V4 | 100.00% | 5.26% | 10.00% | 3 | 0 | 54 |
| INCART | 4 | I40 | 18 | V4 | 86.00% | 93.48% | 89.58% | 86 | 14 | 6 |
| INCART | 4 | I41 | 18 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 1 |
| INCART | 4 | I49 | 22 | V4 | 100.00% | 100.00% | 100.00% | 27 | 0 | 0 |
| INCART | 4 | I50 | 22 | V4 | 0.00% | 0.00% | 0.00% | 0 | 2 | 4 |
| INCART | 4 | I59 | 26 | V4 | 73.33% | 13.58% | 22.92% | 11 | 4 | 70 |
| INCART | 4 | I60 | 26 | V4 | 0.00% | 0.00% | 0.00% | 0 | 11 | 0 |
| INCART | 4 | I61 | 26 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 4 | 103 | 103 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 4 | 105 | 105 | V4 | 5.22% | 14.63% | 7.69% | 6 | 109 | 35 |
| MITBIH | 4 | 201 | 201 | V4 | 92.72% | 96.46% | 94.55% | 191 | 15 | 7 |
| MITBIH | 4 | 217 | 217 | V4 | 83.24% | 91.98% | 87.39% | 149 | 30 | 13 |
| MITBIH | 4 | 223 | 223 | V4 | 99.08% | 45.67% | 62.52% | 216 | 2 | 257 |
| MITBIH | 4 | 228 | 228 | V4 | 75.86% | 18.23% | 29.40% | 66 | 21 | 296 |
| MITBIH | 4 | 230 | 230 | V4 | 100.00% | 100.00% | 100.00% | 1 | 0 | 0 |
| INCART | 4 | I08 | 4 | V4-B | 96.71% | 58.69% | 73.05% | 206 | 7 | 145 |
| INCART | 4 | I29 | 14 | V4-B | 97.30% | 9.20% | 16.80% | 72 | 2 | 711 |
| INCART | 4 | I30 | 14 | V4-B | 100.00% | 12.30% | 21.91% | 93 | 0 | 663 |
| INCART | 4 | I31 | 14 | V4-B | 82.69% | 3.15% | 6.07% | 43 | 9 | 1322 |
| INCART | 4 | I32 | 14 | V4-B | 100.00% | 3.51% | 6.78% | 2 | 0 | 55 |
| INCART | 4 | I40 | 18 | V4-B | 86.00% | 93.48% | 89.58% | 86 | 14 | 6 |
| INCART | 4 | I41 | 18 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 0 | 1 |
| INCART | 4 | I49 | 22 | V4-B | 100.00% | 100.00% | 100.00% | 27 | 0 | 0 |
| INCART | 4 | I50 | 22 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 2 | 4 |
| INCART | 4 | I59 | 26 | V4-B | 73.33% | 13.58% | 22.92% | 11 | 4 | 70 |
| INCART | 4 | I60 | 26 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 11 | 0 |
| INCART | 4 | I61 | 26 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 4 | 103 | 103 | V4-B | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 4 | 105 | 105 | V4-B | 3.48% | 9.76% | 5.13% | 4 | 111 | 37 |
| MITBIH | 4 | 201 | 201 | V4-B | 92.50% | 93.43% | 92.96% | 185 | 15 | 13 |
| MITBIH | 4 | 217 | 217 | V4-B | 85.71% | 92.59% | 89.02% | 150 | 25 | 12 |
| MITBIH | 4 | 223 | 223 | V4-B | 99.00% | 41.86% | 58.84% | 198 | 2 | 275 |
| MITBIH | 4 | 228 | 228 | V4-B | 72.62% | 16.85% | 27.35% | 61 | 23 | 301 |
| MITBIH | 4 | 230 | 230 | V4-B | 100.00% | 100.00% | 100.00% | 1 | 0 | 0 |

Full patient-group aggregation is in group_metrics.json. Group F1 with no referencePVC is not a meaningful sensitivity estimate; acceptance group criterion includes only groups containingPVC. CNN-only counts/FP1000N per fold are retained in evaluation.json. No global final V4-B is trained or selected from outer results. Stop after this report.
