# CONV INT8 numerical diagnosis — 2026-11-06

The numerical cause is demonstrated on host using the actual bundled TFLM
sources and original model/fixtures. The patched ESP32 firmware builds, but has
not been flashed, reset, or executed on the board by this task. Hardware PASS
and sampling performance under the new kernel remain to be measured.

## Integrity and first divergence

Model SHA256:
`38705f5399ada9b87f466725608a053ae2305295a8a3cae7bda01f4928f4a394`.
The model is 8560 bytes; the embedded binary, golden samples, metadata and
dependency lock match Step 8. Sample 5 has 256 original INT8 bytes and input
FNV1a32 `54868f67`. Model schema is 3, first CONV version is 3. FlatBuffer
weights, biases, quantization and options are read directly, not reconstructed
from Serial or guessed from Python output.

First CONV: input NHWC `[1,1,256,1]`, filter OHWI `[8,1,5,1]`, output
`[1,1,252,8]`. VALID padding, stride/dilation 1, fused ReLU, filter quantization
axis 0 and eight channel scales. Filter/bias zero points are 0. Input zero
point is -27; output zero point is -128, clamp [-128,127]. Bias scales match
input scale times channel weight scale within float32 precision. Maximum
absolute accumulator over all 2016 outputs is 31805; no INT32 overflow.

`serial_trace_v2.log` is incomplete and remains rejected by the strict
comparator. Only 2000 checksum-verified bytes of operator 1 are available.
The stock double-round calculation matches all those bytes, including the
three differences below. The other 16 bytes were never repaired or inferred
as hardware evidence. Full 2016-byte comparisons below are host computations.

## Exact arithmetic cause

The stock TFLM `internal/common.cc` with `TFLITE_SINGLE_ROUNDING=0` performs
SaturatingRoundingDoublingHighMul followed by RoundingDivideByPOT. Near a
halfway boundary, the first rounding can create a tie for the second rounding.
The CPU builtin reference for this model is reproduced exactly by the
single-round branch. This is a backend rounding difference, not an ESP-NN,
LOGISTIC, UART, model-cache or input-order correction.

| Byte | timestep/channel | accumulator | multiplier | shift | first high-mul | double requant | single requant | old board INT8 | reference/patched host INT8 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|292|36/4|4212|1158334591|-6|2272|36|35|-92|-93|
|820|102/4|415|1158334591|-6|224|4|3|-124|-125|
|1455|181/7|3266|1893405901|-7|2880|23|22|-105|-106|

For byte 292, the exact scaled accumulator is 35.4987081467. Double rounding
first produces 2272; 2272/64 is 35.5 and rounds to 36. Single rounding produces
35. Adding output zero point -128 gives -93 instead of -92. The corresponding
exact values for bytes 820 and 1455 are 3.49761725567 and 22.4967649871.

Original windows/weights/biases:

| Byte | input window | channel weights | bias INT32 |
|---|---|---|---:|
|292|[-28,-22,-10,5,19]|[-127,-14,-65,56,86]|-488|
|820|[-33,-32,-32,-30,-28]|[-127,-14,-65,56,86]|-488|
|1455|[2,-1,-5,-6,-7]|[-62,63,13,127,100]|-1527|

All scales, intermediate values and partial hardware evidence are in
`isolated_conv_arithmetic.json`. This is supported by two independent tests:
stdlib integer calculations over the original FlatBuffer and the actual
bundled C++ ConvPerChannel/common.cc compiled in both rounding modes.

## Controlled patch

Only CONV_2D uses single rounding. `single_round_conv.cpp` reuses vendor
ConvInit/ConvPrepare, prepared per-channel multipliers and the original
reference convolution loop, under uniquely named inline functions. The
specialization changes the requantization helper only. No model, reference,
sample-specific output adjustment or postprocessing correction is used.

The rest of TFLM stays `TFLITE_SINGLE_ROUNDING=0`. A diagnostic trial of global
single rounding was rejected: it corrected early CONV tensors but introduced
MEAN/downstream divergence and seven golden failures. Consequently enabling
that macro globally is not the fix. Managed component sources are unchanged.

`model.cpp` registers the specialized CONV, verifies the arithmetic macros,
logs their effective values, and optionally prints three `ECG_CONV_ARITH`
records after Invoke. Diagnostic indices affect logging only, never output.
Existing 3 warm-ups, 30 repeats, exact code and class checks remain. A failed
diagnostic Invoke also keeps golden failed. ADC, pipeline/FSM, hardware test,
2-second latch, threshold 0.52, live-disabled guard and console transport are
unchanged. No sampling/console calls were added inside the convolution loop.

## Tests and limits

