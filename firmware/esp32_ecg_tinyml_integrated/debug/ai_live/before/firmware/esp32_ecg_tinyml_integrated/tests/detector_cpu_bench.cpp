#include "signal.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
int main(int argc,char** argv) {
    const int period=argc>1?std::atoi(argv[1]):100;if(period<75)return 2;
    BeatDetector detector;float beat[256];unsigned completed=0,issues=0;
    constexpr int samples=1000000;
    const auto start=std::chrono::steady_clock::now();
    for(int i=0;i<samples;++i) {
        const char* issue=nullptr;
        if(detector.push(i>=600 && (i-600)%period==0?2548:2048,i*4000LL,beat,issue))++completed;
        issues+=issue!=nullptr;
    }
    const auto ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
    printf("{\"samples\":%d,\"rr_samples\":%d,\"host_ns_total\":%lld,\"host_ns_per_sample\":%.3f,\"windows\":%u,\"issues\":%u,\"sizeof_detector_host\":%u}\n",
        samples,period,static_cast<long long>(ns),double(ns)/samples,completed,issues,unsigned(sizeof(BeatDetector)));
}
