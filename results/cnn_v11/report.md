# V11 CNN + causal RR

Annotation-derived RR; timing oracle, not detector end-to-end evidence. Adaptive research CV; outer groups have been inspected in previous experiments. No Test used.

| Dataset | Model | Precision | Recall | F1 | AP | FP/1000 N | Worst F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| MITBIH | V4 | 73.00 ± 13.67% | 78.03 ± 17.63% | 74.41 ± 13.86% | 81.58 ± 15.31% | 29.36 ± 19.05 | 53.69% |
| MITBIH | V6 | 81.20 ± 19.11% | 93.15 ± 3.53% | 85.46 ± 13.04% | 93.49 ± 6.42% | 28.35 ± 37.61 | 60.92% |
| MITBIH | V11 | 86.44 ± 14.03% | 94.03 ± 7.90% | 89.13 ± 8.96% | 97.26 ± 3.16% | 17.59 ± 22.36 | 73.68% |
| INCART | V4 | 85.55 ± 4.78% | 68.92 ± 27.90% | 72.42 ± 21.75% | 82.44 ± 11.32% | 15.43 ± 8.89 | 32.11% |
| INCART | V6 | 82.44 ± 23.66% | 84.47 ± 19.15% | 78.91 ± 17.51% | 96.40 ± 3.42% | 44.63 ± 73.57 | 52.05% |
| INCART | V11 | 87.28 ± 21.98% | 94.58 ± 8.39% | 88.51 ± 14.77% | 99.33 ± 0.55% | 31.51 ± 58.24 | 60.26% |

## Fixed RR perturbations

These perturbations isolate model dependence on RR; they do not simulate the full set of missed/extra detector peaks.
MITBIH missing: mean F1=65.56%, recall=59.15%, FP/1000 N=2.51
MITBIH jitter: mean F1=87.68%, recall=93.64%, FP/1000 N=20.25
INCART missing: mean F1=65.77%, recall=65.44%, FP/1000 N=22.91
INCART jitter: mean F1=88.04%, recall=94.05%, FP/1000 N=32.02