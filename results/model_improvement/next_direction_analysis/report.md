# V4 recall: next direction analysis

No Test, training, threshold change or firmware modification. Frozen final V4(.88), V6(.87), V11(.80); ECG windows from unchanged detector. V4 scores reused, paired V6/V11 scores supplemented because old aggregate metrics did not preserve per-peak pairing. Native stage probe observes accepted centers and completed windows without changing detector; emitted centers asserted identical to old traces for every record.

## Evidence boundaries

Reuse V4-A locked group split: Fit37 records, Calibration19, Evaluation45; MIT record/INCART patient groups disjoint. No parameter or routing classifier is learned/selected in this analysis. Hypotheses and fixed OR diagnostics recorded before Evaluation. Earlier research exposed these groups, and many Evaluation records were used in the frozen CNNs Fit. Train predictions are in-sample, NOT OOF. These are paired internal diagnostic observations, not independent predictive validation. Original Development-only results can be derived from the retained record rows, but are selection-exposed too.

## FN decomposition and paired trade-offs on Evaluation

| Dataset | Reference PVC | No accepted detector center | Accepted but no completed window | CNN V4 Normal | Other/matching unresolved | V11 rescues | V6 rescues | All3 miss matched PVC | New N FP by V11 | New N FP by V6 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | 2548 | 57 | 0 | 181 | 0 | 151 | 127 | 27 | 123 | 29 |
| INCART | 7019 | 82 | 0 | 911 | 0 | 789 | 751 | 69 | 271 | 42 |

“No center” includes warm-up, amplitude/refractory and matching failures; it does not prove there was no physiological R wave. Accepted-without-window is measured from the same native replay, not guessed from missing emitted peaks. OTHER excluded N/V labels; all missing V retained FN. Scope unmatched alarms remain additional FP, not automatically noise. Ungated pipeline, no physical quality-gate/latency simulation.

## Fixed OR diagnostic — actual predictions, not an oracle

| Role | Dataset | Rule | Precision | Recall | F1 | FP | FN |
|---|---|---|---:|---:|---:|---:|---:|
| Fit | MITBIH | V4 | 82.24% | 94.40% | 87.90% | 513 | 141 |
| Fit | MITBIH | V4 OR V6 | 81.68% | 97.14% | 88.74% | 548 | 72 |
| Fit | MITBIH | V4 OR V11 | 80.16% | 97.62% | 88.03% | 608 | 60 |
| Fit | INCART | V4 | 85.63% | 70.90% | 77.57% | 796 | 1947 |
| Fit | INCART | V4 OR V6 | 78.72% | 85.14% | 81.80% | 1540 | 994 |
| Fit | INCART | V4 OR V11 | 72.64% | 85.65% | 78.61% | 2158 | 960 |
| Calibration | MITBIH | V4 | 65.64% | 93.94% | 77.28% | 568 | 70 |
| Calibration | MITBIH | V4 OR V6 | 64.94% | 95.58% | 77.34% | 596 | 51 |
| Calibration | MITBIH | V4 OR V11 | 65.01% | 96.54% | 77.70% | 600 | 40 |
| Calibration | INCART | V4 | 87.67% | 92.19% | 89.87% | 385 | 232 |
| Calibration | INCART | V4 OR V6 | 55.47% | 95.76% | 70.25% | 2283 | 126 |
| Calibration | INCART | V4 OR V11 | 54.14% | 95.59% | 69.13% | 2405 | 131 |
| Evaluation | MITBIH | V4 | 60.47% | 90.66% | 72.55% | 1510 | 238 |
| Evaluation | MITBIH | V4 OR V6 | 60.22% | 95.64% | 73.90% | 1610 | 111 |
| Evaluation | MITBIH | V4 OR V11 | 58.76% | 96.59% | 73.07% | 1727 | 87 |
| Evaluation | INCART | V4 | 75.67% | 85.85% | 80.44% | 1938 | 993 |
| Evaluation | INCART | V4 OR V6 | 68.75% | 96.55% | 80.32% | 3080 | 242 |
| Evaluation | INCART | V4 OR V11 | 65.19% | 97.09% | 78.01% | 3639 | 204 |

