#pragma once
#include "research_shadow.h"
#include <cstring>

// BENCH DEMO only. One owner under the pipeline lock; no heap, sleep or GPIO.
class BenchFeedback {
public:
    static constexpr int64_t kPulseUs=150000,kOffGapUs=10000;
    static constexpr unsigned kCapacity=4;
    explicit BenchFeedback(bool enabled):enabled_(enabled){}
    void cancel() {
        cancelled+=size_+(active_?1:0);head_=size_=0;active_=false;gap_until_=0;
        // Keep last_seen_ so clearing/staling a result cannot replay its beat.
    }
    bool submit(const ecg_ai::View& view,uint32_t generation,int64_t now) {
        if(!enabled_)return false;
        if(!ecg_ai::fresh(view,now) || view.r_sample<128 || !view.classified || std::strcmp(view.reason,"CNN_PREDICTION")!=0) {cancel();return false;}
        if(view.r_sample<=last_seen_) {++duplicates;return false;}
        last_seen_=view.r_sample;
        if(std::strcmp(view.state,"NORMAL")==0){cancel();return true;}
        if(std::strcmp(view.state,"PVC")!=0){cancel();return false;}
        if(size_==kCapacity){++dropped;return false;}
        pending_[(head_+size_)%kCapacity]={view.r_sample,view.valid_until_us,generation};++size_;return true;
    }
    bool step(int64_t now,bool valid_pvc,uint32_t generation) {
        if(!enabled_ || !valid_pvc || now<last_step_) {cancel();last_step_=now;return false;}
        last_step_=now;
        if(active_) {
            if(current_.generation!=generation || now>=current_.expires || now>=off_at_) {
                if(current_.generation==generation && now<current_.expires && now>=off_at_)++completed;else ++cancelled;
                active_=false;gap_until_=now+kOffGapUs;return false;
            }
            return true;
        }
        if(now<gap_until_)return false;
        while(size_) {
            current_=pending_[head_];head_=(head_+1)%kCapacity;--size_;
            if(current_.generation!=generation || now>=current_.expires){++cancelled;continue;}
            active_=true;off_at_=now+kPulseUs;++started;last_started_=current_.sample;return true;
        }
        return false;
    }
    int64_t active_index() const{return last_started_;}
    unsigned pending() const{return size_;}
    uint32_t started=0,completed=0,cancelled=0,duplicates=0,dropped=0;
private:
    struct Event {int64_t sample=0,expires=0;uint32_t generation=0;};
    const bool enabled_;Event pending_[kCapacity]={},current_={};unsigned head_=0,size_=0;
    bool active_=false;int64_t last_seen_=-1,last_started_=-1,off_at_=0,gap_until_=0,last_step_=0;
};
