# ESP32 ECG TinyML - AI LIVE research prototype

The normal ESP-IDF5.4.4 application has one inference path:
ADC250Hz -> unchanged quality gate -> detector2B / FIFO ->256 samples ->
unchanged preprocessing -> INT8 CNN -> ECG1v2 `ai` -> ECG Monitor.

Model weights, threshold0.52 and golden reference are unchanged. Offline
acceptance scores do not enable/disable runtime inference. Validity, lead-off,
clipping, timing, generation checks and prediction expiry still fail closed.
The model worker does not control prediction-driven LED/buzzer alarms.

## Build and run

Use the existing ESP-IDF5.4.4 terminal and `idf.py build` in this directory.
Normal telemetry builds select `ECG_AI_LIVE` automatically. No extra research
mode needs to be enabled. After confirming a no-body bench setup, flash the
build to COM3. Never test this prototype on a person.

Open `tools/ecg_monitor/Start_ECG_Monitor.bat` from the workspace, choose
HARDWARE MONITOR, COM3, Connect, Start Monitoring. One AI ECG CLASSIFICATION
panel and its header share one validated prediction snapshot. UNKNOWN is
expected when signal/input/prediction is invalid, stale or disconnected.

## Diagnostic configurations and compatibility

`ECG_AI_TEST_ONLY` and `ECG_SYNTHETIC_TELEMETRY_TEST` remain supported; both
exclude ADC inference. Reference golden outputs are never live predictions.
Hardware self-test is explicitly separate from CNN predictions.
`tools/ecg_monitor/run_ai_live_bench.py` performs authorized bench backup,
flash and bounded capture. `run_ai_test_only_bench.py` now snapshots the actual
current image into a unique session before diagnostic flashing/restoration.

ECG1v2 framing, CRC32, sample batching and source identity are preserved.
Canonical prediction: `ai.mode=AI_LIVE`, `ai.source=ADC_CNN`. Historical
`research` packets remain readable through the same GUI/CSV decoder adapter,
not a second pipeline. CSV columns and raw capture are preserved.

## Preserved training and evidence

Training/conversion/evaluation scripts in `python/`, datasets/splits, V1
models/weights, golden fixtures, TEST_ONLY, Synthetic and previous captures
remain intact. Continue ModelV2 with the same input contract; update the model
and golden fixtures deliberately when that separate task is authorized.

See `docs/ai_live_cleanup.md` and `debug/ai_live/results.json` for this revision.
Older setup notes are archived in `docs/legacy_integrated_readme.md`; their
acceptance assessments are historical, not runtime switches.

Research prototype - Not for medical diagnosis.
