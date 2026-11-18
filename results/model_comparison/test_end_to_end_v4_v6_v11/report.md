# V4/V6/V11 FP32 Test end-to-end comparison

Retrospective comparison on previously inspected Test. Frozen checkpoints/thresholds. Only V4/V6 inference added; V11 stored predictions reused and per-record confusion counts reproduced exactly. Same native detector centers, reconstructed raw windows and greedy tolerance38 matching. Ungated; no fabricated lead-off/RTOS/quality recovery simulation. Not independent confirmatory evidence.

| Dataset | Model | Precision | Recall PVC | F1 | TP | FP | FN | TN | FP/1000 reference N |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | V4 | 72.91% | 84.75% | 78.39% | 767 | 285 | 138 | 9516 | 27.45 |
| MITBIH | V6 | 21.13% | 84.20% | 33.78% | 762 | 2845 | 143 | 9140 | 274.03 |
| MITBIH | V11 | 24.96% | 90.06% | 39.09% | 815 | 2450 | 90 | 9592 | 235.99 |
| INCART | V4 | 92.22% | 66.53% | 77.30% | 2218 | 187 | 1116 | 22565 | 8.10 |
| INCART | V6 | 41.76% | 76.81% | 54.10% | 2561 | 3572 | 773 | 22281 | 154.69 |
| INCART | V11 | 45.41% | 82.84% | 58.67% | 2762 | 3320 | 572 | 22682 | 143.77 |

Unmatched alarms are scored FP but not proven noise: T/P, localization, rhythm/outside annotation scope or unannotated real events remain possible. OTHER beat matches are not relabeled N; only N/V classification scored. Missed V retained FN. Missed N reported separately and not TN; event ledger is not a fixed binary population. MIT missed688N/56V with2955 unmatched peaks; INC missed361N/366V with3443 unmatched. No quality-gated deployment claim.

FP/1000 reference N uses all raw annotated N in these records:10382 MIT-BIH,
23092 INCART. Older V11 final report used retained offline-window N counts
10374/23081 for this particular denominator. This report standardizes that
denominator for all three models; TP/FP/FN/TN and F1 for V11 remain unchanged.

## Findings and candidate priority

V4 has the highest F1 and lowest FP on both datasets: MIT-BIH F1 78.39%,
INCART77.30%. V11 has the highest PVC recall:90.06%/82.84%, but many unmatched
PVC alarms. V6 does not outperform either model consistently on these Test
records. V4 is relatively consistent in F1 and controls extra-event alarms,
but INCART recall66.53% is a substantial limitation, so none is a demonstrated
fully adequate deployed system.

Unmatched PVC alarms MIT-BIH:V4=107,V6=2291,V11=2348; INCART:V4=21,V6=3122,
V11=3271. V6/V11 alarms concentrate on MIT113 and INCART I63/I64(patient27).
V4 has zero FP on MIT113,3 on117 and most MIT FP on108(250); INCART most V4 FP are
I70(patient30,86) and I18(patient9,42). These are observed error concentrations,
not instructions for Test-driven model/detector tuning. Unmatched alarm
categories remain unresolved physiologically without adjudication.

Prioritize V4 as the conservative technical reference for an ESP32 verification
exercise, while preserving V11 as an optional two-input golden/parity candidate.
This is a retrospective engineering prioritization, not an independent model
selection result or authorization for clinical/live deployment. Do not optimize
models, thresholds or detector from this Test comparison. Further confirmatory
performance work needs an untouched cohort and a frozen full quality-gate
pipeline. No firmware modification/flash performed.

## Per-record FP decomposition

