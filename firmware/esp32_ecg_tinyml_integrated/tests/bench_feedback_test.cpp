#include "bench_feedback.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
using S=BenchFeedback::State;
void expect(BenchFeedback::Output o,bool led,bool buzzer){assert(o.led==led && o.buzzer==buzzer);}
ecg_ai::View prediction(bool pvc,int64_t t){ecg_ai::View v;assert(ecg_ai::publish(v,pvc?135/256.f:2/256.f,t,1000,t-508000,t,81000,2300,true));return v;}
int main(){
    constexpr int64_t t=2000000;
    BenchFeedback off(false);for(auto s:{S::Normal,S::Pvc,S::Unknown,S::Invalid,S::LeadsOff})expect(off.step(t,s),false,false);
    BenchFeedback n(true);expect(n.step(t,S::Normal),true,true);expect(n.step(t+499999,S::Normal),true,true);expect(n.step(t+500000,S::Normal),false,false);expect(n.step(t+999999,S::Normal),false,false);expect(n.step(t+1000000,S::Normal),true,true);
    BenchFeedback p(true);expect(p.step(t,S::Pvc),true,true);expect(p.step(t+199999,S::Pvc),true,true);expect(p.step(t+200000,S::Pvc),true,false);expect(p.step(t+399999,S::Pvc),true,false);expect(p.step(t+400000,S::Pvc),true,true);
    for(auto s:{S::Unknown,S::Invalid}){BenchFeedback b(true);expect(b.step(t,s),false,true);expect(b.step(t+999999,s),false,true);expect(b.step(t+1000000,s),false,false);expect(b.step(t+2000000,s),false,true);}
    expect(p.step(t+450000,S::LeadsOff),true,false);expect(p.step(t+5000000,S::LeadsOff),true,false);
    // Transition resets phase immediately, even if the prior state's OFF phase was active.
    BenchFeedback tr(true);expect(tr.step(t,S::Normal),true,true);expect(tr.step(t+500000,S::Normal),false,false);expect(tr.step(t+500001,S::Pvc),true,true);expect(tr.step(t+500002,S::Invalid),false,true);expect(tr.step(t+500003,S::LeadsOff),true,false);expect(tr.step(t+500004,S::Unknown),false,true);
    auto v=prediction(true,t);assert(BenchFeedback::select(true,true,true,v,t)==S::LeadsOff);assert(BenchFeedback::select(false,true,true,v,t)==S::Invalid);assert(BenchFeedback::select(false,false,true,v,t)==S::Unknown);assert(BenchFeedback::select(false,false,false,v,t)==S::Pvc);
    v=prediction(false,t);assert(BenchFeedback::select(false,false,false,v,t)==S::Normal);
    assert(BenchFeedback::select(false,false,false,v,v.valid_until_us+1)==S::Unknown);
    ecg_ai::clear(v,"LEADS_OFF",true);assert(BenchFeedback::select(true,false,false,v,t)==S::LeadsOff);assert(BenchFeedback::select(false,false,false,v,t)==S::Invalid);
    v=prediction(true,t);v.reason="STATIC_GOLDEN_DATA";assert(BenchFeedback::select(false,false,false,v,t)==S::Unknown);
    v=prediction(true,t);v.probability=NAN;assert(BenchFeedback::select(false,false,false,v,t)==S::Unknown);
    v=prediction(true,t);v.has_result=false;assert(BenchFeedback::select(false,false,false,v,t)==S::Unknown);
    // A newer same-class prediction does not restart the oscillator on every beat.
    BenchFeedback held(true);held.step(t,S::Normal);auto newer=prediction(false,t+600000);expect(held.step(t+600000,BenchFeedback::select(false,false,false,newer,t+600000)),false,false);
    expect(held.step(t-1,S::Normal),true,true); // Clock rewind safely restarts phase.
    puts("PASS: default OFF,500ms NORMAL,200ms PVC,1000ms UNKNOWN/INVALID,LEADS_OFF,transitions,priority,fresh CNN only,same-state continuity,clock rewind");
}
