#include "v4_feedback.h"
#include "research_shadow.h"
#include <cassert>
#include <cstdio>
int main() {
    V4Feedback f;
    auto check=[&](int64_t t,EcgState s,bool led,bool buzzer) {
        auto o=f.step(t,s);assert(o.led==led && o.buzzer==buzzer);
    };
    auto choose=V4Feedback::select;
    assert(choose(false,false,false,false,false)==EcgState::Waiting);
    check(0,EcgState::Waiting,true,false);
    check(999999,EcgState::Waiting,true,false);
    check(1000000,EcgState::Waiting,false,false);
    check(2000000,EcgState::Waiting,true,false);
    assert(choose(false,true,true,true,false)==EcgState::Normal);
    check(2100000,EcgState::Normal,true,false);
    check(3100000,EcgState::Normal,true,false);
    assert(choose(false,true,true,false,true)==EcgState::Pvc);
    check(3200000,EcgState::Pvc,true,true);
    check(3399999,EcgState::Pvc,true,true);
    check(3400000,EcgState::Pvc,false,false);
    check(3600000,EcgState::Pvc,true,true);
    assert(choose(true,true,true,false,true)==EcgState::Invalid);
    check(3600001,EcgState::Invalid,false,false);
    check(9999999,EcgState::Invalid,false,false);
    // Expired or absent prediction never retains NORMAL/PVC.
    assert(choose(false,true,false,false,true)==EcgState::Waiting);
    assert(choose(false,true,false,true,false)==EcgState::Waiting);
    assert(choose(false,true,true,false,false)==EcgState::Waiting);
    check(10000000,EcgState::Waiting,true,false);
    check(11000000,EcgState::Waiting,false,false);
    check(11000001,EcgState::Pvc,true,true); // New state restarts phase immediately.
    check(11000002,EcgState::Normal,true,false);
    assert(choose(true,false,false,false,false)==EcgState::Invalid);
    ecg_ai::View v;
    assert(ecg_ai::publish(v,226/256.f,1000000,200,100000,608000,100,10,true));
    assert(ecg_ai::fresh(v,2500000));
    assert(!ecg_ai::fresh(v,2500001));
    assert(choose(false,true,ecg_ai::fresh(v,2500001),false,true)==EcgState::Waiting);
    ecg_ai::clear(v,"ADC_SATURATION",true);
    assert(!ecg_ai::fresh(v,1000001));
    puts("PASS: WAITING NORMAL PVC INVALID timing, transitions, expiry, priority");
}
