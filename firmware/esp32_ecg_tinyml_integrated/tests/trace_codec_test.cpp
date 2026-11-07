#include "trace_codec.h"
#include <cassert>
#include <cstring>
#include <cstdio>
int main() {
    uint8_t input[256]; for(int i=0;i<256;++i) input[i]=static_cast<uint8_t>(i);
    const char* digits="0123456789abcdef";
    for(int start=0;start<256;start+=16) {
        char output[34]; memset(output,'!',sizeof(output));
        assert(ecg_debug::encode_hex(input+start,16,output,33));
        assert(strlen(output)==32 && output[33]=='!');
        for(int i=0;i<16;++i) {
            assert(output[2*i]==digits[input[start+i]>>4]);
            assert(output[2*i+1]==digits[input[start+i]&15]);
        }
    }
    for(size_t n=1;n<=16;++n) {
        char output[33];
        assert(ecg_debug::encode_hex(input,n,output,2*n+1));
        assert(strlen(output)==2*n);
        assert(!ecg_debug::encode_hex(input,n,output,2*n));
    }
    assert(!ecg_debug::encode_hex(input,1,nullptr,3));
    assert(!ecg_debug::encode_hex(nullptr,1,nullptr,0));
    puts("PASS: actual firmware hex encoder, all256 byte values, chunk sizes1..16, terminator/bounds checks.");
}
