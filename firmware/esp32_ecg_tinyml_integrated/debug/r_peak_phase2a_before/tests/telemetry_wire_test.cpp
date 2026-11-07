#include "telemetry_codec.h"
#include <cassert>
#include <cstdio>
#include <cstring>
int main(int argc,char** argv) {
    assert(ecg_wire::crc32(reinterpret_cast<const uint8_t*>("123456789"),9)==0xcbf43926u);
    for(uint32_t i=0;i<100000;++i)assert(ecg_wire::synthetic(i)>=0 && ecg_wire::synthetic(i)<=4095);
    char tiny[8];assert(ecg_wire::frame("{}",tiny,sizeof(tiny))==-1);
    if(argc==2) {
        FILE* output=fopen(argv[1],"wb");if(!output)return 2;
        constexpr char digits[]="0123456789abcdef";
        for(uint32_t batch=0;batch<500;++batch) {
            uint8_t bytes[32*7];char hex[449],json[900],frame[1000];
            for(uint32_t j=0;j<32;++j)ecg_wire::sample(bytes+7*j,j*4000,ecg_wire::synthetic(batch*32+j),0);
            for(unsigned i=0;i<sizeof(bytes);++i) {hex[2*i]=digits[bytes[i]>>4];hex[2*i+1]=digits[bytes[i]&15];}hex[448]=0;
            snprintf(json,sizeof(json),"{\"v\":2,\"type\":\"samples\",\"boot\":\"CPP_FIXTURE\",\"seq\":%lu,\"first\":%lu,\"t0\":%lu,\"fs\":250,\"n\":32,\"source\":\"SYNTHETIC_TEST\",\"pattern\":\"saw17-v1\",\"data\":\"%s\",\"dropped\":0}",
                static_cast<unsigned long>(batch),static_cast<unsigned long>(batch*32),static_cast<unsigned long>(batch*128000),hex);
            const int n=ecg_wire::frame(json,frame,sizeof(frame));assert(n>0);
            assert(fwrite(frame,1,n,output)==static_cast<size_t>(n));
        }
        assert(fclose(output)==0);
    }
    puts("PASS: actual firmware CRC32/frame encoder and deterministic synthetic pattern;500 production-layout batches emitted when path supplied.");
}
