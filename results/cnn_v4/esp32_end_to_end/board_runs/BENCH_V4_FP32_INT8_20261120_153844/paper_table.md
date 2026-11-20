| Metric | FP32 | INT8 |
|---|---:|---:|
| Invoke_mean (ms) | 34.472409 | 83.084818 |
| Invoke_median (ms) | 34.474500 | 83.088000 |
| Invoke_min (ms) | 34.441000 | 83.064000 |
| Invoke_max (ms) | 34.492000 | 83.093000 |
| Invoke_p95 (ms) | 34.485000 | 83.093000 |
| Invoke_sample_SD (ms) | 0.010572 | 0.009081 |
| Window_to_raw_output_mean (ms) | 36.294545 | 86.771182 |
| Window_to_raw_output_median (ms) | 36.295500 | 86.775000 |
| Window_to_raw_output_min (ms) | 36.210000 | 86.698000 |
| Window_to_raw_output_max (ms) | 36.366000 | 86.837000 |
| Window_to_raw_output_p95 (ms) | 36.360000 | 86.836000 |
| Window_to_raw_output_sample_SD (ms) | 0.037803 | 0.033730 |
| model_bytes | 9584 | 8688 |
| application_bytes | 273936 | 270576 |
| static_DRAM_bytes | 14996 | 15532 |
| static_IRAM_bytes | 49634 | 49634 |
| arena_used_bytes | 18120 | 6124 |
| arena_allocated_bytes | 65536 | 65536 |
| minimum_free_heap_bytes | 230912 | 230376 |
| main_stack_high_water_free_bytes | 6616 | 6592 |
| main_stack_peak_used_estimate_bytes | 1576 | 1600 |

ESP32-D0WD-V3 rev3.1,160MHz,ESP-IDF5.4.4,TFLM1.4.2,ESP-NN disabled. Same22 windows,3 warm-up+30 measured per fixture,660 measurements/backend. P95 linear interpolation; sample SD(ddof1). One boot per backend; pooled timing repeats are not independent board sessions. UART/delay excluded; total ends on Invoke return, excludes score read/dequantization/threshold formatting. These are window-level timings, not R-peak/ADC latency.