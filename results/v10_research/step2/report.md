# V10 Research — Step 2: V10-A

V10-A keeps the 1,969-parameter V6 architecture and adds
`SpatialDropout1D(0.1)` after the final convolution in each branch. It uses the
five locked Step-1 group folds with disjoint Fit, Checkpoint Selection,
Threshold Calibration, and Outer Evaluation roles. No Test or third dataset was
accessed. Values are mean ± population standard deviation over outer folds.

| Model | Dataset | Precision | Recall | F1 | PR-AUC | FP / 1,000 N | Worst-fold F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| V6 | MIT-BIH | 81.20 ± 19.11% | 93.15 ± 3.53% | 85.46 ± 13.04% | 93.49 ± 6.42% | 28.35 ± 37.61 | 60.92% |
| V10-A | MIT-BIH | 79.10 ± 18.76% | 96.68 ± 1.90% | 85.85 ± 12.92% | 94.17 ± 5.89% | 30.87 ± 34.48 | 63.70% |
| V6 | INCART | 82.44 ± 23.66% | 84.47 ± 19.15% | 78.91 ± 17.51% | 96.40 ± 3.42% | 44.63 ± 73.57 | 52.05% |
| V10-A | INCART | 81.64 ± 25.52% | 84.76 ± 19.47% | 78.03 ± 19.31% | 94.94 ± 4.70% | 54.25 ± 93.71 | 46.99% |

Relative to V6, V10-A changes recall by +3.53 percentage points on MIT-BIH and
0.30 points on INCART, but FP/1,000 N increases by 2.52 and 9.62 respectively.
INCART F1, PR-AUC, worst-fold F1, and variability also worsen. Spatial dropout
alone therefore does not improve both datasets and does not meet the objective
of reducing false positives while retaining recall. Keep V6 as the stronger
baseline and proceed, if approved, to the separately scoped normalization
experiment V10-B.
