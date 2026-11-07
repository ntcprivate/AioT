// Diagnostic-only host harness. Calls the unchanged production push(), never firmware.
// Private access exposes decision evidence; no replacement detector is used for scoring.
#define private public
#include "signal.h"
#undef private
#include "sdkconfig.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>

struct Trace {
    float baseline, magnitude, envelope, threshold;
    int32_t age, last_global, pending_global;
    uint32_t flags;
};
static_assert(sizeof(Trace)==32,"Python dtype must match host diagnostic layout");
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    std::ifstream file(argv[1],std::ios::binary);
    std::vector<char> bytes((std::istreambuf_iterator<char>(file)),{});
    if((!file && !file.eof()) || bytes.size()%2)return 3;
    FILE* trace=std::fopen(argv[2],"wb");if(!trace)return 4;
    BeatDetector detector,gated;float beat[256];unsigned good_blocks=0;bool block_allowed=false;
    for(size_t i=0;i<bytes.size()/2;++i) {
        int16_t raw;std::memcpy(&raw,bytes.data()+2*i,2);const char* issue=nullptr;
        if(i%256==0) {
            if(i+256<=bytes.size()/2) {
                int block[256];int64_t times[256];
                for(size_t j=0;j<256;++j) {int16_t x;std::memcpy(&x,bytes.data()+2*(i+j),2);block[j]=x;times[j]=(i+j)*4000;}
                const char* q=signal_block_reason(block,times);
                std::printf("quality,%lu,%s\n",static_cast<unsigned long>(i),q?q:"PASS");
                if(q) {good_blocks=0;gated.reset();}else if(good_blocks<2)++good_blocks;
                block_allowed=!q && good_blocks>=2;
            }else block_allowed=false;
        }
        const int64_t age=detector.count_,offset=static_cast<int64_t>(i)-age;
        float baseline=age==0?raw:detector.baseline_;
        baseline+=0.01f*(raw-baseline);
        const float magnitude=std::abs(raw-baseline);
        const float envelope=detector.envelope_+0.01f*(magnitude-detector.envelope_);
        const float threshold=std::max(static_cast<float>(CONFIG_ECG_QRS_MIN_COUNTS),2.5f*envelope);
        const bool local=detector.prev_abs_>detector.before_abs_ && detector.prev_abs_>=magnitude;
        const bool above=detector.prev_abs_>threshold;
        const bool warm=age>=500;
        const bool refractory=detector.last_center_<0 || age-1-detector.last_center_>=75;
        const bool conflict=local && above && warm && refractory && detector.pending_>=0;
        Trace row={baseline,magnitude,envelope,threshold,static_cast<int32_t>(age),
            detector.last_center_<0?-1:static_cast<int32_t>(offset+detector.last_center_),
            detector.pending_<0?-1:static_cast<int32_t>(offset+detector.pending_),
            static_cast<uint32_t>(local | (above<<1) | (warm<<2) | (refractory<<3) | (conflict<<4))};
        const bool complete=detector.push(raw,static_cast<int64_t>(i)*4000,beat,issue);
        if(complete) {row.flags|=32;std::printf("peak,%lu\n",static_cast<unsigned long>(i-127));}
        if(issue) {row.flags|=64;std::printf("issue,%lu,%s\n",static_cast<unsigned long>(i),issue);}
        if(detector.count_!=0) {
            assert(detector.baseline_==baseline && detector.envelope_==envelope);
        }
        if(std::fwrite(&row,sizeof(row),1,trace)!=1)return 5;
        issue=nullptr;
        if(block_allowed && gated.push(raw,static_cast<int64_t>(i)*4000,beat,issue))std::printf("gated_peak,%lu\n",static_cast<unsigned long>(i-127));
        if(issue)std::printf("gated_issue,%lu,%s\n",static_cast<unsigned long>(i),issue);
    }
    return std::fclose(trace)==0?0:6;
}
