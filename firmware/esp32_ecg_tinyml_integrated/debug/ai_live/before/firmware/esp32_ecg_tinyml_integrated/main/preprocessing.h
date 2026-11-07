#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
namespace ecg_preprocessing {
inline int round_even(double x) {
    double base=std::floor(x),fraction=x-base;
    if(fraction>0.5 || (fraction==0.5 && std::fmod(base,2.0)!=0))++base;
    return static_cast<int>(base);
}
// Original firmware preprocessing, factored verbatim for host parity tests.
inline bool quantize(const float* beat,int8_t* output,float scale,int zero,unsigned& clipped) {
    if(!beat || !output || !std::isfinite(scale) || scale<=0)return false;
    double mean=0,variance=0;
    for(int i=0;i<256;++i) {if(!std::isfinite(beat[i]))return false;mean+=beat[i];}
    mean/=256;
    for(int i=0;i<256;++i)variance+=(beat[i]-mean)*(beat[i]-mean);
    const double stddev=std::sqrt(variance/256);
    if(stddev<1e-8)return false;
    clipped=0;
    for(int i=0;i<256;++i) {
        const float normalized=static_cast<float>((beat[i]-mean)/std::max(stddev,1e-8));
        const int q=round_even(static_cast<double>(normalized)/scale)+zero;
        if(q<-128 || q>127)++clipped;
        output[i]=static_cast<int8_t>(std::max(-128,std::min(127,q)));
    }
    return true;
}
}
