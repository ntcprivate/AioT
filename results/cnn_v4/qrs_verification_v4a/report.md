# V4-A QRS verification experiment

Final recommendation: **keep V4 baseline**. Aggregate gate acceptance criterion passed, but stable multi-patient benefit is not established, so promotion is FAIL. No additional gate variants or Test evaluation were run.

V4 only:849 parameters, model SHA256 36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1, threshold0.88, ECG250Hz/256 samples/window-zscore, no RR. Firmware/detector/model unchanged.

## Split and selection

37 Fit records,19 Calibration records,45 Evaluation records, disjoint MIT record/INCART patient groups (see design.json). Uses locked CV fold0 grouping: Fit folds3+4, Calibration2, Evaluation0+1. Gate family/grid/split frozen before new processing; threshold locked before Evaluation feature/inference processing. Evaluation groups were used historically in V1–V11 and some waveform examples informed the research hypothesis, so this is internally held-out gate-parameter evaluation, not a fresh independent cohort. MIT record groups are proxies, not proven distinct patients.

Gate rejects only if central48-sample squared-difference energy / strongest48-sample energy <0.05 AND strongest support center offset>40samples. It requires a dominant off-center component; no absolute slope or RR cutoff. Runtime has no annotation/label access. Candidate thresholds0,.05,.1,.2,.3. Fit allows at most0.1% matched-PVC rejection; Calibration requires zero matched-PVC rejection, no FN/F1 worsening per dataset. Threshold0.05 reduced2 calibration FP; stronger thresholds rejected PVC and were not selected.

## Evaluation — held out from gate parameter selection

| Dataset | Mode | Precision | Recall PVC | F1 | TP | FP | FN | TN | FP/1000 N | Peak sensitivity | Peak PPV | Gate-rejected PVC |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MITBIH | baseline | 60.4712% | 90.6593% | 72.5503% | 2310 | 1510 | 238 | 23348 | 60.328 | 99.1904% | 99.5698% | 0 |
| INCART | baseline | 75.6655% | 85.8527% | 80.4378% | 6026 | 1938 | 993 | 52730 | 35.382 | 97.7422% | 94.6213% | 0 |
| MITBIH | V4-A | 60.5346% | 90.6593% | 72.5959% | 2310 | 1506 | 238 | 23348 | 60.168 | 99.1904% | 99.7260% | 0 |
| INCART | V4-A | 76.3655% | 85.8527% | 80.8317% | 6026 | 1865 | 993 | 52723 | 34.049 | 97.7315% | 94.9254% | 0 |

MIT FP1510→1506, INC1938→1865. PVC recall unchanged. INC rejects7 matched N (additional missing-N abstentions), not PVC. Baseline FP source: MIT1465/1510 matched-N classification errors; INC681/1938 matched-N errors and1257 unmatched alarms. Gate does not address the dominant MIT CNN classification errors. Improvements only MIT106(2FP),112(2FP); INC I16(71FP),I17(1FP),I47(1FP). All other evaluation records have unchanged F1; no record F1 worsened. Most INC benefit is patient8.

## Diagnosis and safeguards

Train/Development waveform evidence and scope analysis reused from results/cnn_v11/unmatched_peak_analysis/. Some INCART candidates are broad T-wave-compatible events after a separately detected QRS. Other unmatched peaks may be timing errors, secondary lobes, unannotated events or rhythm-scope markers; do not call all noise. Matched OTHER count as peak TP and are excluded from N/V classification. Gate does not use labels, annotations, patient ID, CNN score or future samples beyond the ready window.

The main MIT Development FP burden is on matched Normal QRS, beyond the scope of a verification-only gate. INCART has more unmatched alarms. This distinction is reflected separately in evaluation.json. QRS validity/T/P/noise adjudication remains incomplete; gate rejection is not a physiological ground truth label.

All missed V, including gate-caused misses, are included FN. Missing N separately reported, not TN. Unmatched predicted PVC count FP. Matching is re-applied one-to-one unchanged at +/-38 samples after gating; OTHER never relabeled Normal. Peaks matching rhythm markers outside BEATS are still scope-unmatched under the unchanged metric. Synthetic ADC, ungated baseline stream; not complete firmware quality-gated performance.

## PVC safety strata

