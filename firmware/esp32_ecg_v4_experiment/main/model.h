#pragma once
#include <cstdint>
bool model_init();
bool model_invoke_quantized(const int8_t* input, float& score, int& output, int64_t& latency_us);
bool model_golden_test();
bool model_memory_usage(uint32_t& allocated,uint32_t& used);
