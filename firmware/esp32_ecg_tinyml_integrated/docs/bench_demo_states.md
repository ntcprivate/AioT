# BENCH DEMO state feedback

Replaces the previous one-shot PVC demonstration. This is no-body ECG simulator
feedback, not a medical alarm. Only `CONFIG_ECG_BENCH_DEMO=y` enables it; the
normal firmware configuration remains OFF. Hardware self-test and golden alert
demo cannot coexist with this mode.

| State (highest priority first) | GPIO23 LED | GPIO25 buzzer |
| --- | --- | --- |
| LEADS_OFF | continuously ON | OFF |
| INVALID | OFF | 1000 ms ON / 1000 ms OFF |
| UNKNOWN | OFF | 1000 ms ON / 1000 ms OFF |
| PVC | continuously ON | 200 ms ON / 200 ms OFF |
| NORMAL | 500 ms ON / 500 ms OFF | synchronized 500 ms ON / 500 ms OFF |

On each transition the new pattern starts at its ON phase; no previous phase
is allowed to finish first. Repeated predictions with the same class preserve
the oscillator phase. Expiry, absent prediction, quality warmup or model not
ready cannot select NORMAL/PVC. These two states require a fresh accepted
`CNN_PREDICTION` from the existing live INT8 path. Invalid quality/system faults
override predictions. Latest physical lead-off status overrides both invalid
and prediction states, including while model startup has not finished.

The existing GPIO task evaluates the state every 10 ms with monotonic time and
no heap allocation or blocking waveform delays. State changes therefore apply
on its next scheduled iteration, rather than waiting 200/500/1000 ms. GPIO
driver failures still attempt both outputs OFF and latch the existing fault.
Per-state UART printing is disabled inside the BENCH control loop; unchanged
telemetry carries state/output status. No R-peak event hook or old one-shot
controller writes the outputs in parallel.

Changed files:

- `main/bench_feedback.h`: priority selector and timestamp-driven patterns.
- `main/pipeline.cpp`: latest physical leads input, one state selector/GPIO
  owner, removal of the old per-prediction pulse hook/logging.
- `main/Kconfig.projbuild`: updated BENCH description, default remains OFF.
- `tests/bench_feedback_test.cpp`,
  `tools/ecg_monitor/tests/test_bench_feedback.py`: focused regression checks.

Model, threshold 0.52, preprocessing, detector/FIFO, ADC, telemetry and GUI code
are unchanged. No files were deleted, no training or offline benchmark rerun,
and nothing was pushed to GitHub. Prior reports/captures were retained.

Four related tests PASS: waveform boundaries, synchronous NORMAL outputs,
transitions, priority conflicts, expiry/non-CNN rejection, same-class phase
continuity, default OFF, integration source and protected component hashes.
Both normal and BENCH firmware build with ESP-IDF v5.4.4. Build/test logs,
pre-flash backup and board evidence are in `debug/bench_states/`.

Reproduce the focused tests from the workspace root (g++ must be available):

```powershell
g++ -std=c++17 -O2 -I firmware/esp32_ecg_tinyml_integrated/main firmware/esp32_ecg_tinyml_integrated/tests/bench_feedback_test.cpp -o firmware/esp32_ecg_tinyml_integrated/debug/bench_demo/controller_test.exe
& tools/ecg_monitor/.venv/Scripts/python.exe -m unittest discover -s tools/ecg_monitor/tests -p test_bench_feedback.py -v
```

The dedicated `build_bench_demo` uses `debug/bench_demo/sdkconfig.bench` with
BENCH enabled. Root `sdkconfig` keeps BENCH disabled. Flash/capture results
are recorded separately in `debug/bench_states/hardware_results.json` and
`results.json`; telemetry confirms commanded GPIO states, not external voltage
or audible timing measurements.

COM3 flash completed with MD5 verification after a fresh sector backup, using
the existing explicit user confirmation of no-body bench setup. The board is
left running BENCH DEMO STATE_V2 and COM3 is released for Monitor. Its unchanged
automatic startup golden check reported 12/12 EXACT; no separate offline CNN
evaluation was run.

The 45-second capture has 11,072 valid samples, device-time rate
250.000040 Hz, zero missed samples, ADC errors, CRC/sequence errors, packet gaps,
TX drops or UART errors. There are 7 late samples and 14 parser interval-timing
deviations, so this is not a zero-jitter measurement. The fixed-duration stop
left a 1,216-byte partial final frame; no complete frame was repaired.
All captured statuses are LEADS_OFF with LED ON and buzzer OFF. Other patterns
passed host controller tests; their electrical timing and behavior with valid
NORMAL/PVC simulator input remain pending, not inferred from the golden test.
