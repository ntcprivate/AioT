// Read-only host probe of the unchanged detector at the remaining121 FN sites.
#define private public
#include "signal.h"
#undef private
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <vector>
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    std::ifstream data(argv[1],std::ios::binary),target_file(argv[2]);
    std::vector<int64_t> targets;int64_t target;while(target_file>>target)targets.push_back(target);
    BeatDetector d;float beat[256];int16_t raw;int64_t i=0;
    while(data.read(reinterpret_cast<char*>(&raw),sizeof(raw))) {
        float baseline=d.count_==0?raw:d.baseline_;baseline+=.025f*(raw-baseline);
        const float magnitude=std::abs(raw-baseline),envelope=d.envelope_+.01f*(magnitude-d.envelope_),threshold=std::max(30.f,2.5f*envelope);
        const bool local=d.prev_abs_>d.before_abs_ && d.prev_abs_>=magnitude;
        for(auto ref:targets)if(std::abs(i-1-ref)<=12 && local) {
            printf("%lld,%lld,%lld,%.9g,%.9g,%d,%d,%lld,%d\n",static_cast<long long>(ref),static_cast<long long>(i-1),static_cast<long long>(d.count_),d.prev_abs_,threshold,
                d.prev_abs_>threshold,d.last_center_<0 || i-1-d.last_center_>=75,static_cast<long long>(d.last_center_),d.candidate_active_);
        }
        const char* issue=nullptr;d.push(raw,i*4000LL,beat,issue);
        if(d.count_!=0)assert(d.baseline_==baseline && d.envelope_==envelope);
        ++i;
    }
    return data.eof()?0:3;
}
