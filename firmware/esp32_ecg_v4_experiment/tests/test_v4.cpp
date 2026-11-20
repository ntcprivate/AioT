#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <limits>
#include "preprocessing.h"
#include "research_shadow.h"
int main(int argc,char**argv){
    assert(argc==3);std::ifstream rawfile(argv[1],std::ios::binary),qfile(argv[2],std::ios::binary);
    assert(rawfile && qfile);float raw[256],normalized[256];int8_t q[256],expected[256];unsigned clipped=0;
    for(int i=0;i<22;++i){rawfile.read((char*)raw,1024);qfile.read((char*)expected,256);assert(rawfile && qfile);
        assert(ecg_preprocessing::quantize(raw,q,kInputScale,kInputZero,clipped));assert(memcmp(q,expected,256)==0);
        assert(ecg_preprocessing::normalize(raw,normalized));assert(ecg_preprocessing::quantize_normalized(normalized,q,kInputScale,kInputZero,clipped));assert(memcmp(q,expected,256)==0);
    }puts("PASS golden_preprocessing_22_and_split_stages");
    memset(raw,0,sizeof raw);assert(!ecg_preprocessing::quantize(raw,q,kInputScale,kInputZero,clipped));
    raw[0]=std::numeric_limits<float>::quiet_NaN();assert(!ecg_preprocessing::quantize(raw,q,kInputScale,kInputZero,clipped));
    raw[0]=std::numeric_limits<float>::infinity();assert(!ecg_preprocessing::quantize(raw,q,kInputScale,kInputZero,clipped));
    puts("PASS flat_nan_inf_rejected");
    assert(ecg_preprocessing::round_even(2.5)==2 && ecg_preprocessing::round_even(3.5)==4 && ecg_preprocessing::round_even(-2.5)==-2);
    for(float& x:normalized)x=0;normalized[0]=100;normalized[1]=-100;
    assert(ecg_preprocessing::quantize_normalized(normalized,q,kInputScale,kInputZero,clipped) && clipped==2 && q[0]==127 && q[1]==-128);
    puts("PASS_round_even_and_clipping");
    ecg_ai::View v;assert(ecg_ai::publish(v,97/256.f+0.5f,1000,200,0,500,10,10,true));assert(strcmp(v.state,"NORMAL")==0);
    assert(ecg_ai::publish(v,98/256.f+0.5f,1000,200,0,500,10,10,true));assert(strcmp(v.state,"PVC")==0);
    assert(!ecg_ai::fresh(v,1501001));ecg_ai::clear(v,"LEADS_OFF",true);assert(!v.has_result);
    assert(!ecg_ai::publish(v,.99f,2000000,200,0,0,10,10,true));puts("PASS_threshold98_safety_and_stale");
    BeatWindowBuffer w;const char* issue=nullptr;float beat[256];BeatWindowInfo info;
    for(int i=0;i<900;++i){assert(w.append(i,i,i*4000,issue));if(i==600)assert(w.enqueue(600,issue));if(i==650)assert(w.enqueue(650,issue));
        if(w.pop_ready(beat,info,issue)){assert(beat[128]==info.center_sample);assert(beat[0]==info.center_sample-128);}}
    assert(w.stats().completed==2);puts("PASS_overlap_wraparound");
    BeatWindowBuffer full;for(int i=0;i<=400;++i)assert(full.append(i,i,i*4000,issue));
    for(int i=0;i<4;++i)assert(full.enqueue(200+i,issue));assert(!full.enqueue(204,issue));assert(full.stats().dropped_full==1);
    full.reset();assert(full.pending_count()==0);puts("PASS_queue_full_reset");
    int invalid[256]={};int64_t times[256];for(int i=0;i<256;++i)times[i]=i*4000;
    assert(strcmp(signal_block_reason(invalid,times),"ADC_SATURATION")==0);puts("PASS_quality_gate_retained");
    puts("HOST_TEST_GROUPS_PASS=7");
}
