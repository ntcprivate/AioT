# European ST-T cross-dataset evaluation

Records: 90. Valid N/V: 784,534/4,467.
Excluded OTHER: 13,809; boundary: 99; numeric: 0.
Lead policy: prefer MLIII, then MLI, then D3; otherwise first recorded channel; fixed before inference. Counts: {'MLIII': 47, 'D3': 1, 'MLI': 19, 'V3': 2, 'V2': 8, 'V5': 9, 'V1': 4}.

| Model | Threshold | Precision | Recall | F1 | Confusion matrix N/V |
| --- | ---: | ---: | ---: | ---: | --- |
| V1 | 0.52 | 2.0545% | 85.2698% | 4.0123% | `[[602945, 181589], [658, 3809]]` |
| V4 | 0.88 | 5.2953% | 86.5682% | 9.9801% | `[[715374, 69160], [600, 3867]]` |

V4 better F1: True.

OTHER annotations were excluded, never relabeled as NORMAL. European ST-T was not used for training, checkpoint selection or threshold tuning.

Per-record metrics are stored in `evaluation.json`.
