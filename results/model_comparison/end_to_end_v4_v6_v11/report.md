# Fair FP32 detector-window comparison: V4/V6/V11

Original Development only; ungated, adaptive evaluation, not independent or OOF. Same native detector centers and ECG windows, final models at locked thresholds. Only V4 inference added; V6/V11 stage-old metrics reused after detector reference/miss count checks.

| Dataset | Model | Precision | Recall | F1 | TP | FP | FN | TN | FP/1000 N |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | V4 | 64.40% | 89.39% | 74.86% | 1163 | 643 | 138 | 10507 | 57.58 |
| MITBIH | V6 | 97.26% | 92.77% | 94.96% | 1207 | 34 | 94 | 11105 | 3.04 |
| MITBIH | V11 | 96.17% | 94.70% | 95.43% | 1232 | 49 | 69 | 11106 | 4.39 |
| INCART | V4 | 95.89% | 91.89% | 93.85% | 2844 | 122 | 251 | 21503 | 5.56 |
| INCART | V6 | 95.85% | 98.38% | 97.10% | 3045 | 132 | 50 | 21601 | 6.02 |
| INCART | V11 | 90.34% | 98.45% | 94.22% | 3047 | 326 | 48 | 21555 | 14.87 |

Missing V are FN; missed N remain reported abstentions, never TN. Same detector missing counts for every model: MIT34N+14V; INCART324N+19V. Matching includes OTHER beat symbols; predictions on matched OTHER excluded, never relabeled Normal. Unmatched does not establish noise: outside-scope annotations/rhythm, localization, T/P and unannotated events remain possible. Neither raw lead-off nor real RTOS/gap/age data are available; no fabricated hardware quality gate. No claim of complete firmware equivalence.

Per record, patient/group and occupied fold bins are in evaluation.json. Fold bins are descriptive subsets of Development, not new independent CV. V4/V6/V11 all used this Development in checkpoint/threshold selection; label exposure differs between datasets/models. Fixed-model protocol fairness does not imply equal independent training selection or unbiased generalization.

## Conclusion

V11 exceeds V4 F1 and Recall on both sources, but does not exceed V6 F1 on both.
Against V6, MIT-BIH F1 increases0.47 percentage points and Recall1.92 points,
while FP increases34→49. INCART Recall increases only0.065 points (2 additional
PVCs), while FP increases132→326 and F1 drops2.88 points. V6 is the stronger
balanced end-to-end baseline here; V11 is not a consistent overall winner.
V11 remains suitable for separately scoped static INT8/ESP32 golden arithmetic
tests, not prioritized live deployment or claims of superior end-to-end quality.
No model choice can be finalized from this repeatedly used Development cohort.

## Per-record and patient results

