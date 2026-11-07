#pragma once
#include <cstdint>
// Signal-only heuristics, not an ECG validity certification.
const char* signal_block_reason(const int* raw, const int64_t* timestamps);
struct SignalMetrics {uint32_t clips;int ptp;double diff_percent,power50_ratio,baseline_delta;};
SignalMetrics signal_metrics(const int* raw);
class BeatDetector {
public:
    void reset();
    // Returns a 256-sample window only after 128 post-center samples exist.
    // Detection signal only is baseline-removed; returned morphology is raw.
    bool push(int raw, int64_t timestamp, float* beat, const char*& issue);
private:
    float ring_[512] = {};
    int64_t times_[512] = {};
    int64_t count_ = 0, pending_ = -1, last_center_ = -1;
    float baseline_ = 0, envelope_ = 0, prev_abs_ = 0, before_abs_ = 0;
};
