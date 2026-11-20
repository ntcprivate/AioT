#pragma once
#include <cstdint>
#include "esp_err.h"
esp_err_t telemetry_init();
esp_err_t telemetry_uart_init();
void telemetry_sample(int raw,int64_t timestamp,uint8_t plus,uint8_t minus,bool adc_error,bool missed);
void telemetry_health(uint32_t adc_errors,uint32_t missed,uint32_t late,bool snapshot_ok,
    uint32_t intervals,int64_t first_us,int64_t last_us,int64_t dt_min,int64_t dt_max);
// Read-only atomic diagnostic snapshot; no wire-protocol fields are changed.
struct TelemetryTestHealth {uint32_t attempts,drops,adc_errors,missed,late,snapshot_errors,write_errors,format_errors,uart_errors,timeouts;double acquisition_hz;};
TelemetryTestHealth telemetry_test_health();