{
  "definitions": "Morphology proxies only: central128 peak-to-peak in mV; number of samples over half absolute deviation from median, not clinical QRS duration. Cutoffs from Fit only. Descriptive strata, no parameter selection.",
  "Fit_low_ptp_q10": 1.5231190560895356,
  "Fit_broad_support_q90_ms": 116.0,
  "evaluation": {
    "MITBIH": {
      "all_matched_PVC": {
        "samples": 2491,
        "rejected": 0
      },
      "low_amplitude_Fit_q10": {
        "samples": 250,
        "rejected": 0
      },
      "broad_half_amplitude_support_Fit_q90": {
        "samples": 534,
        "rejected": 0
      },
      "short_detected_RR_lt600ms": {
        "samples": 2284,
        "rejected": 0
      }
    },
    "INCART": {
      "all_matched_PVC": {
        "samples": 6937,
        "rejected": 0
      },
      "low_amplitude_Fit_q10": {
        "samples": 871,
        "rejected": 0
      },
      "broad_half_amplitude_support_Fit_q90": {
        "samples": 326,
        "rejected": 0
      },
      "short_detected_RR_lt600ms": {
        "samples": 5840,
        "rejected": 0
      }
    }
  },
  "streaming_decisions_checked": 182
}

These strata include only baseline-detected matched PVC; baseline missed PVC remain separately counted FN. Width is an amplitude-support proxy, not adjudicated QRS width. No real PVC in Evaluation was rejected; this does not prove preservation on unseen patients.

## Timing, CPU and RAM

Decision waits for existing center+127 (508ms postpeak); no additional latency beyond the ready256-sample window. FIFO candidate confirmation can be50 samples but gate requires complete window. A single streaming scan needs255 differences/squares, about460 rolling-sum operations, about208 comparisons and central support accumulation: O(256), roughly1–2k scalar operations per beat, no sqrt/trigonometry, no dynamic allocation. Comparison central<t*maximum avoids division. 48-value energy ring requires192bytes using float32, plus scalar state, reusing existing1024-byte ECG window. Current host vectorized implementation uses larger arrays; this is a proposed bounded embedded implementation, not measured ESP32 RAM/latency. Streaming decision check uses float64/integer ADC energy, so float32 embedded parity still pending. No board timing claims.

## Per-record Evaluation results