| Dataset | Record | Patient/group | Model | P | R | F1 | TP | FP | FN | FP/1000 N |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| INCART | I08 | 4 | V11 | 67.99% | 97.44% | 80.09% | 342 | 161 | 9 | 90.60 |
| INCART | I08 | 4 | V4 | 93.75% | 85.47% | 89.42% | 300 | 20 | 51 | 11.25 |
| INCART | I08 | 4 | V6 | 83.74% | 96.87% | 89.83% | 340 | 66 | 11 | 37.14 |
| INCART | I33 | 15 | V11 | 0.00% | 0.00% | 0.00% | 0 | 6 | 1 | 4.82 |
| INCART | I33 | 15 | V4 | 50.00% | 100.00% | 66.67% | 1 | 1 | 0 | 0.80 |
| INCART | I33 | 15 | V6 | 33.33% | 100.00% | 50.00% | 1 | 2 | 0 | 1.61 |
| INCART | I34 | 15 | V11 | 0.00% | 0.00% | 0.00% | 0 | 8 | 0 | 5.60 |
| INCART | I34 | 15 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 | 0.00 |
| INCART | I34 | 15 | V6 | 0.00% | 0.00% | 0.00% | 0 | 2 | 0 | 1.40 |
| INCART | I44 | 20 | V11 | 99.85% | 99.85% | 99.85% | 683 | 1 | 1 | 0.55 |
| INCART | I44 | 20 | V4 | 100.00% | 99.71% | 99.85% | 682 | 0 | 2 | 0.00 |
| INCART | I44 | 20 | V6 | 100.00% | 99.85% | 99.93% | 683 | 0 | 1 | 0.00 |
| INCART | I45 | 20 | V11 | 100.00% | 98.98% | 99.49% | 486 | 0 | 5 | 0.00 |
| INCART | I45 | 20 | V4 | 100.00% | 99.39% | 99.69% | 488 | 0 | 3 | 0.00 |
| INCART | I45 | 20 | V6 | 100.00% | 99.59% | 99.80% | 489 | 0 | 2 | 0.00 |
| INCART | I46 | 20 | V11 | 95.19% | 98.58% | 96.86% | 416 | 21 | 6 | 9.41 |
| INCART | I46 | 20 | V4 | 97.87% | 97.87% | 97.87% | 413 | 9 | 9 | 4.03 |
| INCART | I46 | 20 | V6 | 97.64% | 98.10% | 97.87% | 414 | 10 | 8 | 4.48 |
| INCART | I57 | 25 | V11 | 45.00% | 85.71% | 59.02% | 18 | 22 | 3 | 7.74 |
| INCART | I57 | 25 | V4 | 85.00% | 80.95% | 82.93% | 17 | 3 | 4 | 1.06 |
| INCART | I57 | 25 | V6 | 69.23% | 85.71% | 76.60% | 18 | 8 | 3 | 2.81 |
| INCART | I58 | 25 | V11 | 21.82% | 100.00% | 35.82% | 12 | 43 | 0 | 18.59 |
| INCART | I58 | 25 | V4 | 92.31% | 100.00% | 96.00% | 12 | 1 | 0 | 0.43 |
| INCART | I58 | 25 | V6 | 33.33% | 100.00% | 50.00% | 12 | 24 | 0 | 10.38 |
| INCART | I65 | 28 | V11 | 97.64% | 97.38% | 97.51% | 372 | 9 | 10 | 3.96 |
| INCART | I65 | 28 | V4 | 88.86% | 79.32% | 83.82% | 303 | 38 | 79 | 16.72 |
| INCART | I65 | 28 | V6 | 99.20% | 97.38% | 98.28% | 372 | 3 | 10 | 1.32 |
| INCART | I66 | 28 | V11 | 80.59% | 95.50% | 87.41% | 191 | 46 | 9 | 21.51 |
| INCART | I66 | 28 | V4 | 96.32% | 78.50% | 86.50% | 157 | 6 | 43 | 2.81 |
| INCART | I66 | 28 | V6 | 95.00% | 95.00% | 95.00% | 190 | 10 | 10 | 4.68 |
| INCART | I67 | 28 | V11 | 98.32% | 99.25% | 98.78% | 527 | 9 | 4 | 3.69 |
| INCART | I67 | 28 | V4 | 91.46% | 88.70% | 90.06% | 471 | 44 | 60 | 18.05 |
| INCART | I67 | 28 | V6 | 98.69% | 99.06% | 98.87% | 526 | 7 | 5 | 2.87 |
| MITBIH | 115 | 115 | V11 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 | 0.00 |
| MITBIH | 115 | 115 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 | 0.00 |
| MITBIH | 115 | 115 | V6 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 | 0.00 |
| MITBIH | 118 | 118 | V11 | 50.00% | 25.00% | 33.33% | 4 | 4 | 12 | 0.00 |
| MITBIH | 118 | 118 | V4 | 50.00% | 25.00% | 33.33% | 4 | 4 | 12 | 0.00 |
| MITBIH | 118 | 118 | V6 | 100.00% | 25.00% | 40.00% | 4 | 0 | 12 | 0.00 |
| MITBIH | 121 | 121 | V11 | 5.88% | 100.00% | 11.11% | 1 | 16 | 0 | 8.60 |
| MITBIH | 121 | 121 | V4 | 0.00% | 0.00% | 0.00% | 0 | 61 | 1 | 32.78 |
| MITBIH | 121 | 121 | V6 | 0.00% | 0.00% | 0.00% | 0 | 7 | 1 | 3.76 |
| MITBIH | 210 | 210 | V11 | 95.26% | 93.30% | 94.27% | 181 | 9 | 13 | 3.71 |
| MITBIH | 210 | 210 | V4 | 91.10% | 68.56% | 78.24% | 133 | 13 | 61 | 5.37 |
| MITBIH | 210 | 210 | V6 | 99.39% | 84.54% | 91.36% | 164 | 1 | 30 | 0.41 |
| MITBIH | 214 | 214 | V11 | 99.11% | 86.72% | 92.50% | 222 | 2 | 34 | 0.00 |
| MITBIH | 214 | 214 | V4 | 99.51% | 79.69% | 88.50% | 204 | 1 | 52 | 0.00 |
| MITBIH | 214 | 214 | V6 | 99.53% | 83.59% | 90.87% | 214 | 1 | 42 | 0.00 |
| MITBIH | 233 | 233 | V11 | 97.97% | 98.80% | 98.38% | 821 | 17 | 10 | 7.62 |
| MITBIH | 233 | 233 | V4 | 59.31% | 98.92% | 74.15% | 822 | 564 | 9 | 252.91 |
| MITBIH | 233 | 233 | V6 | 97.16% | 98.92% | 98.03% | 822 | 24 | 9 | 10.76 |
| MITBIH | 234 | 234 | V11 | 75.00% | 100.00% | 85.71% | 3 | 1 | 0 | 0.37 |
| MITBIH | 234 | 234 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 3 | 0.00 |
| MITBIH | 234 | 234 | V6 | 75.00% | 100.00% | 85.71% | 3 | 1 | 0 | 0.37 |

