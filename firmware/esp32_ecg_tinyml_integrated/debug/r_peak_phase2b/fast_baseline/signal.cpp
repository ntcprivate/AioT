#include "signal.h"
#include <algorithm>
#include <cmath>
#include "sdkconfig.h"

SignalMetrics signal_metrics(const int* raw) {
    SignalMetrics m={};int lo=4095,hi=0;double mean=0,diff=0,first=0,last=0;
    for(int i=0;i<256;++i) {lo=std::min(lo,raw[i]);hi=std::max(hi,raw[i]);mean+=raw[i];
        m.clips+=raw[i]<=CONFIG_ECG_ADC_RAIL_MARGIN || raw[i]>=4095-CONFIG_ECG_ADC_RAIL_MARGIN;
        if(i)diff+=std::abs(raw[i]-raw[i-1]);
        if(i<64)first+=raw[i];
        if(i>=192)last+=raw[i];
    }
    mean/=256;m.ptp=hi-lo;m.diff_percent=m.ptp?100*diff/(255*m.ptp):0;m.baseline_delta=(last-first)/64;
    double re=0,im=0,energy=0;
    for(int i=0;i<256;++i) {const double x=raw[i]-mean,angle=6.283185307179586*50*i/250;
        re+=x*std::cos(angle);im-=x*std::sin(angle);energy+=x*x;}
    m.power50_ratio=energy>0?std::min(1.0,2*(re*re+im*im)/(256*energy)):0;
    return m; // Diagnostic estimate only; does not loosen any quality threshold.
}

