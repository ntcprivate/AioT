# V4 passive ADC UART capture - ECG end-to-end FAIL

Recorded existing COM3 UART at115200; no flash, reset pulse, firmware/threshold/gate changes. Same boot bc71c753 as previous22/22 golden evidence. Golden was not rerun. Physical isolation and source identity were not established by UART; this is not a patient-safety certification or proof of source identity.

Requested120seconds; host elapsed120.669131s. Raw ADC 30080samples spanning120.316000s; rate250.000000000Hz, interval mean/min/max4000.000000/3685/4315us. Packet boundaries extend the retained span slightly beyond120seconds. Complete-frame CRC/sequence checks passed; final169incomplete tail bytes preserved in uart_raw.log, not counted as complete telemetry.

ADC min/max 0/4095, mean3873.329; 27460samples meet firmware rail criterion raw<=16 or>=4079. Counts are not calibrated volts. LO+HIGH 5580, LO-HIGH 139. Status reasons{'ADC_SATURATION': 192, 'LEADS_OFF': 40, 'PROCESS_BLOCK_GAP': 3}; valid-quality statuses0/235. Quality descriptors can refer to their own quality_t_us, not every live sample; no unsupported ECG morphology claim is made.

R-peaks0; inference0; classified0; rejected beat windows0. NORMAL0,PVC0. Gate blocks before window/inference, so zero rejected windows does not mean valid input. No actual ADC Invoke occurred; latency unavailable, not zero. Golden/benchmark timings are not substituted.

ADC errors/missed flags/queue and block drops: see metrics.json counter deltas and raw sample flags. Heap minimum sinceboot144512bytes, finalfree153348bytes, workerfreestack8312bytes. Arena6124used from earlier same-boot model initialization, not newly measured.

FAIL for valid analog ECG-to-CNN evidence: ADC saturation and safety invalidity prevented inference. UART recording and sampling work, but no usable NORMAL/PVC result exists. Saturation alone cannot identify an overvoltage or its electrical cause. Investigate the analog source/output/bias/grounding using suitable bench equipment without a person connected; do not disable clipping/gates or retune CNN. No reference labels, no Precision/Recall/F1.

Evidence: uart_raw.log, adc_raw.csv, predictions.csv, telemetry.json, adc_metrics.json(preliminary), metrics.json(final), session_metadata.json, evidence_manifest.json. Previous captures unchanged.
