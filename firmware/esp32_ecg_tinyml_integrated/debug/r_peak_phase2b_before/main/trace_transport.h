#pragma once
#include <cstddef>
#include <cstdint>
// One recursive lock for ALL application task stdout writers, plus stdio lock.
void console_lock();
void console_unlock();
bool console_trace_active();
void console_trace_start();
void console_trace_stop();
uint32_t console_trace_errors();
// Bounded, single record + per-line FNV; checks snprintf/fwrite/fflush results.
bool console_trace_line(const char* format, ...) __attribute__((format(printf,1,2)));
