# ADC V4 preparation complete; physical measurement BLOCKED

- ADC application built, Ninja final exit 0 and size exit 0. CPU 160 MHz, IDF 5.4.4, main.cpp selected, replay/benchmark sources excluded, synthetic disabled. TFLM compile definitions confirm reference kernels (sdkconfig ESP-NN option alone is not the effective compiler configuration).
- Model SHA a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e verified and embedded bytes located in application. Threshold .88, output >=98; algorithms unchanged.
- Application 324864 bytes; SHA 80e428b11f8192fb590d34fd902bbc554d22a01e32e555977a3327947362eb2e. Static DRAM 51468, IRAM 54062 bytes; these are BUILD values, not runtime heap/arena/stack measurements.
- Initial reconfigure logged Git ownership warnings and missing ESP_ROM_ELF_DIR for GDB symbol generation. Full binary generation/partition size checks completed. Independent final Ninja and size commands both returned 0. No global Git settings were changed.
- UART helper python/capture_v4_adc_uart.py prepared; four parser regression tests PASS. Live UART/reset/capture functionality has NOT been tested in this task. It requires completed physical and binary confirmation, performs one reset, validates golden/CRC/boot/mode, captures a bounded interval and preserves original UART plus ADC/prediction CSV and JSON. Preliminary capture report requires post-run review; it never asserts ADC PASS or invents accuracy.
- No COM3 open, reset or flash. No current ADC Golden result, R-peak count, inference result, latency or runtime memory measurement exists from this task. The previous recorded board remains BENCH_INT8; it was not queried.
- User general assurance of safety based on earlier measurements is recorded in physical_status.json; measured supply/OUT voltages, source identity, wiring and isolation details remain missing. Do not substitute earlier replay or benchmark data for ADC results.

See hardware_checklist.md for manual checks; run_plan.md for capture procedure. physical_confirmation.template.json is NOT approved and must not be used to bypass physical review. This preparation is for a no-body simulator bench. It does not authorize or certify testing on humans.

Preserved ready-to-flash copies: adc_application.bin, adc_bootloader.bin, adc_partition_table.bin, adc_sdkconfig. Do not flash until physical checks are reviewed. adc_build_manifest.json records original build paths/hashes. Old experimental evidence is unchanged.
