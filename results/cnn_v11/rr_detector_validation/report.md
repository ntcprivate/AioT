# V11 detector-derived RR validation

Fixed five outer checkpoints, thresholds and Fit RR scaling. Current production signal.cpp used without modification. ECG windows remain annotation-centered: RR-only substitution, not detector-window end-to-end accuracy. Synthetic ADC mapping 2048+200 counts/mV follows prior detector protocol. Results use the ungated peak stream; quality-gated deployment may abstain more often. No Test used.

| Dataset | Annotation RR F1 | Detector RR F1 | Change (points) | Detector Precision | Detector Recall | FP/1000 N annotation → detector |
|---|---:|---:|---:|---:|---:|---:|
| MIT-BIH | 89.13% | 84.63% | -4.50 | 85.27% | 86.24% | 17.59 → 17.48 |
| INCART | 88.51% | 83.27% | -5.24 | 87.00% | 84.88% | 31.51 → 26.49 |

All metrics are arithmetic fold means. Reference peak matching uses 38 samples tolerance and requires detection completion by annotation center+128 samples. The current matched detector peak may have a localization offset; only preceding detector peaks are used for its RR. No following beat or annotation class is used as an RR feature. Annotation matching is evaluation association, unavailable online.

MIT-BIH: detector TP=86557, FP=2795, FN=2909; 2.80% N/V missing current peak. Absolute RR error median approximately 0 ms, P95=8 ms among matched peaks.

INCART: detector TP=115556, FP=36637, FN=33256; 22.96% N/V missing current peak. Absolute RR error median=4 ms, P95=204 ms among matched peaks. These error statistics exclude missing peaks and must not be interpreted as overall coverage accuracy.

Missing current peaks receive the fixed V11 missing-history vector [1,1,1,0]. This isolates missing-RR sensitivity but is optimistic operationally: without a detected peak, a real streaming system may produce no window at all. A timing-error vector alone does not cover lead-off or signal-quality gates.

RR precision is inadequate to finalize V11 for deployment. Main degradation is recall (annotation 94.03%/94.58% versus detector 86.24%/84.88%), not increased false positives. Consider a separately validated causal RR-reliability gate routing unreliable RR to the existing ECG-only V6; no fallback was tuned or claimed validated here. Missing detector beats cannot be recovered merely by model routing. Require detector-window end-to-end and independent cohort evaluation before final lock.