OR retains all V4 PVC alarms and adds partner alarms at unchanged thresholds. Added unmatched alarms count FP. Rescue counts are ground-truth diagnostic intersections, NOT achievable conditional selection accuracy. No runtime rule knows which V4 misses are true PVC. A selected cascade would require a separately fixed/calibrated router and new evaluation; it was not created here.

## Morphology/context hypotheses

Metrics are diagnostic proxies: central128 normalized PTP; half-amplitude support count (not clinical QRS duration); current detected RR; correlation with previous raw detector window; central energy ratio. Neighbor window can overlap the current256 window; high correlation is not independent beat morphology evidence. No annotation-neighbor labels are used as input. Score distributions use each fixed model, not re-calibrated confidence.

| Role | Dataset | Group | n | PTP median | Support ms median | RR median | Previous-window corr median | Energy ratio median | V4 score median | V11 score median |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fit | MITBIH | PVC_all_wrong | 9 | 6.1640 | 32.0000 | 0.5400 | 0.3390 | 0.9932 | 0.3412 | 0.4084 |
| Fit | MITBIH | V4_correct_N_V11_false_positive | 23 | 5.3596 | 28.0000 | 0.4120 | 0.1004 | 0.9822 | 0.5400 | 0.9376 |
| Fit | MITBIH | V4_correct_N_V6_false_positive | 7 | 6.7488 | 40.0000 | 0.8160 | 0.5304 | 0.9630 | 0.7769 | 0.1073 |
| Fit | MITBIH | V4_missed_PVC_V11_rescued | 81 | 4.0225 | 48.0000 | 0.4840 | 0.2332 | 0.3356 | 0.8158 | 0.9903 |
| Fit | MITBIH | V4_missed_PVC_V6_rescued | 4 | 5.0789 | 42.0000 | 0.6340 | 0.1664 | 0.7683 | 0.7728 | 0.7707 |
| Fit | INCART | PVC_all_wrong | 111 | 5.9953 | 32.0000 | 1.1000 | 0.2062 | 0.9874 | 0.2169 | 0.0030 |
| Fit | INCART | V4_correct_N_V11_false_positive | 208 | 4.7063 | 60.0000 | 0.3320 | 0.1452 | 0.8686 | 0.3074 | 0.9485 |
| Fit | INCART | V4_correct_N_V6_false_positive | 10 | 5.9694 | 52.0000 | 0.7000 | 0.1408 | 0.4156 | 0.3975 | 0.0089 |
| Fit | INCART | V4_missed_PVC_V11_rescued | 987 | 6.3227 | 36.0000 | 0.4520 | 0.2274 | 0.8291 | 0.6238 | 0.9956 |
| Fit | INCART | V4_missed_PVC_V6_rescued | 78 | 6.1447 | 36.0000 | 0.5800 | 0.1856 | 0.8675 | 0.6500 | 0.3575 |
| Calibration | MITBIH | PVC_all_wrong | 28 | 4.5299 | 36.0000 | 0.5000 | 0.3790 | 0.9418 | 0.5819 | 0.6817 |
| Calibration | MITBIH | V4_correct_N_V11_false_positive | 8 | 6.1929 | 36.0000 | 0.5720 | 0.8320 | 0.9984 | 0.4042 | 0.8902 |
| Calibration | MITBIH | V4_correct_N_V6_false_positive | 11 | 6.2100 | 36.0000 | 0.7520 | -0.6929 | 0.9921 | 0.6679 | 0.0950 |
| Calibration | MITBIH | V4_missed_PVC_V11_rescued | 30 | 4.4669 | 40.0000 | 0.4720 | 0.3159 | 0.7092 | 0.7737 | 0.9375 |
| Calibration | MITBIH | V4_missed_PVC_V6_rescued | 2 | 4.1453 | 36.0000 | 0.4800 | 0.2226 | 0.7259 | 0.7330 | 0.7209 |
| Calibration | INCART | PVC_all_wrong | 40 | 5.9108 | 28.0000 | 0.4780 | 0.8388 | 0.9966 | 0.2728 | 0.4968 |
| Calibration | INCART | V4_correct_N_V11_false_positive | 14 | 4.3568 | 28.0000 | 0.3780 | 0.5564 | 0.9587 | 0.2714 | 0.9551 |
| Calibration | INCART | V4_correct_N_V6_false_positive | 5 | 5.9775 | 24.0000 | 0.5920 | 0.6132 | 0.9778 | 0.6199 | 0.3255 |
| Calibration | INCART | V4_missed_PVC_V11_rescued | 101 | 5.8526 | 36.0000 | 0.4520 | 0.6405 | 0.9919 | 0.7076 | 0.9774 |
| Calibration | INCART | V4_missed_PVC_V6_rescued | 13 | 6.0153 | 28.0000 | 0.4680 | 0.7492 | 0.9959 | 0.6301 | 0.6713 |
| Evaluation | MITBIH | PVC_all_wrong | 27 | 6.2639 | 24.0000 | 0.5400 | 0.3127 | 0.9980 | 0.2812 | 0.2245 |
| Evaluation | MITBIH | V4_correct_N_V11_false_positive | 123 | 4.6953 | 36.0000 | 0.3880 | 0.3619 | 0.9638 | 0.6466 | 0.9204 |
| Evaluation | MITBIH | V4_correct_N_V6_false_positive | 19 | 5.1234 | 40.0000 | 0.5680 | 0.4065 | 0.9094 | 0.5654 | 0.1311 |
| Evaluation | MITBIH | V4_missed_PVC_V11_rescued | 151 | 5.3921 | 52.0000 | 0.4400 | 0.1685 | 0.9572 | 0.7490 | 0.9981 |
| Evaluation | MITBIH | V4_missed_PVC_V6_rescued | 3 | 5.7655 | 36.0000 | 0.4760 | 0.2091 | 0.7483 | 0.8554 | 0.3660 |
| Evaluation | INCART | PVC_all_wrong | 69 | 6.3834 | 36.0000 | 0.5560 | 0.4715 | 0.9900 | 0.2097 | 0.4668 |
| Evaluation | INCART | V4_correct_N_V11_false_positive | 271 | 5.1458 | 60.0000 | 0.3720 | 0.0061 | 0.8774 | 0.3600 | 0.9464 |
| Evaluation | INCART | V4_correct_N_V6_false_positive | 19 | 5.0280 | 44.0000 | 0.4840 | 0.0161 | 0.3166 | 0.2636 | 0.2642 |
| Evaluation | INCART | V4_missed_PVC_V11_rescued | 789 | 5.2321 | 72.0000 | 0.4200 | 0.1034 | 0.9327 | 0.6619 | 0.9965 |
| Evaluation | INCART | V4_missed_PVC_V6_rescued | 53 | 5.8499 | 60.0000 | 0.6360 | 0.2034 | 0.9702 | 0.4966 | 0.2453 |

