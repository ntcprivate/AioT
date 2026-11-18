# CNN V5 validation result

## Architecture and training

V5 is a two-branch 1D CNN with 4,585 parameters:

- Central-QRS branch: crop central 128 samples, Conv1D 8×5, pool2, Conv1D 12×5, pool2, Flatten, Dense8. Flatten preserves position and avoids relying on global averaging for the central beat.
- Full-window branch: Conv1D 8×15, pool4, Conv1D 12×9, GlobalAveragePooling, Dense8.
- Fusion: Concatenate, Dense8, sigmoid PVC output.

Expected TFLM operators are StridedSlice, Conv2D, MaxPool2D, Reshape, Mean, FullyConnected, Concatenation and Logistic. INT8 conversion was not performed.

Training used the same 177,044 MIT-BIH + INCART Train beats, class weights and optimizer policy as V4. Seed 42; best epoch 5; stopped after epoch 10. Checkpoint and threshold were selected only on INCART Validation. INCART Test and European ST-T were not read or used.

- Locked threshold: 0.33.
- Checkpoint SHA-256: `3b7c815814b6c6336118f536b36e36f096438055b3d1647b43277bce07fc24e3`.

## Validation comparison

| Dataset | Model | Threshold | Precision PVC | Recall PVC | F1 PVC | FP | FN |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| INCART Validation | V4 | 0.88 | 95.6435% | 92.9541% | 94.2796% | 131 | 218 |
| INCART Validation | V5 | 0.33 | 99.8062% | 99.8707% | 99.8384% | 6 | 4 |
| MIT-BIH Validation | V4 | 0.88 | 65.0917% | 90.0769% | 75.5728% | 628 | 129 |
| MIT-BIH Validation | V5 | 0.33 | 97.9463% | 95.3846% | 96.6485% | 26 | 60 |

V5 gains 5.5588 F1 percentage points on INCART Validation and 21.0757 points on MIT-BIH Validation. It satisfies the predeclared continuation rule: INCART F1 gain at least 0.5 points, MIT-BIH F1 loss no worse than 1 point, and INCART recall loss no worse than 1 point.

## Conclusion

V5 is worth testing on a new independent dataset. The near-perfect INCART result is a development-set result used for checkpoint and threshold selection, not independent evidence. MIT-BIH Validation has also been examined in earlier work. Neither result justifies replacing V4 or claiming deployment readiness without a genuinely unseen cohort.
