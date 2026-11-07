#pragma once
#include <cstdint>
#include "esp_err.h"
esp_err_t telemetry_init();
void telemetry_sample(int raw,int64_t timestamp,uint8_t plus,uint8_t minus,bool adc_error,bool missed);
void telemetry_health(uint32_t adc_errors,uint32_t missed,uint32_t late,bool snapshot_ok);
