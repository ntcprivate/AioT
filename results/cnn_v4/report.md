# CNN V4 result

## Training and selection

- Architecture: unchanged V1 CNN, 849 parameters.
- Fit data: MIT-BIH Train 58,134 beats plus INCART Train 118,910 beats.
- Imbalance handling: class weights N=0.5583328603, V=4.7857490404.
- Seed 42, Adam 0.001, batch 64, maximum 30 epochs, patience 5.
- Checkpoint and threshold selected only on patient-disjoint INCART Validation.
- Best epoch: 3; stopped after epoch 8.
- Frozen threshold: 0.88.
- Validation: Precision 95.6435%, Recall 92.9541%, F1 94.2796%; CM `[[21785,131],[218,2876]]`.
- Model SHA-256: `36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1`.

Preprocessing produced 118,910 Train, 25,010 Validation and 26,413 Test N/V windows. There were no NaN/Inf values. Annotation-to-central-morphology offset had median 0 samples and P95 absolute offset 6 samples at 250 Hz.

## Single locked INCART Test evaluation

Test contains 26,413 beats: 23,081 N and 3,332 V. No Test result was used for checkpoint or threshold selection.

| Model | Threshold | Precision PVC | Recall PVC | F1 PVC | FP | FN | Confusion matrix N/V |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| V1 | 0.52 | 46.7000% | 70.0780% | 56.0490% | 2,665 | 997 | `[[20416,2665],[997,2335]]` |
| V4 | 0.88 | 86.5532% | 77.8511% | 81.9719% | 403 | 738 | `[[22678,403],[738,2594]]` |

V4 improves Test PVC F1 by 25.9229 percentage points, reduces false positives by 2,262 and false negatives by 259 relative to V1.

## Per-patient Test result

| Patient | Model | Precision | Recall | F1 | FP | FN |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 9 | V1 | 86.5330% | 49.6711% | 63.1139% | 94 | 612 |
| 9 | V4 | 93.5357% | 78.5362% | 85.3822% | 66 | 261 |
| 10 | V1 | 95.8621% | 45.8746% | 62.0536% | 6 | 164 |
| 10 | V4 | 98.5816% | 45.8746% | 62.6126% | 2 | 164 |
| 17 | V1 | 83.5903% | 88.5648% | 86.0057% | 149 | 98 |
| 17 | V4 | 99.6840% | 73.6289% | 84.6980% | 2 | 226 |
| 27 | V1 | 98.8138% | 87.1339% | 92.6070% | 10 | 123 |
| 27 | V4 | 99.5418% | 90.8996% | 95.0246% | 4 | 87 |
| 30 | V1 | n/a | n/a | n/a | 2,406 | 0 |
| 30 | V4 | n/a | n/a | n/a | 329 | 0 |

Patient 30 contains no V annotation, so PVC Precision/Recall/F1 are undefined for that patient; its false-positive count remains meaningful. V4 is better overall, but patient-level behavior is heterogeneous: recall decreased for patient 17 and did not improve for patient 10.

## Full INT8 PTQ

- Calibration: 1,000 beats from Train only, seed 42, balanced 500 N / 500 V across MIT-BIH Train and INCART Train.
- Output: `models/v4/ecg_cnn_v4_int8.tflite`, 8,688 bytes.
- SHA-256: `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`.
- I/O: INT8. Input scale/zero point `0.06217966973781586 / -8`; output scale/zero point `0.00390625 / -128`.
- Tensor types are INT8 and INT32 only.
- Operators: ExpandDims, Conv2D, Reshape, MaxPool2D, Mean, FullyConnected and Logistic. This is the existing V1 resolver/operator set.

### FP32 versus INT8 on INCART Validation at frozen threshold 0.88

| Model | Precision | Recall | F1 | FP | FN | Confusion matrix N/V |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| FP32 | 95.6435% | 92.9541% | 94.2796% | 131 | 218 | `[[21785,131],[218,2876]]` |
| INT8 | 96.4770% | 92.0491% | 94.2110% | 104 | 246 | `[[21812,104],[246,2848]]` |

F1 decreases by 0.0686 percentage points. There are 55 classification changes among 25,010 windows. Score absolute error: mean 0.003726, P99 0.050660, maximum 0.489056. Five of 6,402,560 quantized input values clip to the INT8 range.

### TFLM host numerical parity

The V1 host executable could not be reused directly because it hard-coded the V1 file size of 8,560 bytes. A separate diagnostic host was built under `results/cnn_v4/`; it uses the same TFLM 1.4.2 Conv/FC single-rounding adapters but accepts the V4 model size.

- Python TFLite versus TFLM host: 25,010 / 25,010 output codes exact.
- Mismatches: 0; maximum code delta: 0 LSB.
- This result tests the adapters with V4 weights/scales; it does not assume V1 rounding behavior transfers automatically.

### ESP32 readiness

The graph and resolver are compatible. Because graph topology, tensor shapes and dtypes match V1, estimated tensor arena use is 6,124 bytes, against the current 65,536-byte allocation. This is an estimate based on the measured V1 graph; V4 `AllocateTensors()` must still be measured in an actual firmware build.

The INT8 artifact is ready as a firmware-integration candidate, but not yet ready to declare deployed: firmware model size/hash, input quantization constants, golden outputs and board parity have not been updated or tested in this task.
