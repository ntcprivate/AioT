#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
namespace ecg_wire {
constexpr size_t kBatch=32,kStride=7;
inline int synthetic(uint32_t index) {return 512+static_cast<int>((static_cast<uint64_t>(index)*17)%3072);}
inline uint32_t crc32(const uint8_t* p,size_t n) {
    uint32_t c=0xffffffffu;
    for(size_t i=0;i<n;++i) {c^=p[i];for(int b=0;b<8;++b)c=(c>>1)^(0xedb88320u & (0u-(c&1)));}
    return c^0xffffffffu;
}
inline void sample(uint8_t* p,uint32_t delta,int raw,uint8_t flags) {
    for(int i=0;i<4;++i)p[i]=static_cast<uint8_t>(delta>>(8*i));
    const uint16_t v=raw<0?65535:static_cast<uint16_t>(raw);
    p[4]=v&255;p[5]=v>>8;p[6]=flags;
}
inline int frame(const char* json,char* output,size_t capacity) {
    if(!json || !output || !capacity)return -1;
    const int n=snprintf(output,capacity,"\nECG1 %08lx %s\n",static_cast<unsigned long>(crc32(reinterpret_cast<const uint8_t*>(json),strlen(json))),json);
    return n>0 && static_cast<size_t>(n)<capacity?n:-1;
}
}