| Dataset | Record | Patient/group | Model | Precision | Recall | F1 | FP N matched | FP unmatched alarm | FN |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| INCART | I18 | 9 | V11 | 95.62% | 95.36% | 95.49% | 2 | 14 | 17 |
| INCART | I18 | 9 | V4 | 88.71% | 90.16% | 89.43% | 39 | 3 | 36 |
| INCART | I18 | 9 | V6 | 97.98% | 92.90% | 95.37% | 2 | 5 | 26 |
| INCART | I19 | 9 | V11 | 99.03% | 96.24% | 97.61% | 1 | 7 | 32 |
| INCART | I19 | 9 | V4 | 98.14% | 68.24% | 80.50% | 7 | 4 | 270 |
| INCART | I19 | 9 | V6 | 99.83% | 71.18% | 83.10% | 0 | 1 | 245 |
| INCART | I20 | 10 | V11 | 86.21% | 90.09% | 88.11% | 0 | 16 | 11 |
| INCART | I20 | 10 | V4 | 100.00% | 41.44% | 58.60% | 0 | 0 | 65 |
| INCART | I20 | 10 | V6 | 89.09% | 88.29% | 88.69% | 0 | 12 | 13 |
| INCART | I21 | 10 | V11 | 16.67% | 100.00% | 28.57% | 0 | 40 | 0 |
| INCART | I21 | 10 | V4 | 100.00% | 75.00% | 85.71% | 0 | 0 | 2 |
| INCART | I21 | 10 | V6 | 21.21% | 87.50% | 34.15% | 0 | 26 | 1 |
| INCART | I22 | 10 | V11 | 91.80% | 90.81% | 91.30% | 0 | 15 | 17 |
| INCART | I22 | 10 | V4 | 94.19% | 43.78% | 59.78% | 4 | 1 | 104 |
| INCART | I22 | 10 | V6 | 94.92% | 90.81% | 92.82% | 0 | 9 | 17 |
| INCART | I38 | 17 | V11 | 99.06% | 97.06% | 98.05% | 1 | 4 | 16 |
| INCART | I38 | 17 | V4 | 99.71% | 63.67% | 77.72% | 0 | 1 | 198 |
| INCART | I38 | 17 | V6 | 99.23% | 94.13% | 96.61% | 0 | 4 | 32 |
| INCART | I39 | 17 | V11 | 92.77% | 98.40% | 95.50% | 2 | 22 | 5 |
| INCART | I39 | 17 | V4 | 98.22% | 88.18% | 92.93% | 0 | 5 | 37 |
| INCART | I39 | 17 | V6 | 96.15% | 95.85% | 96.00% | 0 | 12 | 13 |
| INCART | I62 | 27 | V11 | 90.05% | 45.53% | 60.48% | 4 | 36 | 433 |
| INCART | I62 | 27 | V4 | 99.78% | 56.60% | 72.23% | 0 | 1 | 345 |
| INCART | I62 | 27 | V6 | 95.85% | 55.22% | 70.07% | 0 | 19 | 356 |
| INCART | I63 | 27 | V11 | 7.16% | 76.09% | 13.09% | 0 | 1361 | 33 |
| INCART | I63 | 27 | V4 | 98.88% | 63.77% | 77.53% | 0 | 1 | 50 |
| INCART | I63 | 27 | V6 | 5.64% | 57.25% | 10.27% | 0 | 1321 | 59 |
| INCART | I64 | 27 | V11 | 0.85% | 65.22% | 1.68% | 0 | 1749 | 8 |
| INCART | I64 | 27 | V4 | 87.50% | 60.87% | 71.79% | 1 | 1 | 9 |
| INCART | I64 | 27 | V6 | 0.70% | 52.17% | 1.38% | 1 | 1708 | 11 |
| INCART | I70 | 30 | V11 | 0.00% | 0.00% | 0.00% | 6 | 4 | 0 |
| INCART | I70 | 30 | V4 | 0.00% | 0.00% | 0.00% | 82 | 4 | 0 |
| INCART | I70 | 30 | V6 | 0.00% | 0.00% | 0.00% | 313 | 3 | 0 |
| INCART | I71 | 30 | V11 | 0.00% | 0.00% | 0.00% | 33 | 3 | 0 |
| INCART | I71 | 30 | V4 | 0.00% | 0.00% | 0.00% | 33 | 0 | 0 |
| INCART | I71 | 30 | V6 | 0.00% | 0.00% | 0.00% | 134 | 2 | 0 |
| MITBIH | 107 | 107 | V11 | 100.00% | 32.20% | 48.72% | 0 | 0 | 40 |
| MITBIH | 107 | 107 | V4 | 100.00% | 40.68% | 57.83% | 0 | 0 | 35 |
| MITBIH | 107 | 107 | V6 | 100.00% | 30.51% | 46.75% | 0 | 0 | 41 |
| MITBIH | 108 | 108 | V11 | 7.06% | 70.59% | 12.83% | 67 | 91 | 5 |
| MITBIH | 108 | 108 | V4 | 3.10% | 47.06% | 5.82% | 154 | 96 | 9 |
| MITBIH | 108 | 108 | V6 | 1.11% | 41.18% | 2.16% | 545 | 79 | 10 |
| MITBIH | 113 | 113 | V11 | 0.00% | 0.00% | 0.00% | 0 | 1580 | 0 |
| MITBIH | 113 | 113 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 | 0 |
| MITBIH | 113 | 113 | V6 | 0.00% | 0.00% | 0.00% | 0 | 1576 | 0 |
| MITBIH | 117 | 117 | V11 | 0.00% | 0.00% | 0.00% | 0 | 597 | 0 |
| MITBIH | 117 | 117 | V4 | 0.00% | 0.00% | 0.00% | 2 | 1 | 0 |
| MITBIH | 117 | 117 | V6 | 0.00% | 0.00% | 0.00% | 0 | 595 | 0 |
| MITBIH | 123 | 123 | V11 | 50.00% | 100.00% | 66.67% | 0 | 3 | 0 |
| MITBIH | 123 | 123 | V4 | 100.00% | 100.00% | 100.00% | 0 | 0 | 0 |
| MITBIH | 123 | 123 | V6 | 50.00% | 100.00% | 66.67% | 0 | 3 | 0 |
| MITBIH | 200 | 200 | V11 | 97.38% | 94.55% | 95.95% | 6 | 15 | 45 |
| MITBIH | 200 | 200 | V4 | 98.79% | 88.62% | 93.43% | 4 | 5 | 94 |
| MITBIH | 200 | 200 | V6 | 97.61% | 88.86% | 93.03% | 8 | 10 | 92 |
| MITBIH | 222 | 222 | V11 | 0.00% | 0.00% | 0.00% | 29 | 62 | 0 |
| MITBIH | 222 | 222 | V4 | 0.00% | 0.00% | 0.00% | 18 | 5 | 0 |
| MITBIH | 222 | 222 | V6 | 0.00% | 0.00% | 0.00% | 1 | 28 | 0 |

