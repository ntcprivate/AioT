# Locked cross-dataset evaluation — MIT-BIH ST Change Database

Records: 28; patient IDs unavailable. Valid N/V: 74,999/322.
Excluded OTHER: 821; boundary: 39; numeric: 0.

| Model | Threshold | Precision | Recall | F1 | FP | FN | Confusion matrix [N,V] |
|---|---:|---:|---:|---:|---:|---:|---|
| V4 | 0.88 | 8.2365% | 77.0186% | 14.8815% | 2763 | 74 | `[[72236, 2763], [74, 248]]` |
| V5 | 0.33 | 2.3807% | 85.7143% | 4.6328% | 11317 | 46 | `[[63682, 11317], [46, 276]]` |
| V6 | 0.87 | 7.3778% | 74.5342% | 13.4266% | 3013 | 82 | `[[71986, 3013], [82, 240]]` |

No model, threshold, lead, or preprocessing choice was adjusted using STDB. Per-record results are in evaluation.json.
