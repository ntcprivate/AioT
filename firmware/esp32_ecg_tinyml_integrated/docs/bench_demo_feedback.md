# CNN-driven BENCH DEMO feedback

## Behavior and scope

GPIO23 LED and GPIO25 active-HIGH buzzer are LOW for NORMAL and for UNKNOWN,
invalid input, leads-off, sampling/process gaps and expired predictions. In
explicit BENCH DEMO only, a newly accepted live CNN PVC prediction schedules
one simultaneous approximately 150 ms pulse. A held PVC label cannot replay it.
This is simulator-only research feedback, not a medical alarm.

The only event producer is the successful `ecg_ai::publish` branch after actual
live model invocation and existing quality/generation/freshness checks. Neither
an R peak nor golden-test output triggers this controller. Absolute R sample
index is monotonically deduplicated, including across invalidation. A newer
NORMAL or invalid/stale state cancels active and pending pulses rather than
playing old PVC feedback later.

`BenchFeedback` uses four fixed pending slots, no heap and no sleeps. The
existing GPIO task services it every 10 ms on core 0, priority 6; ADC sampling
remains core 1 priority 10. Completed pulses have at least a 10 ms OFF interval.
Overflow drops the newest event and increments `dropped`; cancellation,
duplicate and completion counters are available in the controller. No new
telemetry fields or GUI changes were made. UART pulse logging happens only
after the GPIO falling edge. A 150 ms deadline is quantized by task scheduling;
invalidation or a newer NORMAL intentionally shortens it.

## Files

- Changed `main/pipeline.cpp`: accepted-CNN event hook, fail-closed GPIO task,
  invalidation cancellation; default outputs LOW. Explicit old golden demo
  remains diagnostic-only and cannot coexist with BENCH DEMO.
- Changed `main/Kconfig.projbuild`, `sdkconfig`, `sdkconfig.defaults`:
  `ECG_BENCH_DEMO` defaults OFF, hardware boot self-test defaults OFF.
- Added `main/bench_feedback.h`, `tests/bench_feedback_test.cpp` and
  `tools/ecg_monitor/tests/test_bench_feedback.py`.
- Added `debug/bench_demo/`: dedicated configuration, before hashes/source
  snapshots, build/test logs, authorized flash runner, pre-flash sector backup,
  raw serial capture and results. Existing research artifacts were retained.

CNN, threshold 0.52, golden reference, preprocessing, detector/FIFO, ADC,
telemetry and GUI sources are unchanged (SHA-256 regression check).

## Configuration and checks

Normal project configuration has BENCH DEMO OFF. Enable **BENCH DEMO** under
the integrated ECG menu only for a no-body simulator setup; disable hardware
self-test and golden alert demo. The dedicated build uses
`debug/bench_demo/sdkconfig.bench` and directory `build_bench_demo` so the normal
project configuration remains OFF.

Focused tests:

```powershell
& tools/ecg_monitor/.venv/Scripts/python.exe -m unittest discover -s tools/ecg_monitor/tests -p test_bench_feedback.py -v
```

Four tests PASS: the compiled production controller scenarios (150 ms,
deduplication, consecutive PVCs, NORMAL/invalid cancellation, expiry, generation,
queue overflow and clock rewind), explicit modes, real event source and
protected component hashes. Both normal and BENCH DEMO firmware builds PASS
with ESP-IDF v5.4.4. Normal app is 0x50b70 bytes; BENCH app is 0x51120 bytes.
No offline model evaluation or training was repeated.

## Board verification

Current user explicitly confirmed no body connection and permitted COM3
flash/reset. Flash/capture evidence and limitations are recorded in
`debug/bench_demo/hardware_results.json` and `results.json` below this session.
A valid simulator PVC and external GPIO measurement are required to establish
physical pulse timing; host tests and invalid-input captures do not prove it.

COM3 flash PASS, all written images MD5 verified. The board remains running the
BENCH DEMO build. Its boot marker reports `enabled=1 source=LIVE_CNN
pulse_us=150000 medical_alarm=0`; the automatic unchanged golden test is
12/12 EXACT. A fresh 0x70000-byte pre-flash backup was retained. An initial
attempt stopped before writing because Monitor reopened COM3; the completed
session held exclusive serial ownership through backup, flash and capture.

The 90-second raw capture contains 22,336 valid hardware samples, measured
device-time rate 250.000011 Hz, zero missed samples/ADC errors, zero CRC,
schema/sequence errors, packet gaps, TX drops and UART errors. Firmware reports
7 late samples; the parser flags 14 interval-timing deviations. This is not a
zero-jitter result or proof of their cause. The fixed capture stop left a
480-byte incomplete final frame, retained as received; complete frames passed
validation without repair.

Every captured status is `LEADS_OFF`, LED OFF and buzzer OFF; accepted live
inferences and pulses are zero. This verifies fail-closed behavior for the
observed input. Actual NORMAL/PVC physical response and electrical 150 ms pulse
timing remain **PENDING**, requiring valid bench simulator input and external
GPIO observation. No fake prediction or bypass was used. After flash the serial
capture released COM3; ECG Monitor can reconnect normally.
