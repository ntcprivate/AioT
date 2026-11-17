# V4 ESP32 golden preparation — 2026-11-16

## Status

ESP-IDF 5.4.4 build: PASS. Hardware golden: **NOT RUN**; both Windows and pyserial enumeration found no Serial ports. No flash/reset performed. There are 22 prepared fixtures, not 22 hardware passes.

## Model and arithmetic

- Source: `models/v4/ecg_cnn_v4_best.keras`, 849 parameters, SHA-256 `36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1`.
- INT8: `models/v4/ecg_cnn_v4_int8.tflite`, 8,688 bytes, SHA-256 `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`.
- Input int8 [1,256,1], scale 0.06217966973781586, zero point -8. No RR input.
- Output int8 [1,1], scale 1/256, zero point -128. Probability `(q+128)/256`. Fixed threshold 0.88 means **q >= 98**; q97=0.87890625, q98=0.8828125. No threshold tuning.
- Existing V4 host parity 25,010/25,010 exact reused, not rerun. Cached host/reference codes checked equal.
- Operators: EXPAND_DIMS, CONV_2D, RESHAPE, MAX_POOL_2D, MEAN, FULLY_CONNECTED, LOGISTIC; resolver compiles against TFLM 1.4.2. ESP-NN 1.3.0 present as dependency but disabled for inference. Same host-proven specialized Conv/FC rounding configuration retained; other reference operators unchanged. Actual Xtensa numerical parity remains pending.

## Fixtures and isolation

`fixtures.json` and `golden_fixtures.npz` contain 22 INCART Validation examples (N/V, output extremes and threshold-adjacent outputs). No Final Test accessed. Physical float32 windows reconstructed from lead II, resampled 257→250 Hz; normalized windows and input bytes agree exactly with cached Validation inputs. Fixture preparation verifies source hashes and refuses overwrite.

Independent firmware project: `firmware/` within this directory. Original V1/integrated firmware, models, detector and quality gate were not edited. This firmware only runs embedded static fixtures, no live ADC classification or GPIO alerts. It checks asset hashes, input quantization, preprocessing bytes, raw output, dequantization and classification. Each output must be exact; incorrect true-label classifications are preserved and do not redefine numerical parity.

Strict log verifier requires BEGIN, END, RESULT, memory report, model hash and all unique samples. Its five synthetic parser regression tests passed; these are **not board tests**.

## Memory and build

Build toolchain: ESP-IDF 5.4.4, Xtensa GCC 14.2.0, TFLM 1.4.2. Existing IDF Python environment used; no dependencies installed. Missing local IDF constraints file required session-only `IDF_PYTHON_CHECK_CONSTRAINTS=no`; minimum dependency check succeeded. Optional ROM debugger ELF path warning does not affect compilation.

Build-time size (includes embedded golden/raw assets, not production firmware size):

| Item | Bytes |
|---|---:|
| Application .bin | 276,928 |
| Flash code | 126,552 |
| Flash data | 90,760 |
| Static DRAM | 14,508 |
| IRAM | 49,634 |
| RTC slow | 52 |

Internal heap arena configured at 65,536 bytes. **Actual arena used, free/minimum heap, stack high-water and inference latency are unmeasured**. Firmware logs these when executed; static size is not runtime RAM usage. Do not reuse the old V1 arena measurement as V4 measurement.

## Run when a board is available

From project root, in an ESP-IDF-capable PowerShell terminal:

```powershell
& .\results\cnn_v4\esp32_golden_test\run_golden.ps1 -Action build
# Only with bench hardware disconnected from any person; select actual port:
& .\results\cnn_v4\esp32_golden_test\run_golden.ps1 -Action flash-monitor -Port COM3 -BenchConfirmed
```

If local PowerShell execution policy blocks the helper, use an approved ESP-IDF terminal and run `idf.py -C results/cnn_v4/esp32_golden_test/firmware build` / `idf.py -C results/cnn_v4/esp32_golden_test/firmware -p COM3 flash monitor`. Flash replaces the board application, not the preserved V1 source/artifacts. Save a complete single-boot Serial log; exit monitor using Ctrl+]. Then:

```powershell
.\.venv\Scripts\python.exe results/cnn_v4/esp32_golden_test/verify_board_log.py REAL_BOARD_LOG.txt --output results/cnn_v4/esp32_golden_test/board_result.json
```

Expected hardware result: 22/22 exact, preprocessing 22/22 exact, max code delta 0, correct model SHA, complete markers. Anything else is not PASS and requires investigation without changing references.

## Remaining before end-to-end ECG testing

First obtain real board golden output and runtime memory/latency. Then separately validate ADC physical scaling, 250 Hz timing, lead-off/clipping/quality gates, detector-centered windows and preprocessing against the V4 input contract using an ECG simulator. This static test does not validate R-peak detection, clinical accuracy or live pipeline behavior; no end-to-end pipeline changed here.
