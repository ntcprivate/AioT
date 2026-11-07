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
void BeatDetector::reset() { *this=BeatDetector{}; }
bool BeatDetector::push(int raw,int64_t timestamp,float* beat,const char*& issue) {
    issue=nullptr;
    const int64_t current=count_++;
    ring_[current%512]=raw; times_[current%512]=timestamp;
    if(current==0) baseline_=raw;
    baseline_+=0.01f*(raw-baseline_);
    const float magnitude=std::abs(raw-baseline_);
    envelope_+=0.01f*(magnitude-envelope_);
    const float threshold=std::max(static_cast<float>(CONFIG_ECG_QRS_MIN_COUNTS),2.5f*envelope_);
    // Experimental polarity-independent magnitude peak; NOT validated R annotation replacement.
    if(current>=500 && prev_abs_>before_abs_ && prev_abs_>=magnitude && prev_abs_>threshold) {
        int64_t center=current-1;
        if(last_center_<0 || center-last_center_>=75) { // >=300ms refractory.
            if(pending_>=0) { issue="AMBIGUOUS_CLOSE_PEAKS"; reset(); return false; }
            pending_=center; last_center_=center;
        }
    }
    before_abs_=prev_abs_; prev_abs_=magnitude;
    if(pending_>=0 && current>=pending_+127) {
        // Python slice [center-128, center+128): center occupies input index 128.
        const int64_t start=pending_-128;
        for(int i=0;i<256;++i) {
            beat[i]=ring_[(start+i)%512];
            if(i) {
                int64_t dt=times_[(start+i)%512]-times_[(start+i-1)%512];
                if(dt<2000 || dt>6000) { issue="BEAT_TIMING_GAP"; reset(); return false; }
            }
        }
        pending_=-1;
        return true;
    }
    if(current>1000 && (last_center_<0 || current-last_center_>500)) {
        issue="NO_RELIABLE_R_PEAK"; reset();
    }
    return false;
}