const char* signal_block_reason(const int* raw,const int64_t* timestamps) {
    int minimum=4095,maximum=0; double differences=0;
    for(int i=0;i<256;++i) {
        if(raw[i]<=CONFIG_ECG_ADC_RAIL_MARGIN || raw[i]>=4095-CONFIG_ECG_ADC_RAIL_MARGIN) return "ADC_SATURATION";
        minimum=std::min(minimum,raw[i]); maximum=std::max(maximum,raw[i]);
        if(i) {
            const int64_t dt=timestamps[i]-timestamps[i-1];
            if(dt<2000 || dt>6000) return "TIMING_DISCONTINUITY";
            differences+=std::abs(raw[i]-raw[i-1]);
        }
    }
    if(maximum-minimum<CONFIG_ECG_MIN_BLOCK_PTP) return "FLAT_OR_TOO_SMALL";
    if(100*differences/255 > CONFIG_ECG_MAX_DIFF_PERCENT*(maximum-minimum)) return "HIGH_FREQUENCY_NOISE";
    return nullptr; // Necessary checks only; not proof of ECG validity.
}
void BeatWindowBuffer::reset() {
    stats_.dropped_reset+=size_;
    if(size_)last_drop_reason_="WINDOW_CANCELLED_BY_RESET";
    head_=size_=0;first_=last_=-1;
    // Invalidate history instead of zeroing a 6KiB ring on the worker stack.
}
bool BeatWindowBuffer::append(int raw,int64_t sample,int64_t timestamp,const char*& issue) {
    issue=nullptr;
    if(sample<0 || (last_>=0 && sample!=last_+1)) {issue="BEAT_SAMPLE_INDEX_GAP";return false;}
    if(first_<0)first_=sample;
    ring_[sample%kRingSamples]=raw;times_[sample%kRingSamples]=timestamp;last_=sample;
    return true;
}
bool BeatWindowBuffer::enqueue(int64_t center,const char*& issue) {
    issue=nullptr;
    if(center==last_enqueued_) {++stats_.duplicate;issue=last_drop_reason_="DUPLICATE_R_CENTER";return false;}
    if(center<last_enqueued_) {++stats_.out_of_order;issue=last_drop_reason_="R_CENTER_OUT_OF_ORDER";return false;}
    if(center<128 || first_<0 || center-128<first_ || center>last_ || last_-(center-128)>=kRingSamples) {
        ++stats_.invalid_center;issue=last_drop_reason_="R_CENTER_HISTORY_UNAVAILABLE";return false;
    }
    // Drop newest explicitly. Existing windows remain intact, never reset for overlap/full.
    if(size_==kPendingCapacity) {++stats_.dropped_full;issue=last_drop_reason_="PENDING_QUEUE_FULL";return false;}
    pending_[(head_+size_)%kPendingCapacity]={center,times_[center%kRingSamples]};
    ++size_;++stats_.enqueued;stats_.high_water=std::max<uint32_t>(stats_.high_water,size_);last_enqueued_=center;
    return true;
}
bool BeatWindowBuffer::pop_ready(float* beat,BeatWindowInfo& info,const char*& issue) {
    issue=nullptr;
    if(!size_ || last_<pending_[head_].sample+127)return false;
    const Center center=pending_[head_];
    head_=(head_+1)%kPendingCapacity;--size_;
    const int64_t start=center.sample-128,end=center.sample+127;
    if(!beat || start<first_ || last_-start>=kRingSamples || times_[center.sample%kRingSamples]!=center.timestamp) {
        ++stats_.overwritten;issue=last_drop_reason_="BEAT_RING_HISTORY_UNAVAILABLE";return false;
    }
    if(center.sample<=last_emitted_) {++stats_.out_of_order;issue=last_drop_reason_="BEAT_OUTPUT_OUT_OF_ORDER";return false;}
    // Validate the complete window before exposing any morphology to the caller.
    for(int i=1;i<256;++i) {
        const int64_t dt=times_[(start+i)%kRingSamples]-times_[(start+i-1)%kRingSamples];
        if(dt<2000 || dt>6000) {++stats_.timing_errors;issue=last_drop_reason_="BEAT_TIMING_GAP";return false;}
    }
    for(int i=0;i<256;++i)beat[i]=ring_[(start+i)%kRingSamples];
    info={center.sample,center.timestamp,start,end};last_emitted_=center.sample;++stats_.completed;
    return true;
}
void BeatDetector::reset_state() {
    windows_.reset();last_window_={};count_=0;last_center_=-1;
    baseline_=envelope_=prev_abs_=before_abs_=0;
    candidate_active_=false;last_timestamp_=0;no_peak_reported_=false;
}
void BeatDetector::reset() {++counters_.external_resets;reset_state();}
BeatDetectorStats BeatDetector::stats() const {
    return {counters_.samples,counters_.candidates,counters_.warmup_samples,
        counters_.no_peak_resets,counters_.external_resets,windows_.stats(),no_peak_events_};
}
bool BeatDetector::push(int raw,int64_t timestamp,float* beat,const char*& issue) {
    issue=nullptr;const int64_t sample=next_sample_++;const int64_t current=count_++;
    ++counters_.samples;if(current<500)++counters_.warmup_samples;
    if(raw<0 || raw>4095 || timestamp<0) {issue="INVALID_ADC_SAMPLE";reset_state();return false;}
    if(current>0 && (timestamp-last_timestamp_<2000 || timestamp-last_timestamp_>6000)) {
        issue="BEAT_TIMING_GAP";reset_state();return false;
    }
    last_timestamp_=timestamp;
    if(!windows_.append(raw,sample,timestamp,issue)) {reset_state();return false;}
    if(current==0)baseline_=raw;
    baseline_+=0.025f*(raw-baseline_);
    const float magnitude=std::abs(raw-baseline_);
    envelope_+=0.01f*(magnitude-envelope_);
    const float threshold=std::max(static_cast<float>(CONFIG_ECG_QRS_MIN_COUNTS),2.5f*envelope_);
    if(current>=500 && prev_abs_>before_abs_ && prev_abs_>=magnitude && prev_abs_>threshold) {
        const int64_t center=sample-1;
        if(last_center_<0 || center-last_center_>=75) {
            if(!candidate_active_) {candidate_active_=true;candidate_start_=sample;candidate_center_=center;candidate_strength_=prev_abs_;}
            else if(prev_abs_>candidate_strength_) {candidate_center_=center;candidate_strength_=prev_abs_;}
        }
    }
    before_abs_=prev_abs_;prev_abs_=magnitude;
    if(candidate_active_ && sample-candidate_start_>=50) {
        candidate_active_=false;++counters_.candidates;last_center_=candidate_center_;no_peak_reported_=false;
        if(!windows_.enqueue(candidate_center_,issue))return false;
    }
    if(windows_.pop_ready(beat,last_window_,issue))return true;
    if(issue) {reset_state();return false;}
    if(current>1000 && (last_center_<0 || sample-last_center_>500) && !no_peak_reported_) {
        issue="NO_RELIABLE_R_PEAK";no_peak_reported_=true;++no_peak_events_;
    }
    return false;
}
