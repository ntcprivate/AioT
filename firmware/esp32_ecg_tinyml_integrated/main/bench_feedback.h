#pragma once
#include "research_shadow.h"
#include <cstring>

// BENCH DEMO only. Owned by the existing GPIO task; no heap or blocking calls.
class BenchFeedback {
public:
    enum class State { Disabled, Normal, Pvc, Unknown, Invalid, LeadsOff };
    struct Output { bool led=false,buzzer=false; };
    explicit BenchFeedback(bool enabled):enabled_(enabled){}
    static State select(bool leads,bool invalid,bool unknown,const ecg_ai::View& v,int64_t now) {
        if(leads)return State::LeadsOff;
        if(invalid || std::strcmp(v.state,"INVALID")==0)return State::Invalid;
        if(unknown || !ecg_ai::fresh(v,now) || !v.classified || v.r_sample<128 ||
            std::strcmp(v.reason,"CNN_PREDICTION")!=0 || !std::isfinite(v.probability))return State::Unknown;
        if(std::strcmp(v.state,"PVC")==0)return State::Pvc;
        if(std::strcmp(v.state,"NORMAL")==0)return State::Normal;
        return State::Unknown;
    }
    Output step(int64_t now,State requested) {
        if(!enabled_)requested=State::Disabled;
        if(requested!=state_ || now<last_) {state_=requested;start_=now;}
        last_=now;
        const int64_t elapsed=now-start_;
        switch(state_) {
        case State::Normal: {const bool on=(elapsed%1000000)<500000;return {on,on};}
        case State::Pvc:return {true,(elapsed%400000)<200000};
        case State::Unknown:
        case State::Invalid:return {false,(elapsed%2000000)<1000000};
        case State::LeadsOff:return {true,false};
        default:return {};
        }
    }
private:
    const bool enabled_;State state_=State::Disabled;int64_t start_=0,last_=0;
};
