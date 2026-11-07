// Deterministic numerical unit inputs, NOT clinical ECG validation or AI results.
#include "signal.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>

int main() {
    int raw[256]; int64_t timestamps[256];
    for(int i=0;i<256;++i) { raw[i]=2000+static_cast<int>(100*sin(i*0.05)); timestamps[i]=i*4000; }
    assert(signal_block_reason(raw,timestamps)==nullptr);
    raw[10]=0; assert(strcmp(signal_block_reason(raw,timestamps),"ADC_SATURATION")==0);
    raw[10]=4095; assert(strcmp(signal_block_reason(raw,timestamps),"ADC_SATURATION")==0);
    for(int i=0;i<256;++i) raw[i]=2000;
    assert(strcmp(signal_block_reason(raw,timestamps),"FLAT_OR_TOO_SMALL")==0);
    for(int i=0;i<256;++i) raw[i]=i%2?2100:1900;
    assert(strcmp(signal_block_reason(raw,timestamps),"HIGH_FREQUENCY_NOISE")==0);
    timestamps[100]=timestamps[99];
    assert(strcmp(signal_block_reason(raw,timestamps),"TIMING_DISCONTINUITY")==0);
    for(int polarity : {-1,1}) {
        BeatDetector detector; float beat[256]; bool found=false;
        for(int i=0;i<800;++i) {
            const char* issue=nullptr;
            if(detector.push(i==600?2000+polarity*500:2000,i*4000,beat,issue)) {
                assert(i==727); assert(beat[128]==2000+polarity*500);
                assert(beat[127]==2000 && beat[129]==2000); found=true;
            }
            assert(issue==nullptr);
        }
        assert(found);
    }
    printf("PASS: rails/flat/noise/timestamp-gap guards; 128-before/128-from-center indexing, both detector polarities. Not ECG/clinical validation.\n");
}
