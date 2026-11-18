# V10 Research — Step 1: 5-Fold Group Cross-Validation

Only MIT-BIH Train+Validation and INCART Train+Validation were used. Each
iteration uses one outer fold for evaluation, one disjoint fold for checkpoint
selection by PR-AUC, one disjoint fold for threshold calibration by F1, and the
remaining two folds for fitting. No Test or third dataset was used.

Values are mean ± population standard deviation across five outer folds.

| Model | Dataset | Precision | Recall | F1 | PR-AUC | FP / 1,000 N | Worst-fold F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| V4 | MIT-BIH | 73.00 ± 13.67% | 78.03 ± 17.63% | 74.41 ± 13.86% | 81.58 ± 15.31% | 29.36 ± 19.05 | 53.69% (fold 1) |
| V4 | INCART | 85.55 ± 4.78% | 68.92 ± 27.90% | 72.42 ± 21.75% | 82.44 ± 11.32% | 15.43 ± 8.89 | 32.11% (fold 4) |
| V6 | MIT-BIH | 81.20 ± 19.11% | 93.15 ± 3.53% | 85.46 ± 13.04% | 93.49 ± 6.42% | 28.35 ± 37.61 | 60.92% (fold 1) |
| V6 | INCART | 82.44 ± 23.66% | 84.47 ± 19.15% | 78.91 ± 17.51% | 96.40 ± 3.42% | 44.63 ± 73.57 | 52.05% (fold 1) |

All ten checkpoint hashes match the hashes stored with their fold results.
Group-role intersections are empty in every fold for both datasets.

V6 has higher mean F1/PR-AUC and lower F1 variability, especially stronger and
more stable recall. It is not uniformly safer: its precision and false-positive
rate vary substantially, with INCART FP/1,000 N worse than V4. The strongest
evidence is therefore score/operating-point instability across patient groups,
not simply inadequate positive-class weighting. For V10, prioritize
normalization/regularization and calibration robustness before changing loss or
class weights.
