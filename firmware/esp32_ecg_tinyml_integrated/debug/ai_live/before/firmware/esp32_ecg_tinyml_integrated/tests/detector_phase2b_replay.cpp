// Host labeled replay only. Never enables firmware live classification.
#include "signal.h"
#include "preprocessing.h"
#include "test_data/ecg_test_metadata.h"
#include <cstdio>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
int main(int argc,char** argv) {
    if(argc!=4)return 2;
    std::ifstream file(argv[1],std::ios::binary);std::vector<char> bytes((std::istreambuf_iterator<char>(file)),{});
    if((!file && !file.eof()) || bytes.size()%2)return 3;
    std::vector<int16_t> raw(bytes.size()/2);memcpy(raw.data(),bytes.data(),bytes.size());
    FILE* output=fopen(argv[2],"wb");FILE* safe_output=fopen(argv[3],"wb");if(!output || !safe_output)return 4;
    BeatDetector detector,safe;float beat[256];bool allowed=false;unsigned good=0;int64_t last_center=-1,last_safe=-1;
    for(size_t i=0;i<raw.size();++i) {
        if(i%256==0) {
            if(i+256<=raw.size()) {
                int block[256];int64_t times[256];for(int j=0;j<256;++j){block[j]=raw[i+j];times[j]=(i+j)*4000;}
                const char* q=signal_block_reason(block,times);printf("quality,%lu,%s\n",static_cast<unsigned long>(i),q?q:"PASS");
                if(q){good=0;safe.reset();}else if(good<2)++good;
                allowed=!q && good>=2;
            }else allowed=false;
        }
        const char* issue=nullptr;
        if(detector.push(raw[i],i*4000LL,beat,issue)) {
            const auto w=detector.last_window();const int64_t c=w.center_timestamp/4000;
            assert(!issue && c>last_center);last_center=c;
            for(int j=0;j<256;++j)assert(beat[j]==raw[c-128+j]);
            assert(w.center_sample-w.start_sample==128 && w.end_sample-w.start_sample==255);
            if(fwrite(beat,sizeof(float),256,output)!=256)return 5;
            printf("peak,%lld,%lu\n",static_cast<long long>(c),static_cast<unsigned long>(i));
        }
        if(issue)printf("issue,%lu,%s\n",static_cast<unsigned long>(i),issue);
        issue=nullptr;
        if(allowed && safe.push(raw[i],i*4000LL,beat,issue)) {
            const auto w=safe.last_window();const int64_t c=w.center_timestamp/4000;assert(!issue && c>last_safe);last_safe=c;
            for(int j=0;j<256;++j)assert(beat[j]==raw[c-128+j]);
            int8_t quantized[256];unsigned clipped=0;
            const bool normalized=ecg_preprocessing::quantize(beat,quantized,kInputScale,kInputZero,clipped);
            if(!normalized || clipped) {
                printf("safe_abstain,%lld,%s\n",static_cast<long long>(c),normalized?"INPUT_QUANTIZATION_CLIPPING":"NORMALIZATION_FAILED");
                safe.reset();good=0;allowed=false;
            } else {
                if(fwrite(beat,sizeof(float),256,safe_output)!=256)return 5;
                printf("safe_peak,%lld,%lu\n",static_cast<long long>(c),static_cast<unsigned long>(i));
            }
        }
        if(issue){printf("safe_issue,%lu,%s\n",static_cast<unsigned long>(i),issue);safe.reset();good=0;allowed=false;}
    }
    const auto s=detector.stats();const auto w=s.windows;
    printf("stats,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%u,%u\n",
        static_cast<unsigned long long>(s.samples),static_cast<unsigned long long>(w.enqueued),
        static_cast<unsigned long long>(w.completed),static_cast<unsigned long long>(w.dropped_full),
        static_cast<unsigned long long>(w.dropped_reset),static_cast<unsigned long long>(w.duplicate),
        static_cast<unsigned long long>(w.out_of_order),static_cast<unsigned long long>(s.no_peak_resets),w.high_water,detector.pending_count());
    return fclose(output)==0 && fclose(safe_output)==0?0:6;
}