| Dataset | Record | Patient/group | Mode | F1 | TP | FP | FN | Gate PVC rejected |
|---|---|---|---|---:|---:|---:|---:|---:|
| INCART | I01 | 1 | V4-A | 28.491% | 101 | 264 | 243 | 0 |
| INCART | I01 | 1 | baseline | 28.491% | 101 | 264 | 243 | 0 |
| INCART | I02 | 1 | V4-A | 11.009% | 18 | 80 | 211 | 0 |
| INCART | I02 | 1 | baseline | 11.009% | 18 | 80 | 211 | 0 |
| INCART | I03 | 2 | V4-A | 64.039% | 65 | 13 | 60 | 0 |
| INCART | I03 | 2 | baseline | 64.039% | 65 | 13 | 60 | 0 |
| INCART | I04 | 2 | V4-A | 20.588% | 14 | 1 | 107 | 0 |
| INCART | I04 | 2 | baseline | 20.588% | 14 | 1 | 107 | 0 |
| INCART | I05 | 2 | V4-A | 76.174% | 219 | 109 | 28 | 0 |
| INCART | I05 | 2 | baseline | 76.174% | 219 | 109 | 28 | 0 |
| INCART | I12 | 6 | V4-A | 42.857% | 3 | 5 | 3 | 0 |
| INCART | I12 | 6 | baseline | 42.857% | 3 | 5 | 3 | 0 |
| INCART | I13 | 6 | V4-A | 99.782% | 229 | 0 | 1 | 0 |
| INCART | I13 | 6 | baseline | 99.782% | 229 | 0 | 1 | 0 |
| INCART | I14 | 6 | V4-A | 100.000% | 64 | 0 | 0 | 0 |
| INCART | I14 | 6 | baseline | 100.000% | 64 | 0 | 0 | 0 |
| INCART | I16 | 8 | V4-A | 0.000% | 0 | 909 | 2 | 0 |
| INCART | I16 | 8 | baseline | 0.000% | 0 | 980 | 2 | 0 |
| INCART | I17 | 8 | V4-A | 0.000% | 0 | 12 | 27 | 0 |
| INCART | I17 | 8 | baseline | 0.000% | 0 | 13 | 27 | 0 |
| INCART | I23 | 11 | V4-A | 37.500% | 3 | 0 | 10 | 0 |
| INCART | I23 | 11 | baseline | 37.500% | 3 | 0 | 10 | 0 |
| INCART | I24 | 11 | V4-A | 42.857% | 3 | 5 | 3 | 0 |
| INCART | I24 | 11 | baseline | 42.857% | 3 | 5 | 3 | 0 |
| INCART | I27 | 13 | V4-A | 97.283% | 716 | 36 | 4 | 0 |
| INCART | I27 | 13 | baseline | 97.283% | 716 | 36 | 4 | 0 |
| INCART | I28 | 13 | V4-A | 66.667% | 4 | 4 | 0 | 0 |
| INCART | I28 | 13 | baseline | 66.667% | 4 | 4 | 0 | 0 |
| INCART | I47 | 21 | V4-A | 87.437% | 87 | 19 | 6 | 0 |
| INCART | I47 | 21 | baseline | 87.000% | 87 | 20 | 6 | 0 |
| INCART | I48 | 21 | V4-A | 94.530% | 216 | 6 | 19 | 0 |
| INCART | I48 | 21 | baseline | 94.530% | 216 | 6 | 19 | 0 |
| INCART | I51 | 23 | V4-A | 98.343% | 801 | 25 | 2 | 0 |
| INCART | I51 | 23 | baseline | 98.343% | 801 | 25 | 2 | 0 |
| INCART | I52 | 23 | V4-A | 100.000% | 137 | 0 | 0 | 0 |
| INCART | I52 | 23 | baseline | 100.000% | 137 | 0 | 0 | 0 |
| INCART | I53 | 23 | V4-A | 99.549% | 1104 | 3 | 7 | 0 |
| INCART | I53 | 23 | baseline | 99.549% | 1104 | 3 | 7 | 0 |
| INCART | I54 | 24 | V4-A | 19.802% | 10 | 69 | 12 | 0 |
| INCART | I54 | 24 | baseline | 19.802% | 10 | 69 | 12 | 0 |
| INCART | I55 | 24 | V4-A | 30.435% | 7 | 22 | 10 | 0 |
| INCART | I55 | 24 | baseline | 30.435% | 7 | 22 | 10 | 0 |
| INCART | I56 | 24 | V4-A | 29.630% | 4 | 16 | 3 | 0 |
| INCART | I56 | 24 | baseline | 29.630% | 4 | 16 | 3 | 0 |
| INCART | I65 | 28 | V4-A | 83.817% | 303 | 38 | 79 | 0 |
| INCART | I65 | 28 | baseline | 83.817% | 303 | 38 | 79 | 0 |
| INCART | I66 | 28 | V4-A | 86.501% | 157 | 6 | 43 | 0 |
| INCART | I66 | 28 | baseline | 86.501% | 157 | 6 | 43 | 0 |
| INCART | I67 | 28 | V4-A | 90.057% | 471 | 44 | 60 | 0 |
| INCART | I67 | 28 | baseline | 90.057% | 471 | 44 | 60 | 0 |
| INCART | I72 | 31 | V4-A | 79.507% | 355 | 152 | 31 | 0 |
| INCART | I72 | 31 | baseline | 79.507% | 355 | 152 | 31 | 0 |
| INCART | I73 | 31 | V4-A | 77.707% | 61 | 26 | 9 | 0 |
| INCART | I73 | 31 | baseline | 77.707% | 61 | 26 | 9 | 0 |
| INCART | I74 | 32 | V4-A | 97.770% | 263 | 1 | 11 | 0 |
| INCART | I74 | 32 | baseline | 97.770% | 263 | 1 | 11 | 0 |
| INCART | I75 | 32 | V4-A | 99.837% | 611 | 0 | 2 | 0 |
| INCART | I75 | 32 | baseline | 99.837% | 611 | 0 | 2 | 0 |
| MITBIH | 100 | 100 | V4-A | 100.000% | 1 | 0 | 0 | 0 |
| MITBIH | 100 | 100 | baseline | 100.000% | 1 | 0 | 0 | 0 |
| MITBIH | 106 | 106 | V4-A | 94.673% | 471 | 4 | 49 | 0 |
| MITBIH | 106 | 106 | baseline | 94.483% | 471 | 6 | 49 | 0 |
| MITBIH | 109 | 109 | V4-A | 91.429% | 32 | 0 | 6 | 0 |
| MITBIH | 109 | 109 | baseline | 91.429% | 32 | 0 | 6 | 0 |
| MITBIH | 111 | 111 | V4-A | 0.000% | 0 | 11 | 1 | 0 |
| MITBIH | 111 | 111 | baseline | 0.000% | 0 | 11 | 1 | 0 |
| MITBIH | 112 | 112 | V4-A | 0.000% | 0 | 4 | 0 | 0 |
| MITBIH | 112 | 112 | baseline | 0.000% | 0 | 6 | 0 | 0 |
| MITBIH | 116 | 116 | V4-A | 99.083% | 108 | 1 | 1 | 0 |
| MITBIH | 116 | 116 | baseline | 99.083% | 108 | 1 | 1 | 0 |
| MITBIH | 118 | 118 | V4-A | 33.333% | 4 | 4 | 12 | 0 |
| MITBIH | 118 | 118 | baseline | 33.333% | 4 | 4 | 12 | 0 |
| MITBIH | 121 | 121 | V4-A | 0.000% | 0 | 61 | 1 | 0 |
| MITBIH | 121 | 121 | baseline | 0.000% | 0 | 61 | 1 | 0 |
| MITBIH | 122 | 122 | V4-A | 0.000% | 0 | 0 | 0 | 0 |
| MITBIH | 122 | 122 | baseline | 0.000% | 0 | 0 | 0 | 0 |
| MITBIH | 124 | 124 | V4-A | 94.382% | 42 | 0 | 5 | 0 |
| MITBIH | 124 | 124 | baseline | 94.382% | 42 | 0 | 5 | 0 |
| MITBIH | 202 | 202 | V4-A | 44.186% | 19 | 48 | 0 | 0 |
| MITBIH | 202 | 202 | baseline | 44.186% | 19 | 48 | 0 | 0 |
| MITBIH | 203 | 203 | V4-A | 36.777% | 388 | 1278 | 56 | 0 |
| MITBIH | 203 | 203 | baseline | 36.777% | 388 | 1278 | 56 | 0 |
| MITBIH | 208 | 208 | V4-A | 98.592% | 980 | 16 | 12 | 0 |
| MITBIH | 208 | 208 | baseline | 98.592% | 980 | 16 | 12 | 0 |
| MITBIH | 210 | 210 | V4-A | 78.235% | 133 | 13 | 61 | 0 |
| MITBIH | 210 | 210 | baseline | 78.235% | 133 | 13 | 61 | 0 |
| MITBIH | 215 | 215 | V4-A | 72.222% | 130 | 66 | 34 | 0 |
| MITBIH | 215 | 215 | baseline | 72.222% | 130 | 66 | 34 | 0 |
| MITBIH | 231 | 231 | V4-A | 100.000% | 2 | 0 | 0 | 0 |
| MITBIH | 231 | 231 | baseline | 100.000% | 2 | 0 | 0 | 0 |

## Original Development subset — descriptive, not independent Evaluation

For direct continuity with prior V4 reports, the original7 MIT Validation
records and11 INCART Validation records have unchanged results at the locked
gate0.05: MIT F1=74.8632% (TP1163,FP643,FN138); INC F1=93.8459%
(TP2844,FP122,FN251). These original Development records span Fit/Calibration/
Evaluation roles of this gate experiment, so these values are descriptive only.
Original Development FP decomposition from saved V4 scores: MIT626 matched-N
classification FP +17 unmatched PVC alarms; INC101 matched-N FP +21 unmatched
alarms. Thus most original Development FP are on real annotated Normal QRS,
not primarily invalid detector peaks. A peak-verification gate alone cannot
be assumed to fix those CNN errors.
They must not be confused with the separate45-record held-out gate Evaluation
pool reported above. There is no demonstrated original-Development benefit.

## Worst Evaluation group

MITBIH baseline: group111, F10.000%.
MITBIH V4-A: group111, F10.000%.
INCART baseline: group8, F10.000%.
INCART V4-A: group8, F10.000%.