## Fold bins

| Dataset | Fold | Model | Precision | Recall | F1 | TP | FP | FN | FP/1000 N |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | 1 | V4 | 63.72% | 64.93% | 64.32% | 137 | 78 | 74 | 18.21 |
| MITBIH | 2 | V4 | 64.49% | 94.13% | 76.54% | 1026 | 565 | 64 | 82.09 |
| MITBIH | 1 | V6 | 95.45% | 79.62% | 86.82% | 168 | 8 | 43 | 1.87 |
| MITBIH | 2 | V6 | 97.56% | 95.32% | 96.43% | 1039 | 26 | 51 | 3.78 |
| MITBIH | 1 | V11 | 86.51% | 88.15% | 87.32% | 186 | 29 | 25 | 6.77 |
| MITBIH | 2 | V11 | 98.12% | 95.96% | 97.03% | 1046 | 20 | 44 | 2.91 |
| INCART | 0 | V4 | 91.36% | 83.65% | 87.34% | 931 | 88 | 182 | 12.85 |
| INCART | 2 | V4 | 99.37% | 99.12% | 99.25% | 1584 | 10 | 14 | 1.23 |
| INCART | 3 | V4 | 87.88% | 87.88% | 87.88% | 29 | 4 | 4 | 0.78 |
| INCART | 4 | V4 | 93.75% | 85.47% | 89.42% | 300 | 20 | 51 | 11.25 |
| INCART | 0 | V6 | 98.19% | 97.75% | 97.97% | 1088 | 20 | 25 | 2.92 |
| INCART | 2 | V6 | 99.13% | 99.31% | 99.22% | 1587 | 14 | 11 | 1.72 |
| INCART | 3 | V6 | 48.39% | 90.91% | 63.16% | 30 | 32 | 3 | 6.21 |
| INCART | 4 | V6 | 83.74% | 96.87% | 89.83% | 340 | 66 | 11 | 37.14 |
| INCART | 0 | V11 | 94.45% | 97.93% | 96.16% | 1090 | 64 | 23 | 9.34 |
| INCART | 2 | V11 | 97.78% | 99.19% | 98.48% | 1585 | 36 | 13 | 4.42 |
| INCART | 3 | V11 | 31.58% | 90.91% | 46.88% | 30 | 65 | 3 | 12.61 |
| INCART | 4 | V11 | 67.99% | 97.44% | 80.09% | 342 | 161 | 9 | 90.60 |
