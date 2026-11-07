#pragma once
#include <cstddef>
#include <cstdint>
#include "esp_err.h"

// Initializes worker/alert tasks. No allocations in the sampling hot path.
esp_err_t pipeline_init();
// Sampling-task only: bounded shared-state update, no UART/ADC/AI calls.
void pipeline_observe(int raw, bool adc_error, bool leads, bool missed, int64_t timestamp);
// Queue copies a completed immutable raw block; never waits for the AI consumer.
void pipeline_offer(uint32_t number, const int* raw, const int64_t* timestamps, bool integrity_ok);
void pipeline_sampling_fault();
struct PipelineTelemetry {
    const char* state; const char* reason;
    bool model_ready,led,buzzer,self_test,quality_known,quality_valid;
    uint32_t clips;int ptp;double diff_percent,power50_ratio,baseline_delta;int64_t quality_time;
};
PipelineTelemetry pipeline_telemetry();

// Single inference payload shared by GUI and CSV.
int pipeline_ai_json(char* output,size_t capacity);
