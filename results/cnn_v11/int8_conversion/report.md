# V11 Full INT8 PTQ

Source: models/v11/v11_final_best.keras, 2,017 parameters.
SHA256: 61909ec7f93e3d8823627a0127422aefdd098f92a9c95619073968c7a3eb3601.
Converted model: ecg_cnn_v11_int8.tflite, 17,792 bytes.
SHA256: 54f34c5961d61146b53775c167eaf3740f8c9df638e8ae2b0734ad72ef038e58.

No architecture/weights training change. TensorFlow2.21.0, oneDNN=0. PTQ uses
TFLITE_BUILTINS_INT8 only, INT8 for both inputs and output; no floating tensors
remain. INT32 bias/shape tensors are expected and do not indicate float fallback.

## Calibration and preprocessing

1,565 real Train-only samples, seed42: dataset/class-stratified selection plus
Train startup/history cases. Exact dataset/record/source-index manifest retained.
Representative inputs are passed by signature NAME to avoid positional input
reordering. First conversion attempt failed during calibration before producing
a model because positional input order differed; corrected to named mapping.

Existing RR annotation feature artifact was reused in the exact validated V11
record ordering; no ECG re-extraction, training, Test input or detector change.
Train RR feature mean was checked against locked Fit mean. ECG uses existing
250Hz,256-sample,per-window z-score. RR uses frozen final-model mean/std, no
re-estimation on Development. RR features are current RR, median up to7 previous
RR, ratio, history fraction up to8; startup [1,1,1,0]. Offline Development uses
reference annotation timing, not detector RR/windows. It was used for checkpoint
and calibration selection previously, so these figures are quantization
regression comparisons, not independent classification estimates.

## Input/output contract

| Input | TFLite tensor index | Shape | dtype | scale | zero point |
|---|---:|---|---|---:|---:|
| RR normalized | 0 | [1,4] | int8 | 0.14875458180904388 | 79 |
| ECG normalized | 1 | [1,256,1] | int8 | 0.059675201773643494 | -15 |
| Output PVC | 63 | [1,1] | int8 | 0.00390625 | -128 |

Map by name/shape; Keras input order is ECG then RR, while TFLite input_details
order is RR then ECG. Quantization contract: saturate(round_ties_to_even(x/scale)
+zero_point,-128,127). Dequantize output=(q+128)/256.

Fixed probability threshold0.80 becomes **q>=77**, the smallest code with
dequantized score>=0.80. q76=0.796875, q77=0.80078125. No threshold optimization.
Development input clipping: ECG2 values, RR0 values.

## FP32 vs INT8 — same Development samples

| Dataset | Model | Accuracy | Precision | Recall | F1 | TP | FP | FN | TN |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MIT-BIH,12459 | FP32 | 99.3659% | 98.4909% | 95.3846% | 96.9129% | 1240 | 19 | 60 | 11140 |
| MIT-BIH | INT8 | 99.2857% | 97.6397% | 95.4615% | 96.5383% | 1241 | 30 | 59 | 11129 |
| INCART,25010 | FP32 | 99.9280% | 99.8057% | 99.6122% | 99.7088% | 3082 | 6 | 12 | 21910 |
| INCART | INT8 | 99.9320% | 99.7735% | 99.6768% | 99.7251% | 3084 | 7 | 10 | 21909 |

MIT-BIH:20 prediction changes, score MAE0.008664, P99 absolute error0.127299,
maximum0.257533. INCART:3 prediction changes, MAE0.000857, P990.007992,
maximum0.204989. Probability errors can be material for individual samples even
when aggregate F1 changes little. No statistical equivalence margin was
predeclared; do not call these results proof of “no significant degradation”.
MIT Precision decreases0.8512 percentage points; Recall increases0.0769 points.
INC Precision decreases0.0322 points; Recall increases0.0646 points.

## Operators and ESP32/TFLM

32 operator instances,9 unique builtins:
STRIDED_SLICE(v2), EXPAND_DIMS(v1), CONV_2D(v3), RESHAPE(v1),
MAX_POOL_2D(v2), MEAN(v2), FULLY_CONNECTED(v4), CONCATENATION(v2), LOGISTIC(v2).
No Flex/custom/float operator fallback.

Project's installed espressif__esp-tflite-micro source exposes all9 resolver
registrations. strided_slice.cc explicitly handles kTfLiteInt8; concatenation.cc
handles/rescales int8. Existing firmware model.cpp only registers7 operators;
future V11 harness requires AddStridedSlice and AddConcatenation plus two-input
handling. This is source-level compatibility evidence, not an executed V11
AllocateTensors/Invoke result on TFLM or ESP32. ESP-NN optimized coverage can
differ from reference kernels. V1 single-rounding adapters must not be assumed
correct for V11 without exact-code comparison.

## Memory

Flatbuffer/model storage17,792 bytes. Logical input/output payload261 bytes
(ECG256,RR4,output1). Largest tensor by shape3,744 bytes; sum of all tensor shape
storage29,456 bytes **includes constants and alias/reshape tensors**. Neither
number is Tensor Arena usage or a safe arena estimate. Persistent op state,
scratch allocations, lifetime reuse, alignment and actual TFLM planner require
AllocateTensors measurement. Tensor Arena, stack and board latency: NOT MEASURED.

## Golden artifacts and readiness

16 real Development fixtures cover both datasets/classes and threshold-near
cases. golden_fixtures.npz/json contain FP32 ECG, raw/normalized RR, INT8 ECG/RR,
raw output code, dequantized score, true label and host predicted class. Separate
binary files provide fixed-stride MCU payloads (256/4/1 bytes per fixture).
Model hash and scales are retained. Classification mistakes are preserved.

golden_verification.json:16/16 input requantization, host TFLite replay and fixed
threshold decisions exact. TFLM/ESP32 exact numerical parity PENDING. These are
host references to test, not pre-approved device outputs; do not loosen pass
criteria or rewrite references to accommodate board differences.

Ready as an artifact package for a separately authorized static golden harness;
not integrated into firmware, no flash, no INT8 detector end-to-end claim. Need
two-input resolver harness, exact-code comparison, measured arena/latency and
RR/preprocessing parity before integration. Existing detector/system validation
limitations remain unchanged.
