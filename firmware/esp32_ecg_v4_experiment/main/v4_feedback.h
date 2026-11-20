#pragma once
#include "system_state.h"
#include <cstdint>

// GPIO23 LED and GPIO25 active buzzer are wired active HIGH.
// No inference, GPIO access, allocation or waiting in this state machine.
class V4Feedback {
public:
    static EcgState select(bool invalid, bool ready, bool fresh,
                           bool normal, bool pvc) {
        if(invalid) return EcgState::Invalid;
        if(!ready || !fresh) return EcgState::Waiting;
        if(pvc) return EcgState::Pvc;
        if(normal) return EcgState::Normal;
        return EcgState::Waiting;
    }
    AlertOutput step(int64_t now,EcgState state) {
        if(!initialized_ || state!=state_ || now<phase_) {
            initialized_=true;state_=state;phase_=now;
        }
        const int64_t elapsed=now-phase_;
        switch(state) {
            case EcgState::Waiting:return {elapsed%2000000<1000000,false};
            case EcgState::Normal:return {true,false};
            case EcgState::Pvc:{const bool on=elapsed%400000<200000;return {on,on};}
            default:return {false,false};
        }
    }
private:
    bool initialized_=false;
    EcgState state_=EcgState::Invalid;
    int64_t phase_=0;
};