IQRs and full individual observations in evaluation.json/beat_diagnostics.json. Overlap between rescued PVC and new-FP Normal morphology/RR distributions means medians alone cannot justify a runtime rule. Width and neighbor similarity are hypotheses; contributions of learned morphology, RR and distribution shift are not causally isolated. PVC all-wrong and Normal all-wrong counts per record/group are preserved.

## Interpretation and priority (no new model or rule implemented)

On held-out-for-analysis Evaluation groups, 181/238=76.05% MIT and
911/993=91.74% INC V4 FN occur after a valid detector window reaches CNN.
57/82 PVC FN occur before an accepted matched detector center;0 window-stage
losses and0 unresolved stage assignments were observed. These are diagnostic
facts on Train/Development groups, not an explanation proven for historical
Test. Existing ungated coverage and matching limitations still apply.

Evaluation V11 rescues151 MIT and789 INC matched PVC missed by V4. However
the corresponding new-FP costs are123/271 matched Normal plus94/1430 unmatched
PVC alarms, totaling217/1701 extra FP. The fixed OR diagnostic raises Recall,
but INC F1 falls80.44%→78.01%; it does not demonstrate a controlled cascade.
V6 rescues127/751, with100/1142 extra FP. No model or routing rule is granted
ground-truth knowledge of which rescue candidates to accept.

