#pragma once
#include "signal.h"
#include <cstdint>
#include <cmath>
namespace research {
constexpr int64_t kResultLifetimeUs=1500000,kMaxWindowAgeUs=1500000;
struct View {
    const char* state="UNKNOWN";const char* reason="MODEL_VALIDATION_PENDING";
    float probability=0;bool has_result=false;
    int64_t r_sample=-1,r_us=0,window_end_us=0,result_us=0,valid_until_us=0,latency_us=0,prep_us=0;
    uint32_t classified=0,rejected=0,queue_drops=0,invalid_blocks=0,block_drops=0,inference_calls=0;
    uint32_t detected=0,queue_depth=0,queue_high_water=0,heap_free=0,heap_min=0,stack_free=0;
};
inline void clear(View& v,const char* reason,bool invalid=false) {
    v.has_result=false;v.probability=0;v.state=invalid?"INVALID":"UNKNOWN";v.reason=reason;
    v.r_sample=-1;v.r_us=v.window_end_us=v.result_us=v.valid_until_us=v.latency_us=v.prep_us=0;
}
inline bool fresh(const View& v,int64_t now) {
    return v.has_result && now>=v.result_us && now<=v.valid_until_us;
}
inline bool publish(View& v,float score,int64_t now,int64_t r_sample,int64_t r_us,int64_t end_us,int64_t latency,int64_t prep,bool safe) {
    if(!safe || !std::isfinite(score) || score<0 || score>1 || now<end_us || now-end_us>kMaxWindowAgeUs) {
        ++v.rejected;clear(v,safe?"BEAT_TOO_OLD":"SIGNAL_CHANGED_DURING_INFERENCE");return false;
    }
    ++v.classified;v.has_result=true;v.state=score>=0.52f?"PVC":"NORMAL";v.reason="CNN_RESEARCH_PREDICTION";
    v.probability=score;v.r_sample=r_sample;v.r_us=r_us;v.window_end_us=end_us;v.result_us=now;
    v.valid_until_us=now+kResultLifetimeUs;v.latency_us=latency;v.prep_us=prep;return true;
}
struct Window {float raw[256];int64_t r_sample,r_us,end_us;uint32_t generation;};
// Single model worker owns detector and four immutable window copies. No heap.
class Engine {
public:
    static constexpr unsigned kCapacity=4;
    void reset() {rejected+=size_;head_=size_=0;detector_.reset();aligned_=false;}
    bool enqueue(const Window& w) {
        if(size_==kCapacity){++drops;++rejected;return false;}
        queue_[(head_+size_)%kCapacity]=w;++size_;if(size_>high_water)high_water=size_;return true;
    }
    bool pop(Window& w) {if(!size_)return false;w=queue_[head_];head_=(head_+1)%kCapacity;--size_;return true;}
    const char* push(int raw,int64_t time,int64_t adc_index,uint32_t generation) {
        if(!aligned_){offset_=adc_index-static_cast<int64_t>(detector_.stats().samples);aligned_=true;}
        const char* issue=nullptr;
        if(detector_.push(raw,time,scratch_.raw,issue)) {
            const auto& info=detector_.last_window();scratch_.r_sample=info.center_sample+offset_;scratch_.r_us=info.center_timestamp;
            scratch_.end_us=time;scratch_.generation=generation;
            if(!enqueue(scratch_))return "SHADOW_QUEUE_FULL";
        }
        return issue;
    }
    unsigned depth() const{return size_;}
    unsigned detected() const{return static_cast<unsigned>(detector_.stats().candidates);}
    uint32_t total_rejected() const {
        const auto w=detector_.stats().windows;
        return rejected+static_cast<uint32_t>(w.dropped_full+w.dropped_reset+w.duplicate+w.out_of_order+w.invalid_center+w.overwritten+w.timing_errors);
    }
    uint32_t drops=0,rejected=0,high_water=0;
private:
    BeatDetector detector_;Window queue_[kCapacity]={},scratch_={};unsigned head_=0,size_=0;
    bool aligned_=false;int64_t offset_=0;
};
} // namespace research
