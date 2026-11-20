#pragma once
#include <cstddef>
#include <cstdint>
namespace ecg_debug {
inline bool encode_hex(const uint8_t* data,size_t count,char* output,size_t capacity) {
    if(!output || !capacity || (!data && count) || count>(capacity-1)/2) return false;
    constexpr char digits[]="0123456789abcdef";
    for(size_t i=0;i<count;++i) {
        output[2*i]=digits[data[i]>>4]; output[2*i+1]=digits[data[i]&15];
    }
    output[2*count]='\0';
    return true;
}
}
