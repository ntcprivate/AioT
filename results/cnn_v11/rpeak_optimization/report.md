# Controlled detector confirmation experiment

No Test accessed. Firmware unchanged. Final V11 threshold 0.80; V6 threshold 0.87. Old/new share current native peak stream. New is a causal slope confirmation gate after window completion; RR recomputed from accepted peaks. Only one candidate, rejected. Training traces were used for diagnosis; final end-to-end uses original Development only, with final models selected on these Development groups, not OOF or independent evidence.

| Dataset | Stage/model | Precision | Recall | F1 | TP | FP | FN | TN | Peak sensitivity | Peak PPV |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | old_V6 | 97.26% | 92.77% | 94.96% | 1207 | 34 | 94 | 11105 | 99.661% | 99.822% |
| MITBIH | old_V11 | 96.17% | 94.70% | 95.43% | 1232 | 49 | 69 | 11106 | 99.661% | 99.822% |
| MITBIH | candidate_V6 | 97.39% | 88.93% | 92.97% | 1157 | 31 | 144 | 11105 | 99.270% | 99.892% |
| MITBIH | candidate_V11 | 97.19% | 90.24% | 93.58% | 1174 | 34 | 127 | 11109 | 99.270% | 99.892% |
| INCART | old_V6 | 95.85% | 98.38% | 97.10% | 3045 | 132 | 50 | 21601 | 98.641% | 97.982% |
| INCART | old_V11 | 90.34% | 98.45% | 94.22% | 3047 | 326 | 48 | 21555 | 98.641% | 97.982% |
| INCART | candidate_V6 | 97.40% | 72.57% | 83.17% | 2246 | 60 | 849 | 21595 | 95.498% | 98.488% |
| INCART | candidate_V11 | 91.62% | 72.41% | 80.89% | 2241 | 205 | 854 | 21559 | 95.498% | 98.488% |

## Evidence and limits

Across Train+Development traces, 18,775 MIT-BIH and 4,761 INCART detected matches are OTHER beats, not unmatched false peaks. Matching includes all BEATS symbols, tolerance 38 samples. There are 483/8,319 unmatched peaks; 189/4,265 lie within 75 samples of a reference. Temporal proximity is evidence of nearby mislocalization/secondary events, not proof of double detection or T/P morphology. Native detector uses absolute baseline-removed magnitude and no explicit QRS slope confirmation. The slope gate rejects many true PVCs, so low-slope candidates cannot safely be called T waves.

Unmatched peaks may include unlabeled genuine beats; they are scoring-unmatched, not adjudicated noise. Distinguishing noise/T/P requires waveform adjudication not established here. Historical 22.96% missing RR was inflated by annotation-relative completion gating, as already documented. Final Test figures were not rerun or used for tuning.

All missed V included FN; missed N separately retained in record JSON and never counted TN. Unmatched PVC predictions count FP; OTHER matches excluded from N/V labels. Ungated synthetic ADC replay is not a complete firmware safety-gate or hardware validation.

## Worst available Development fold (not a new full 5-fold evaluation)
MITBIH old: fold 1, F1 87.32%.
MITBIH candidate: fold 1, F1 82.99%.
INCART old: fold 3, F1 46.88%.
INCART candidate: fold 0, F1 46.57%.

## Decision

Reject candidate: PPV improves marginally while sensitivity and PVC recall worsen. No improved detector is accepted or ready for deployment. Keep original detector and model artifacts. Current evidence does not justify further parameter search or deployment claims; morphology adjudication and separate development for QRS/T rejection are required before proposing another change.