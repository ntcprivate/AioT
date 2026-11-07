#pragma once
#include <cstdint>
bool model_init();
bool model_invoke_quantized(const int8_t* input, float& score, int& output, int64_t& latency_us);
bool model_invoke_beat(const float* raw_beat, float& score, int64_t& latency_us, unsigned& clipped);
bool model_golden_test();
