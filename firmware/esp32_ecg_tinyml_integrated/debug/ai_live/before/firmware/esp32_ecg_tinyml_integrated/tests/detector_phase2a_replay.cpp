// Host diagnostic only; invokes unchanged QRS rule and validates every returned window.
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
struct Trace {float baseline,magnitude,envelope,threshold;int32_t age,last_global,pending_global;uint32_t flags;};
static_assert(sizeof(Trace)==32,"Python trace layout");
void stats(const char* tag,const BeatDetector& detector) {
    const auto s=detector.stats();const auto w=s.windows;
    printf("stats,%s,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%u,%u\n",tag,
        static_cast<unsigned long long>(s.samples),static_cast<unsigned long long>(s.candidates),
        static_cast<unsigned long long>(s.warmup_samples),static_cast<unsigned long long>(s.no_peak_resets),
        static_cast<unsigned long long>(s.external_resets),static_cast<unsigned long long>(w.enqueued),
        static_cast<unsigned long long>(w.completed),static_cast<unsigned long long>(w.dropped_full),
        static_cast<unsigned long long>(w.dropped_reset),static_cast<unsigned long long>(w.duplicate),
        static_cast<unsigned long long>(w.out_of_order),static_cast<unsigned long long>(w.overwritten),w.high_water,detector.pending_count());
}
void validate(const BeatDetector& detector,const float* beat,const std::vector<int16_t>& raw) {
    const auto w=detector.last_window();const int64_t absolute=w.center_timestamp/4000;
    assert(w.end_sample-w.start_sample==255 && w.center_sample-w.start_sample==128);
    assert(w.center_timestamp%4000==0 && absolute>=128 && absolute+127<static_cast<int64_t>(raw.size()));
    for(int i=0;i<256;++i)assert(beat[i]==raw[absolute-128+i]);
}
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    std::ifstream file(argv[1],std::ios::binary);std::vector<char> bytes((std::istreambuf_iterator<char>(file)),{});
    if((!file && !file.eof()) || bytes.size()%2)return 3;
    std::vector<int16_t> raw(bytes.size()/2);memcpy(raw.data(),bytes.data(),bytes.size());
    FILE* output=fopen(argv[2],"wb");if(!output)return 4;
    BeatDetector detector,gated;float beat[256];unsigned good_blocks=0;bool allowed=false;
    int64_t previous_center=-1,previous_gated=-1;
    for(size_t i=0;i<raw.size();++i) {
        if(i%256==0) {
            if(i+256<=raw.size()) {
                int block[256];int64_t times[256];for(int j=0;j<256;++j){block[j]=raw[i+j];times[j]=(i+j)*4000;}
                const char* q=signal_block_reason(block,times);printf("quality,%lu,%s\n",static_cast<unsigned long>(i),q?q:"PASS");
                if(q){good_blocks=0;gated.reset();}else if(good_blocks<2)++good_blocks;
                allowed=!q && good_blocks>=2;
            }else allowed=false;
        }
        const auto age=detector.count_;float baseline=age==0?raw[i]:detector.baseline_;
        baseline+=0.01f*(raw[i]-baseline);const float magnitude=std::abs(raw[i]-baseline);
        const float envelope=detector.envelope_+0.01f*(magnitude-detector.envelope_);
        const float threshold=std::max(float(CONFIG_ECG_QRS_MIN_COUNTS),2.5f*envelope);
        const bool local=detector.prev_abs_>detector.before_abs_ && detector.prev_abs_>=magnitude;
        const bool above=detector.prev_abs_>threshold,warm=age>=500;
        const bool refractory=detector.last_center_<0 || static_cast<int64_t>(i)-1-detector.last_center_>=75;
        const bool overlap=local && above && warm && refractory && detector.pending_count()>0;
        Trace trace={baseline,magnitude,envelope,threshold,static_cast<int32_t>(age),
            static_cast<int32_t>(detector.last_center_),static_cast<int32_t>(detector.windows_.first_pending_center()),
            static_cast<uint32_t>(local|(above<<1)|(warm<<2)|(refractory<<3)|(overlap<<4))};
        const char* issue=nullptr;
        if(detector.push(raw[i],i*4000,beat,issue)) {
            assert(!issue);validate(detector,beat,raw);const auto w=detector.last_window();
            assert(w.center_sample>previous_center);previous_center=w.center_sample;
            trace.flags|=32;printf("peak,%lld\n",static_cast<long long>(w.center_timestamp/4000));
            printf("window,%lld,%lld,%lld,%lld,%lu\n",static_cast<long long>(w.center_sample),
                static_cast<long long>(w.center_timestamp),static_cast<long long>(w.start_sample),
                static_cast<long long>(w.end_sample),static_cast<unsigned long>(i));
        }
        if(issue){trace.flags|=64;printf("issue,%lu,%s\n",static_cast<unsigned long>(i),issue);}
        if(detector.count_!=0)assert(detector.baseline_==baseline && detector.envelope_==envelope);
        if(fwrite(&trace,sizeof(trace),1,output)!=1)return 5;
        issue=nullptr;
        if(allowed && gated.push(raw[i],i*4000,beat,issue)) {
            assert(!issue);validate(gated,beat,raw);const auto w=gated.last_window();
            assert(w.center_timestamp>previous_gated);previous_gated=w.center_timestamp;
            printf("gated_peak,%lld\n",static_cast<long long>(w.center_timestamp/4000));
        }
        if(issue)printf("gated_issue,%lu,%s\n",static_cast<unsigned long>(i),issue);
    }
    stats("candidate",detector);stats("gated",gated);
    printf("size,%u,%u\n",unsigned(sizeof(BeatDetector)),unsigned(sizeof(BeatWindowBuffer)));
    return fclose(output)==0?0:6;
}
