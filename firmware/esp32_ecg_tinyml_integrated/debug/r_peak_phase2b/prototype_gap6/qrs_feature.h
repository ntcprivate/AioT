#pragma once
#include <cmath>
#include <cstdint>
// Detection-only causal, symmetric second-difference after three-sample averaging.
// Delay is explicit: feature at input n refers to n-Gap-1. Raw CNN data is untouched.
template<unsigned Gap> class CausalQrsFeature {
public:
    static_assert(Gap>=6 && Gap<=10,"Reviewed250Hz development range");
    void reset() {age_=0;envelope_=prev_=before_=0;cluster_=false;}
    bool push(int raw,int64_t sample,float baseline,int64_t& center,float& strength) {
        history_[sample%64]=raw;++age_;
        if(age_<2*Gap+3)return false;
        const float middle=average(sample-Gap);
        const float magnitude=std::abs(middle-0.5f*(average(sample-2*Gap)+average(sample)));
        envelope_+=0.01f*(magnitude-envelope_);
        const float threshold=std::fmax(10.0f,2.5f*envelope_);
        if(prev_>before_ && prev_>=magnitude && prev_>threshold) {
            // Local feature maximum at the preceding sample, including smoothing delay.
            const int64_t peak=sample-Gap-2;
            if(!cluster_) {cluster_=true;cluster_start_=sample;cluster_center_=peak;cluster_strength_=prev_;}
            else if(prev_>cluster_strength_) {cluster_center_=peak;cluster_strength_=prev_;}
        }
        before_=prev_;prev_=magnitude;
        if(!cluster_ || sample-cluster_start_<20)return false; //80ms bounded confirmation.
        cluster_=false;
        // Localize to raw morphology within24ms, without annotation/zero-phase lookahead.
        center=cluster_center_;float best=-1;
        for(int offset=-6;offset<=6;++offset) {
            const int64_t k=cluster_center_+offset;
            if(k<0 || k>sample || sample-k>=64)continue;
            const float value=std::abs(history_[k%64]-baseline);
            if(value>best) {best=value;center=k;}
        }
        strength=cluster_strength_;
        return best>=30.0f; //Retain original absolute raw amplitude floor for localization.
    }
private:
    float average(int64_t k) const {return (history_[k%64]+history_[(k-1)%64]+history_[(k-2)%64])/3.0f;}
    float history_[64]={},envelope_=0,prev_=0,before_=0,cluster_strength_=0;
    int64_t cluster_start_=0,cluster_center_=0;
    unsigned age_=0;
    bool cluster_=false;
};
