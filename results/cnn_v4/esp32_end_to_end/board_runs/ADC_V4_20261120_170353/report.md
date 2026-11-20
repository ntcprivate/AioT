# V4 ADC disconnected-electrode hardware check

Flash PASS on COM3; esptool readback hash verification succeeded. ADC V4 application SHA-256 80e428b11f8192fb590d34fd902bbc554d22a01e32e555977a3327947362eb2e. Model hash a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e; threshold .88 / code >=98, CPU160MHz. No model, detector, preprocessing or threshold change. Firmware now on ESP32: ADC V4, not BENCH or REPLAY.

Golden 22/22 EXACT in original boot bc71c753. Arena used 6124 / allocated 65536 bytes from model runtime log. The first capture stopped after golden because the capture helper required an ADC startup marker emitted before UART initialization. This is a capture-validator condition, not a golden failure. Its raw log is preserved at D:\Code Part Two\AIoT\results\cnn_v4\esp32_end_to_end\board_runs\ADC_V4_20261120_170132\uart_raw.log. A corrected helper attached to the SAME boot without reset and required CRC-valid HARDWARE / V4 / ADC_CNN status. No reflash or repeated golden was used. No raw data was repaired.

Second capture requested120seconds; ADC sample span 120.316000s, 30080 samples, actual frequency 250.000000000Hz. Host elapsed 120.579851s. Packet read boundaries can extend slightly beyond the requested interval; use actual recorded timestamps, not exactly30000 assumed samples. dt mean/min/max 4000.000000/3992/4008us. ADC raw min/max/mean 1728/1984/1866.662; raw counts are not calibrated millivolts.

LO+ HIGH 30080/30080, LO- HIGH 30080/30080. SIGNAL_INVALID / LEADS_OFF throughout. R-peaks0, inference0, classified0, rejected beat windows0 (gate prevents window formation; not evidence of valid input). NORMAL0/PVC0. Invoke and R-to-result latency unavailable for ADC because no ADC inference occurred. Golden latency must not be substituted.

Sample-index gaps 0; telemetry sequence gaps 0; ADC errors/missed/queue/block drops0. Late counter3 existed at first measured status and remained3: delta0 during the status interval. Status interval 119.808000s differs from raw sample span. Single boot identity across logs, no observed unexpected reset. CRC-valid complete frames were used; final 159bytes form a preserved incomplete UART tail at intentional capture stop, not silently repaired or counted as a complete frame. TX-rate display is not used as ADC sample frequency.

Minimum heap since boot 144512bytes, final free heap 153348bytes, worker free stack 8312bytes. Metrics reflect runtime status, arena reflects model startup.

Conclusion: firmware flash, golden and physical ADC sampling at250Hz VERIFIED. Valid ECG acquisition, QRS detection and ADC-to-CNN classification NOT VERIFIED because electrodes were deliberately disconnected and safety gate correctly blocked inference. No ground truth, so no confusion matrix/Precision/Recall/F1. Next appropriate experiment is a specified safe analog ECG simulator with electrodes still off people; this log does not certify human isolation safety.

Files: uart_raw.log (original continuation bytes), adc_raw.csv, predictions.csv (header only), telemetry.json, session_metadata.json, adc_metrics.json (preliminary capture), verified_metrics.json (final review), evidence_manifest.json; initial flash/golden log paths recorded above.
