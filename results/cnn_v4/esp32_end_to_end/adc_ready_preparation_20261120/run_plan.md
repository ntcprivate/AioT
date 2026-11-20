# Prepared ADC automation

No COM3 access, flash or reset has occurred. Firmware algorithms and model are unchanged.

Build log: ../adc_preparation_build_20261120.log. Check build completion and binary manifest before flashing; a directory name alone is not evidence of ADC mode.

New continuous capture helper: python/capture_v4_adc_uart.py. It requires a separately reviewed confirmation JSON, captures raw bytes before one reset, requires 22 exact golden fixtures and ADC mode, rejects reset/CRC/source faults, and writes raw UART, metadata, telemetry JSON, ADC samples CSV, beat predictions CSV and preliminary metrics/report in a fresh ADC_V4 timestamp folder. It never flashes. Its parser has host checks; hardware capture is NOT tested yet.

After physical review and verified ADC flash ONLY, planned command:
C:/Espressif/tools/python/v5.4.4/venv/Scripts/python.exe python/capture_v4_adc_uart.py --confirmation PATH_TO_REVIEWED_JSON --seconds 60

Capture duration starts at golden completion. Quality recovery is not assumed complete at that instant: retain and separately report recovery/rejected intervals, evaluate valid inference using telemetry. No replay END marker is expected. Review boot identity, sample/sequence gaps, health-counter deltas, gates, actual Invoke results, memory and latency before declaring any technical PASS. No reference labels means no Precision/Recall/F1. Keep all original bytes including a possible incomplete tail.
