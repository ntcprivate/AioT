# ECG Monitor - AI LIVE research prototype

Open `Start_ECG_Monitor.bat` using the existing `.venv`. Select HARDWARE
MONITOR -> COM3 -> Connect -> Start Monitoring. Close other Serial monitors
first. DEMO is synthetic display data and does not run or invent inference.

The single AI ECG CLASSIFICATION area and top header share one snapshot:
- Valid fresh CNN output: AI LIVE + NORMAL (N) or PVC (V).
- Awaiting prediction: WAITING + UNKNOWN.
- Invalid input, leads-off, process gap, expiry or disconnection: UNKNOWN
  with the corresponding reason, no old probability or latency.

The main firmware emits `ai.mode=AI_LIVE` via ECG1v2/CRC32 at115200 baud.
The parser also reads preserved legacy captures through a compatibility
adapter. No offline F1/approval flag gates runtime predictions. Source,
quality/golden readiness, input faults and expiry remain required.

Raw ADC plotting, display-only filtering, rates, CRC/loss counters, CSV export
and automatic raw captures are retained. GUI and CSV use the same prediction
policy. CSV columns are unchanged. Reconnect waits for a newly produced result.
Do not interpret a displayed CNN label as independently verified accuracy.

TEST_ONLY/Synthetic, training/evaluation and conversion tools are retained.
The hardware smoke helper requires explicit bench authorization and saves new
QA results separately. No automatic reset/flash is performed by the GUI.

Current implementation/report: ../../firmware/esp32_ecg_tinyml_integrated/docs/ai_live_cleanup.md
Earlier operational notes: reports/ai_live_cleanup/legacy_monitor_readme.md
All earlier raw captures, CSV and research reports remain preserved.

Research prototype - Not for medical diagnosis.