## Patient/record groups

| Dataset | Group | Model | Precision | Recall | F1 | FP | FN |
|---|---|---|---:|---:|---:|---:|---:|
| MITBIH | 107 | V4 | 100.00% | 40.68% | 57.83% | 0 | 35 |
| MITBIH | 107 | V6 | 100.00% | 30.51% | 46.75% | 0 | 41 |
| MITBIH | 107 | V11 | 100.00% | 32.20% | 48.72% | 0 | 40 |
| MITBIH | 108 | V4 | 3.10% | 47.06% | 5.82% | 250 | 9 |
| MITBIH | 108 | V6 | 1.11% | 41.18% | 2.16% | 624 | 10 |
| MITBIH | 108 | V11 | 7.06% | 70.59% | 12.83% | 158 | 5 |
| MITBIH | 113 | V4 | 0.00% | 0.00% | 0.00% | 0 | 0 |
| MITBIH | 113 | V6 | 0.00% | 0.00% | 0.00% | 1576 | 0 |
| MITBIH | 113 | V11 | 0.00% | 0.00% | 0.00% | 1580 | 0 |
| MITBIH | 117 | V4 | 0.00% | 0.00% | 0.00% | 3 | 0 |
| MITBIH | 117 | V6 | 0.00% | 0.00% | 0.00% | 595 | 0 |
| MITBIH | 117 | V11 | 0.00% | 0.00% | 0.00% | 597 | 0 |
| MITBIH | 123 | V4 | 100.00% | 100.00% | 100.00% | 0 | 0 |
| MITBIH | 123 | V6 | 50.00% | 100.00% | 66.67% | 3 | 0 |
| MITBIH | 123 | V11 | 50.00% | 100.00% | 66.67% | 3 | 0 |
| MITBIH | 200 | V4 | 98.79% | 88.62% | 93.43% | 9 | 94 |
| MITBIH | 200 | V6 | 97.61% | 88.86% | 93.03% | 18 | 92 |
| MITBIH | 200 | V11 | 97.38% | 94.55% | 95.95% | 21 | 45 |
| MITBIH | 222 | V4 | 0.00% | 0.00% | 0.00% | 23 | 0 |
| MITBIH | 222 | V6 | 0.00% | 0.00% | 0.00% | 29 | 0 |
| MITBIH | 222 | V11 | 0.00% | 0.00% | 0.00% | 91 | 0 |
| INCART | 10 | V4 | 96.38% | 43.75% | 60.18% | 5 | 171 |
| INCART | 10 | V6 | 85.31% | 89.80% | 87.50% | 47 | 31 |
| INCART | 10 | V11 | 79.54% | 90.79% | 84.79% | 71 | 28 |
| INCART | 17 | V4 | 99.05% | 72.61% | 83.79% | 6 | 235 |
| INCART | 17 | V6 | 98.07% | 94.76% | 96.38% | 16 | 45 |
| INCART | 17 | V11 | 96.65% | 97.55% | 97.10% | 29 | 21 |
| INCART | 27 | V4 | 99.28% | 57.74% | 73.02% | 4 | 404 |
| INCART | 27 | V6 | 14.81% | 55.44% | 23.37% | 3049 | 426 |
| INCART | 27 | V11 | 13.27% | 50.42% | 21.01% | 3150 | 474 |
| INCART | 30 | V4 | 0.00% | 0.00% | 0.00% | 119 | 0 |
| INCART | 30 | V6 | 0.00% | 0.00% | 0.00% | 452 | 0 |
| INCART | 30 | V11 | 0.00% | 0.00% | 0.00% | 46 | 0 |
| INCART | 9 | V4 | 94.50% | 74.84% | 83.52% | 53 | 306 |
| INCART | 9 | V6 | 99.16% | 77.71% | 87.14% | 8 | 271 |
| INCART | 9 | V11 | 97.98% | 95.97% | 96.97% | 24 | 49 |
