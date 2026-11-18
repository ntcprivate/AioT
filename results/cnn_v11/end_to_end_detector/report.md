# V11 detector-window end-to-end evaluation

Original Validation/Development only: 7 MIT-BIH records and 11 INCART records.
Each record uses its held-out outer-fold V6/V11 checkpoint and locked threshold.
No model training or threshold optimization. Windows come from current native
signal.cpp detector replay, synthetic ADC mapping 2048+200 counts/mV. Full-window
z-score is computed from each detector window. RR uses only current and prior
detector centers. This is ungated detector/CNN evaluation, not the complete
firmware safety-gated system. No Test used.

Fallback was frozen before inference: use V6 with fewer than 2 prior intervals
or any RR timing feature beyond 3 Fit standard deviations. It uses saved Fit
statistics only, no annotation matching, labels, or outer error information.

Metrics below are pooled micro results on this Development cohort, unlike
previous means across all five outer folds of Train+Development.

| Dataset | Mode | Precision | Recall | F1 | TP | FP | FN | TN | FP/1000 N |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MIT-BIH | V6 | 79.37% | 94.93% | 86.45% | 1235 | 321 | 66 | 10822 | 28.75 |
| MIT-BIH | V11 | 90.45% | 97.54% | 93.86% | 1269 | 134 | 32 | 11018 | 12.00 |
| MIT-BIH | fallback | 90.64% | 97.54% | 93.97% | 1269 | 131 | 32 | 11021 | 11.73 |
| INCART | V6 | 96.80% | 96.83% | 96.82% | 2997 | 99 | 98 | 21601 | 4.51 |
| INCART | V11 | 92.96% | 98.09% | 95.46% | 3036 | 230 | 59 | 21558 | 10.49 |
| INCART | fallback | 92.95% | 98.03% | 95.42% | 3034 | 230 | 61 | 21558 | 10.49 |

All missed V are included in FN. Missed N are separately counted as abstentions,
never TN: MIT-BIH 34 N + 14 V = 48/12468 N/V missed (0.385%); INCART 324 N +
19 V = 343/25023 missed (1.371%). Across all beat symbols, misses are 57 and
356 respectively. Extra peaks are 30 and 532. PVC predictions on unmatched
peaks count FP. Matches to OTHER are excluded from N/V classification and not
relabeled Normal. Consequently TP+FP+FN+TN is not the reference N/V count:
unmatched alerts are added and missed Normal beats remain abstentions.

## Why the previous INCART missing-RR rate was inflated

The previous RR-only evaluator required emitted_sample <= annotation_center+128
while allowing localization errors up to 38 samples. A valid peak localized a
few samples after annotation finishes its window later and was incorrectly
marked missing. On this Development cohort, 1931 matched N/V beats fail that
deadline (MIT-BIH: 146). That is an evaluation association defect, not proof of
a detector missing those peaks. The previous 22.96% figure also covered a
different, larger Train+Development cohort and is not directly comparable.
This run matches completed detector windows one-to-one within 38 samples with
no annotation-relative completion deadline. Annotation is used only for
scoring. Center offsets and actual completion samples are retained per record.

Some genuine misses remain, plus many extra INCART peaks. Their exact
morphological causes have not been established by this evaluation. Do not
attribute all misses to one detector mechanism or tune it on these results.

## Decision

Fallback reduces 3 MIT-BIH FP, with no FN reduction; on INCART it adds 2 FN.
It is not a demonstrated general improvement. V11 improves MIT-BIH over V6 but
has worse INCART precision/F1 despite better recall. Neither final model lock
nor blanket replacement is supported. Retain V6 as the stable baseline; further
detector/quality-gate validation and a genuinely independent cohort are needed.
These Development results have been repeatedly examined and are adaptive,
not independent evidence of generalization.