Files changed/added for this numerical fix (all inside integrated):

- Runtime: `main/model.cpp`, `main/single_round_conv.cpp/.h`,
  `main/single_round_math.h`; register the specialized Conv and compact logs.
- Build/config: `CMakeLists.txt`, `main/CMakeLists.txt`,
  `main/Kconfig.projbuild`; generated `sdkconfig` enables the diagnostic options.
- New host diagnostics: `tests/flat_reader.py`, `tests/isolate_conv.py`,
  generated `tests/conv_fixture.h`, `tests/conv_kernel_test.cpp`,
  `tests/run_conv_host.py`, `tests/requantization_test.cpp`,
  `tests/run_requant_host.py`, `tests/full_chain_host.cpp`,
  `tests/run_full_host.py`, `tests/host_stubs/esp_timer.h`.
- Existing `tests/check_xtensa_syntax.py` includes the new Conv and macros;
  the actual firmware build is the compile/link verification for this task.
- Documentation/reports: `README.md`, `operator_debug_report.json`,
  `integration_report.json`, `debug/numerical_fix_notes.md`,
  `debug/numerical_fix_report.json` and diagnostic JSON/text/build logs.
  Executables, object files and host tensor dumps are generated test artifacts.

`main/main.cpp`, `main/pipeline.cpp`, `main/signal.cpp`, the console/trace
implementation and strict comparator are unchanged in this numerical fix.

- Original host backend: reproduces sample 2=-61 and sample 5=0, exactly two
  golden failures. This also agrees with the archived Step 8 board log; that
  archive did not prove Step 8 passed all golden samples.
- Isolated CONV: original FNV `84bd53f7`, three differences; single-round FNV
  `c1b69a54`, zero differences over 2016 bytes.
- Actual patched host interpreter: all 12 golden codes exact; sample 2=-66,
  sample 5=7. All 16 sample-5 operator tensors match the saved Python reference
  byte for byte. Host uses preserve-all-tensors for inspection; firmware keeps
  its original arena planner/alignment. See `full_host_results.json`.
- Adapter helper vs vendor single-round helper: 20000 signed cases, shifts
  and positive/negative ties pass.
- Fourteen strict transport tests pass, including missing character, invalid
  checksums/markers, missing/duplicate chunks. Original corrupted capture is
  rejected, not repaired (`strict_trace_recheck.json`).
- Fresh C++ trace encoder and signal guard tests pass. These cover buffer
  bounds, HEX conversion, rails/flat/noise/timing rejection and beat indexing;
  they do not measure board sampling or LED/buzzer timing.
- ESP-IDF 5.4.4, target esp32, linked binary and partition size check pass.
  Final size/hash and source evidence are in `numerical_fix_report.json`.

Sample 5 changes from p=0.5/class 0 to p=0.52734375/class 1 at threshold 0.52
on patched host. This establishes reference consistency, not a new accuracy
claim. Some golden references themselves misclassify ground truth.

## Board verification (user executes)

In an ESP-IDF v5.4.4 PowerShell terminal:

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
idf.py build
idf.py -p COM3 flash
idf.py -p COM3 monitor
```

Expected checks, not yet observed on the patched board:

```text
ECG_KERNELS reference_active=1 esp_nn_effective=0 single_rounding=0 conv_single_rounding=1
ECG_GOLDEN_DONE samples=12 failed=0 status=PASSED live_mode_unchanged=1
```

Check sample 2 code=-66, sample 5 code=7, warm_exact=1, stable_exact=1,
class_match=1, and compact Conv records actual=-93/-125/-106. Record ADC_BUFFER
missed_est/late/adc_errors, continuity and hardware self-test. INVALID_LEADS or
saturation must stay SIGNAL_INVALID, never evidence for NORMAL/PVC. Live
classification remains disabled even if all golden fixtures pass.

To reduce Serial volume, disable only `ECG_OPERATOR_TRACE` via menuconfig;
keep `ECG_CONV_ARITHMETIC_LOG` enabled with diagnostic sample 5. Arithmetic logs
use the existing serialized console and line checksum. For complete tensor
comparison keep operator tracing enabled and capture a fresh intact protocol2
log; run the unchanged comparator. A rejected capture cannot establish a full
hardware operator-chain PASS.

Host rerun commands (Python with stdlib and g++ on PATH; TensorFlow not needed):

```powershell
python tests/isolate_conv.py
python tests/run_conv_host.py
python tests/run_requant_host.py
python tests/run_full_host.py
python -m unittest discover -s tests -p test_trace_protocol.py -v
```

The workspace .venv interpreter could not start in this session; it was not
recreated or changed. Host diagnostics use system Python; firmware uses the
installed IDF tool environment.
