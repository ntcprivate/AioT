# V10-B Dual-Scale Normalization

All five checkpoint hashes and all group-role intersections verified. Runtime: see runtime.json. Outer results were previously inspected to motivate this experiment; adaptive evaluation, not independent confirmation.

| Dataset | Model | Precision | Recall | F1 | PR-AUC (AP) | FP/1000 N | Worst fold F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| MITBIH | V6 | 81.20 ± 19.11% | 93.15 ± 3.53% | 85.46 ± 13.04% | 93.49 ± 6.42% | 28.35 ± 37.61 | 60.92% (fold 1) |
| MITBIH | V10-A | 79.10 ± 18.76% | 96.68 ± 1.90% | 85.85 ± 12.92% | 94.17 ± 5.89% | 30.87 ± 34.48 | 63.70% (fold 1) |
| MITBIH | V10-B | 71.56 ± 22.93% | 94.97 ± 3.48% | 79.69 ± 14.76% | 94.43 ± 4.64% | 45.79 ± 36.90 | 63.17% (fold 2) |
| INCART | V6 | 82.44 ± 23.66% | 84.47 ± 19.15% | 78.91 ± 17.51% | 96.40 ± 3.42% | 44.63 ± 73.57 | 52.05% (fold 1) |
| INCART | V10-A | 81.64 ± 25.52% | 84.76 ± 19.47% | 78.03 ± 19.31% | 94.94 ± 4.70% | 54.25 ± 93.71 | 46.99% (fold 1) |
| INCART | V10-B | 83.68 ± 27.20% | 88.01 ± 10.01% | 82.19 ± 19.77% | 94.92 ± 6.14% | 52.90 ± 98.85 | 44.48% (fold 1) |