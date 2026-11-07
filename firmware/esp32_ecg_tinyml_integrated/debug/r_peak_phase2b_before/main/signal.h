#pragma once
#include <cstdint>
// Signal-only heuristics, not an ECG validity certification.
const char* signal_block_reason(const int* raw, const int64_t* timestamps);
struct SignalMetrics {uint32_t clips;int ptp;double diff_percent,power50_ratio,baseline_delta;};
SignalMetrics signal_metrics(const int* raw);
struct BeatWindowInfo {
    int64_t center_sample=-1, center_timestamp=0;
    int64_t start_sample=-1, end_sample=-1;
};
struct BeatWindowStats {
    uint64_t enqueued=0, completed=0, dropped_full=0, dropped_reset=0;
    uint64_t duplicate=0, out_of_order=0, invalid_center=0, overwritten=0, timing_errors=0;
    uint32_t high_water=0;
};
// Single worker owns this object. No allocations or waits; raw morphology stays unchanged.
class BeatWindowBuffer {
public:
    static constexpr unsigned kRingSamples=512, kPendingCapacity=4;
    void reset(); // Cancel outstanding windows; retain lifetime diagnostics/order history.
    bool append(int raw,int64_t sample,int64_t timestamp,const char*& issue);
    bool enqueue(int64_t center,const char*& issue);
    bool pop_ready(float* beat,BeatWindowInfo& info,const char*& issue);
    unsigned pending_count() const {return size_;}
    int64_t first_pending_center() const {return size_?pending_[head_].sample:-1;}
    const BeatWindowStats& stats() const {return stats_;}
    const char* last_drop_reason() const {return last_drop_reason_;}
private:
    struct Center {int64_t sample=0,timestamp=0;};
    float ring_[kRingSamples]={};
    int64_t times_[kRingSamples]={};
    Center pending_[kPendingCapacity]={};
    int64_t first_=-1,last_=-1,last_enqueued_=-1,last_emitted_=-1;
    unsigned head_=0,size_=0;
    BeatWindowStats stats_={};
    const char* last_drop_reason_=nullptr;
};
struct BeatDetectorStats {
    uint64_t samples=0,candidates=0,warmup_samples=0,no_peak_resets=0,external_resets=0;
    BeatWindowStats windows={};
};
class BeatDetector {
public:
    void reset();
    // Returns [center-128,center+128) only after its last sample exists.
    // Detection signal only is baseline-removed; returned morphology is raw.
    bool push(int raw, int64_t timestamp, float* beat, const char*& issue);
    const BeatWindowInfo& last_window() const {return last_window_;}
    BeatDetectorStats stats() const;
    unsigned pending_count() const {return windows_.pending_count();}
private:
    void reset_state();
    BeatWindowBuffer windows_;
    BeatWindowInfo last_window_={};
    struct {uint64_t samples=0,candidates=0,warmup_samples=0,no_peak_resets=0,external_resets=0;} counters_;
    // Absolute sample index survives resets; count_ remains detector warm-up age.
    int64_t next_sample_=0,count_=0,last_center_=-1;
    float baseline_ = 0, envelope_ = 0, prev_abs_ = 0, before_abs_ = 0;
};
