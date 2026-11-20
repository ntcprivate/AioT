# ADC V4 feedback firmware deployment

Flash PASS via COM3; esptool exit0 and data hash verified. Used existing prepared application, bootloader and partition table from adc_v4_feedback_20261120; no build, benchmark, replay, unit test, CNN/threshold/code changes. Operator confirmed electrodes removed and Monitor released COM3.

Application325648bytes, SHA-256 f0f3b8817b144205032a10409873f48b1b7940e4aa971766dd6e06f085efb3bb. Model SHA-256 a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e; threshold.88/code>=98 unchanged. The selected binary is the feedback-enabled version, not the old all-OFF ADC image. Source/build provenance: ../..//adc_v4_feedback_20261120/manifest.json. Its verified implementation uses GPIO23LED and GPIO25buzzer: WAITING1s/1s LED,buzzerOFF; NORMALLEDON,buzzerOFF; PVC200ms/200ms both; INVALIDbothOFF. Firmware inclusion verified by binary hash/provenance and successful flash, not by visual/audible hardware observation.

Boot['e5ab600c']; startup Golden22/22 EXACT, failed0. Raw boot log['I (251) app_init: ELF file SHA256:  ff7718ab9...']. UART contains CRC-valid HARDWARE/V4/ADC_CNN status with golden=true and threshold.88. ADC mode confirmed from status/config; early V4_EXPERIMENT marker may be lost before UART initialization. Final acq_hz250.0; finalstateSIGNAL_INVALID/LEADS_OFF, LEDreportedFalse,buzzerreportedFalse. This is a short startup capture, not a new120s ECG or performance benchmark. Previous golden is not substituted:22new exact fixtures are in this run's raw log.

No observed second boot/reset during capture. Raw UART retained including0incomplete tail bytes at capture stop; partial tail is not treated as a complete frame. The firmware remains ADC V4 feedback on ESP32. Physical LED/buzzer operation and valid ECG-to-CNN inference are NOT claimed PASS.

Files: flash.log, uart_raw.log, capture_console.log, session_metadata.json, deployment_result.json, telemetry.json, adc_metrics.json, adc_raw.csv, predictions.csv and evidence_manifest.json. Existing experiment evidence unchanged.
