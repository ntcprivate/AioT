#include "research_shadow.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
int main() {
    research::View v;
    assert(!v.has_result);
    // Recorded golden output codes -126 (N) and7 (PVC), not fake inference.
    assert(research::publish(v,2/256.f,2000000,250,1500000,1999999,81000,2300,true));
    assert(strcmp(v.state,"NORMAL")==0 && research::fresh(v,2000000));
    assert(!research::fresh(v,3500001));
    assert(research::publish(v,135/256.f,2000000,250,1500000,1999999,81000,2300,true));
    assert(strcmp(v.state,"PVC")==0);
    assert(!research::publish(v,135/256.f,2000000,250,1500000,1999999,81000,2300,false));
    assert(!v.has_result);
    for(auto issue:{"LEADS_OFF","ADC_SATURATION","SAMPLE_GAP","HIGH_FREQUENCY_NOISE"}) {
        research::clear(v,issue,true);assert(!v.has_result && strcmp(v.state,"INVALID")==0);
    }
    assert(!research::publish(v,135/256.f,4000000,250,1500000,1999999,81000,2300,true));
    research::Engine engine;research::Window w={},out={};w.raw[0]=123;
    for(unsigned i=0;i<4;++i){w.r_sample=i+500;assert(engine.enqueue(w));}
    w.raw[0]=456;assert(!engine.enqueue(w));assert(engine.drops==1 && engine.depth()==4);
    for(unsigned i=0;i<4;++i){assert(engine.pop(out));assert(out.r_sample==i+500 && out.raw[0]==123);}
    assert(!engine.pop(out));assert(engine.high_water==4);
    engine.enqueue(w);engine.reset();assert(!engine.pop(out));assert(engine.rejected==2);
    bool no_peak=false;
    for(int i=0;i<1600;++i){const char* r=engine.push(2048,1000000+i*4000LL,i+10240,3);if(r && !strcmp(r,"NO_RELIABLE_R_PEAK"))no_peak=true;}
    assert(no_peak && engine.detected()==0 && engine.depth()==0);
    // Rebase ADC indices after startup/skipped blocks. No detector changes.
    engine.reset();
    BeatDetector reference;float reference_beat[256];const char* reference_issue=nullptr;
    for(int i=0;i<2000;++i){int phase=i%200;const int raw=2048+(phase==99?200:phase==100?600:phase==101?200:0);
        const bool expected=reference.push(raw,10000000+i*4000LL,reference_beat,reference_issue);
        engine.push(raw,10000000+i*4000LL,i+20000,4);
        const bool emitted=engine.pop(out);assert(emitted==expected);
        if(emitted){assert(out.r_sample>=20000 && out.generation==4);assert(out.r_us==10000000+(out.r_sample-20000)*4000LL);
            assert(out.r_sample==reference.last_window().center_sample+20000);assert(out.end_us==10000000+i*4000LL);
            assert(std::memcmp(out.raw,reference_beat,sizeof(reference_beat))==0);}
    }
    assert(engine.detected()>0);
    int raw[256];int64_t times[256];for(int i=0;i<256;++i){raw[i]=2048;times[i]=i*4000LL;}
    assert(!strcmp(signal_block_reason(raw,times),"FLAT_OR_TOO_SMALL"));
    raw[10]=4095;assert(!strcmp(signal_block_reason(raw,times),"ADC_SATURATION"));
    raw[10]=2148;times[12]+=3000;assert(!strcmp(signal_block_reason(raw,times),"TIMING_DISCONTINUITY"));
    for(int i=0;i<256;++i){raw[i]=2048+int(100*std::sin(6.283185307179586*50*i/250));times[i]=i*4000LL;}
    assert(signal_block_reason(raw,times));
    std::printf("PASS: shadow queues, immutable windows, index rebasing, stale/safety, no-peak and quality controls\n");
}
