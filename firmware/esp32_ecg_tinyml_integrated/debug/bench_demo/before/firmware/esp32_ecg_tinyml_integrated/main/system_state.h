#pragma once
#include <cstdint>
enum class EcgState { Waiting, Collecting, Normal, Pvc, Invalid, Fault };
inline const char* state_name(EcgState s) {
    switch(s) {
        case EcgState::Waiting:return "WAITING";
        case EcgState::Collecting:return "COLLECTING";
        case EcgState::Normal:return "NORMAL";
        case EcgState::Pvc:return "PVC";
        case EcgState::Invalid:return "SIGNAL_INVALID";
        default:return "SYSTEM_FAULT";
    }
}
struct AlertOutput { bool led,buzzer; };
inline AlertOutput alert_pattern(EcgState s,int64_t elapsed) {
    switch(s) {
        case EcgState::Waiting:return {elapsed%1000000<500000,false};
        case EcgState::Collecting:return {elapsed%1000000<80000,false};
        case EcgState::Invalid:return {elapsed%333333<166666,false};
        case EcgState::Fault:return {elapsed%2000000<100000 || (elapsed%2000000>=250000 && elapsed%2000000<350000),false};
        case EcgState::Normal:return {true,false};
        case EcgState::Pvc:{ bool on=elapsed%500000<150000;return {on,on}; }
    }
    return {false,false};
}
inline bool recovery_allowed(EcgState state,bool system_fault,uint32_t samples,uint32_t good_blocks,bool same_generation) {
    return state==EcgState::Invalid && !system_fault && samples>=512 && good_blocks>=2 && same_generation;
}