Morphology/context separation is not stable enough for a simple rule:
INC Fit rescued-PVC support median36ms versus new-FP Normal60ms, but Evaluation
rescued-PVC median72ms versus60ms. MIT previous-window correlation order also
reverses (Fit .233 vs .100; Evaluation .169 vs .362). RR medians in Evaluation
are .440/.420s for rescued PVC versus even shorter .388/.372s for new-FP N;
prematurity alone cannot safely separate them. V11 false-positive confidence
medians remain high (.920/.946), so confidence is not calibrated evidence of
truth. Width is a support proxy and not clinical QRS measurement. Learned
morphology, current RR and neighboring context were not separately ablated.

**B has the strongest rationale for a separately authorized research step**:
the dominant loss is CNN classification, the paired models show recoverable
morphology cases, and original-Train missed PVC/protected Normal candidates
are explicitly available. This supports investigating a balanced Train-only
training objective, not claiming a future V4-B will improve. A remains a useful
diagnostic feature family; there is no stable calibrated runtime rule yet.
C needs a learned/validated reliability router and adds the most deployment
complexity; no such router is justified by these data alone.

Keep V4 unchanged for a limited static ESP32 arithmetic/golden/timing exercise.
Continue research before claiming adequate PVC recall or deploying a final
system. This analysis does not authorize training B, changing model thresholds,
or beginning ESP32 integration. All next-step proposals stop at this report.

## Three options and ESP32 cost estimates

| Direction | Evidence/potential | Approximate embedded cost | Main unresolved requirement |
|---|---|---|---|
| A V4+temporal/morphology context | Can describe missed PVC and existing QRS-verification limits; no validated decision rule yet | V4 raw FP32 weights3396B plus feature code; one previous float ECG window1024B and8 int64 timestamps64B if needed; O(256) feature scan; model latency plus feature time, board PENDING | Fit-only/calibration rule or feature training; avoid rejecting wide/early/low-QRS PVC; causal history/reset policy |
| B focused training with protected Normal negatives | Single-model potential: missed PVC and partner-induced Normal FP provide concrete Train-only targets; no improvement claim before training | If architecture V4 retained,849 weights=3396B FP32; input1024B; runtime should be similar graph class but actual arena/latency PENDING; no required ECG history | Maintain group diversity and class balance; no Test hard negatives; Evaluate once with separate groups and protect hard-negative N |
| C V4+V11 controlled cascade | Paired rescue exists, but actual OR also adds false alarms; not evidence of a working controlled router | Raw FP32 weights3396+8068=11464B excluding graph/runtime; shared input1024B plus RR history/scaling; sequential worst-case latency T4+T11+router; arena can only be planned/measured, not assumed additive or reusable | Router reliability, reset/missing-RR policy, independent calibration, full safety gate; no oracle routing |

These are parameter/input payload calculations, not Tensor Arena or compiled Flash measurements. FP32 deployment, INT8 graph metadata, allocator scratch/persistent state and ESP-NN coverage differ. Actual RAM/Flash and inference time require a separately authorized host/build/board measurement. No such deployment measurements were performed here.

