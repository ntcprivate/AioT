# ADC V4 preflight - NOT RUN

Status: WAITING_HARDWARE_CONFIRMATION. No new build, COM3 access, reset, flash, UART capture or analog measurement was performed. The last documented board image is BENCH_INT8 V4; its current contents were not queried.

## Source checks

- V4 INT8 SHA-256: a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e.
- Threshold 0.88; output INT8 code >= 98.
- ADC1 channel 6 / GPIO34; 12 bit; 12 dB attenuation. LO+ GPIO27, LO- GPIO26, input without pulls.
- GPTimer period 4000 us (250 Hz); ISR only notifies the sampling task.
- Window 256 samples; existing detector confirmation 50 / refractory 75 samples and FIFO retained. Existing z-score, rounding, clipping and signal-quality checks retained.
- ADC mode selects main.cpp, not replay_main.cpp or benchmark.cpp. A newly configured ADC binary still needs verification before flashing.
- Lead-off, ADC error, gaps, integrity/generation, block quality, normalization, quantization clipping and freshness gates remain active. Recovery requires 512 good samples and two good blocks. These checks do not establish clinical ECG validity.

## Required physical checks

Before flashing or measuring, the user must identify the simulator or appropriately verified isolated source, confirm no body connection, report measured AD8232 supply and OUT offset/minimum/maximum, and verify OUT->34, LO+->27, LO-->26 and common GND. Attenuation is not proof of safe voltage or calibrated linear range. Do not connect an unknown or overvoltage source to the GPIO.

Also record simulator lead/rate/amplitude/PVC settings, synchronized reference availability and requested capture duration. Earlier digital replay bench confirmations do not verify this analog setup.

## Measurement plan after confirmation

Verify ADC build mode, CPU/configuration and model/binary hashes. Capture raw UART before a single reset; require 22/22 golden results. Separate boot/golden startup from the actual measurement interval after model readiness and recovery. Use bounded continuous capture, not replay END markers. Validate CRC, boot identity, sequence/sample indices and drops. Export raw ADC samples and per-beat outputs with rejection reasons when available.

Without trustworthy synchronized labels, report predictions and technical metrics only; leave confusion matrix and F1 unavailable. Do not use model predictions as reference labels. The GUI's legacy 0.52 validation must not be used to score V4 output at threshold 0.88.

## Evidence in this folder

- firmware_preflight.json: source hashes and historical ADC binary hash; historical build evidence is not a new hardware result.
- session_metadata.json: pending physical details and explicit actions-not-performed.
- adc_metrics.json: NOT_RUN; unmeasured values are null.
- predictions.csv: header only, no observations.
- No uart_raw.log was created because no UART session occurred.

Decision: NOT READY for analog measurement until the requested physical checks are supplied. No analog end-to-end PASS is claimed.