## Train-only candidate counts for a possible future B experiment
MITBIH: {"matched_PVC_V4miss": 94, "protected_N_V4correct_V11_FP": 23}
INCART: {"matched_PVC_V4miss": 1126, "protected_N_V4correct_V11_FP": 173}

Use only these original-Train groups for future hard-example construction; do not mine Evaluation, original Development or Test for training examples. This artifact identifies counts, not a new dataset or model.

## Record/patient diagnostic detail

| Role | Dataset | Record | Group | Detector FN | Window FN | CNN FN | V11 rescue | New N FP V11 | OR11 extra FP incl unmatched |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| Fit | INCART | I06 | 3 | 0 | 0 | 0 | 0 | 6 | 44 |
| Fit | INCART | I07 | 3 | 0 | 0 | 0 | 0 | 5 | 27 |
| Fit | INCART | I08 | 4 | 2 | 0 | 49 | 43 | 28 | 154 |
| Fit | INCART | I09 | 5 | 0 | 0 | 6 | 3 | 7 | 287 |
| Fit | INCART | I10 | 5 | 0 | 0 | 16 | 16 | 10 | 37 |
| Fit | INCART | I11 | 5 | 0 | 0 | 0 | 0 | 0 | 199 |
| Fit | INCART | I29 | 14 | 23 | 0 | 400 | 372 | 15 | 62 |
| Fit | INCART | I30 | 14 | 4 | 1 | 418 | 371 | 0 | 32 |
| Fit | INCART | I31 | 14 | 721 | 0 | 199 | 108 | 11 | 20 |
| Fit | INCART | I32 | 14 | 0 | 0 | 24 | 23 | 1 | 15 |
| Fit | INCART | I40 | 18 | 0 | 0 | 2 | 2 | 24 | 111 |
| Fit | INCART | I41 | 18 | 0 | 0 | 1 | 1 | 3 | 10 |
| Fit | INCART | I42 | 19 | 4 | 0 | 2 | 2 | 0 | 0 |
| Fit | INCART | I43 | 19 | 5 | 0 | 4 | 2 | 0 | 0 |
| Fit | INCART | I49 | 22 | 0 | 0 | 0 | 0 | 1 | 3 |
| Fit | INCART | I50 | 22 | 0 | 0 | 3 | 2 | 1 | 10 |
| Fit | INCART | I57 | 25 | 3 | 0 | 1 | 1 | 3 | 20 |
| Fit | INCART | I58 | 25 | 0 | 0 | 0 | 0 | 4 | 43 |
| Fit | INCART | I59 | 26 | 3 | 0 | 40 | 30 | 13 | 57 |
| Fit | INCART | I60 | 26 | 0 | 0 | 0 | 0 | 12 | 45 |
| Fit | INCART | I61 | 26 | 0 | 0 | 0 | 0 | 0 | 0 |
| Fit | INCART | I68 | 29 | 5 | 0 | 9 | 9 | 61 | 179 |
| Fit | INCART | I69 | 29 | 0 | 0 | 2 | 2 | 3 | 7 |
| Fit | MITBIH | 101 | 101 | 0 | 0 | 0 | 0 | 1 | 5 |
| Fit | MITBIH | 103 | 103 | 0 | 0 | 0 | 0 | 0 | 0 |
| Fit | MITBIH | 105 | 105 | 0 | 0 | 14 | 14 | 1 | 7 |
| Fit | MITBIH | 114 | 114 | 0 | 0 | 3 | 2 | 1 | 2 |
| Fit | MITBIH | 119 | 119 | 1 | 0 | 0 | 0 | 0 | 0 |
| Fit | MITBIH | 201 | 201 | 1 | 0 | 2 | 2 | 7 | 7 |
| Fit | MITBIH | 205 | 205 | 12 | 0 | 0 | 0 | 0 | 0 |
| Fit | MITBIH | 207 | 207 | 7 | 0 | 0 | 0 | 0 | 1 |
| Fit | MITBIH | 213 | 213 | 2 | 0 | 2 | 0 | 0 | 0 |
| Fit | MITBIH | 217 | 217 | 11 | 0 | 0 | 0 | 1 | 3 |
| Fit | MITBIH | 221 | 221 | 2 | 0 | 2 | 2 | 0 | 0 |
| Fit | MITBIH | 223 | 223 | 6 | 0 | 60 | 51 | 0 | 1 |
| Fit | MITBIH | 228 | 228 | 5 | 0 | 11 | 10 | 11 | 65 |
| Fit | MITBIH | 230 | 230 | 0 | 0 | 0 | 0 | 1 | 4 |
| Calibration | INCART | I15 | 7 | 0 | 0 | 3 | 3 | 0 | 1 |
| Calibration | INCART | I25 | 12 | 3 | 0 | 0 | 0 | 5 | 780 |
| Calibration | INCART | I26 | 12 | 0 | 0 | 3 | 1 | 0 | 1201 |
| Calibration | INCART | I33 | 15 | 0 | 0 | 0 | 0 | 0 | 5 |
| Calibration | INCART | I34 | 15 | 0 | 0 | 0 | 0 | 0 | 8 |
| Calibration | INCART | I35 | 16 | 2 | 0 | 83 | 56 | 3 | 3 |
| Calibration | INCART | I36 | 16 | 71 | 0 | 53 | 37 | 1 | 4 |
| Calibration | INCART | I37 | 16 | 0 | 0 | 0 | 0 | 0 | 0 |
| Calibration | INCART | I44 | 20 | 1 | 0 | 1 | 1 | 1 | 1 |
| Calibration | INCART | I45 | 20 | 1 | 0 | 2 | 0 | 0 | 0 |
| Calibration | INCART | I46 | 20 | 0 | 0 | 9 | 3 | 4 | 17 |
| Calibration | MITBIH | 115 | 115 | 0 | 0 | 0 | 0 | 0 | 0 |
| Calibration | MITBIH | 209 | 209 | 0 | 0 | 0 | 0 | 0 | 10 |
| Calibration | MITBIH | 212 | 212 | 0 | 0 | 0 | 0 | 0 | 11 |
| Calibration | MITBIH | 214 | 214 | 3 | 0 | 49 | 20 | 0 | 1 |
| Calibration | MITBIH | 219 | 219 | 0 | 0 | 6 | 5 | 5 | 6 |
| Calibration | MITBIH | 220 | 220 | 0 | 0 | 0 | 0 | 0 | 0 |
| Calibration | MITBIH | 233 | 233 | 7 | 0 | 2 | 2 | 3 | 3 |
| Calibration | MITBIH | 234 | 234 | 0 | 0 | 3 | 3 | 0 | 1 |
| Evaluation | INCART | I01 | 1 | 35 | 0 | 208 | 181 | 43 | 225 |
| Evaluation | INCART | I02 | 1 | 3 | 0 | 208 | 197 | 50 | 91 |
| Evaluation | INCART | I03 | 2 | 1 | 0 | 59 | 54 | 25 | 60 |
| Evaluation | INCART | I04 | 2 | 0 | 0 | 107 | 78 | 21 | 99 |
| Evaluation | INCART | I05 | 2 | 0 | 0 | 28 | 19 | 11 | 189 |
| Evaluation | INCART | I12 | 6 | 2 | 0 | 1 | 1 | 0 | 2 |
| Evaluation | INCART | I13 | 6 | 1 | 0 | 0 | 0 | 0 | 0 |
| Evaluation | INCART | I14 | 6 | 0 | 0 | 0 | 0 | 2 | 8 |
| Evaluation | INCART | I16 | 8 | 1 | 0 | 1 | 0 | 0 | 371 |
| Evaluation | INCART | I17 | 8 | 3 | 0 | 24 | 3 | 0 | 151 |
| Evaluation | INCART | I23 | 11 | 0 | 0 | 10 | 10 | 8 | 22 |
| Evaluation | INCART | I24 | 11 | 0 | 0 | 3 | 3 | 2 | 7 |
| Evaluation | INCART | I27 | 13 | 3 | 0 | 1 | 0 | 3 | 12 |
| Evaluation | INCART | I28 | 13 | 0 | 0 | 0 | 0 | 0 | 8 |
| Evaluation | INCART | I47 | 21 | 1 | 0 | 5 | 5 | 15 | 152 |
| Evaluation | INCART | I48 | 21 | 4 | 0 | 15 | 15 | 10 | 115 |
| Evaluation | INCART | I51 | 23 | 2 | 0 | 0 | 0 | 1 | 1 |
| Evaluation | INCART | I52 | 23 | 0 | 0 | 0 | 0 | 0 | 0 |
| Evaluation | INCART | I53 | 23 | 6 | 0 | 1 | 1 | 0 | 2 |
| Evaluation | INCART | I54 | 24 | 0 | 0 | 12 | 8 | 48 | 71 |
| Evaluation | INCART | I55 | 24 | 0 | 0 | 10 | 8 | 10 | 18 |
| Evaluation | INCART | I56 | 24 | 0 | 0 | 3 | 2 | 0 | 0 |
| Evaluation | INCART | I65 | 28 | 3 | 0 | 76 | 70 | 2 | 9 |
| Evaluation | INCART | I66 | 28 | 7 | 0 | 36 | 34 | 4 | 41 |
| Evaluation | INCART | I67 | 28 | 2 | 0 | 58 | 57 | 1 | 7 |
| Evaluation | INCART | I72 | 31 | 3 | 0 | 28 | 26 | 5 | 5 |
| Evaluation | INCART | I73 | 31 | 2 | 0 | 7 | 7 | 0 | 0 |
| Evaluation | INCART | I74 | 32 | 2 | 0 | 9 | 9 | 10 | 35 |
| Evaluation | INCART | I75 | 32 | 1 | 0 | 1 | 1 | 0 | 0 |
| Evaluation | MITBIH | 100 | 100 | 0 | 0 | 0 | 0 | 0 | 0 |
| Evaluation | MITBIH | 106 | 106 | 7 | 0 | 42 | 42 | 0 | 2 |
| Evaluation | MITBIH | 109 | 109 | 0 | 0 | 6 | 1 | 0 | 0 |
| Evaluation | MITBIH | 111 | 111 | 0 | 0 | 1 | 1 | 0 | 12 |
| Evaluation | MITBIH | 112 | 112 | 0 | 0 | 0 | 0 | 7 | 14 |
| Evaluation | MITBIH | 116 | 116 | 1 | 0 | 0 | 0 | 1 | 3 |
| Evaluation | MITBIH | 118 | 118 | 0 | 0 | 12 | 0 | 0 | 0 |
| Evaluation | MITBIH | 121 | 121 | 0 | 0 | 1 | 1 | 2 | 5 |
| Evaluation | MITBIH | 122 | 122 | 0 | 0 | 0 | 0 | 0 | 0 |
| Evaluation | MITBIH | 124 | 124 | 0 | 0 | 5 | 4 | 0 | 1 |
| Evaluation | MITBIH | 202 | 202 | 0 | 0 | 0 | 0 | 19 | 22 |
| Evaluation | MITBIH | 203 | 203 | 39 | 0 | 17 | 12 | 89 | 95 |
| Evaluation | MITBIH | 208 | 208 | 3 | 0 | 9 | 9 | 0 | 3 |
| Evaluation | MITBIH | 210 | 210 | 4 | 0 | 57 | 52 | 5 | 7 |
| Evaluation | MITBIH | 215 | 215 | 3 | 0 | 31 | 29 | 0 | 0 |
| Evaluation | MITBIH | 231 | 231 | 0 | 0 | 0 | 0 | 0 | 53 |
