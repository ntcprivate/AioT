// Test the exact adapter function against the bundled common.cc single-round
// branch across signed values/ties. Unused operator registration is GC-linked.
#include "../main/single_round_math.h"
#include "tensorflow/lite/micro/kernels/internal/common.h"
#include <cstdio>
int main() {
    using namespace tflite::micro;
    if(EcgSingleRoundMultiplier(1,1<<30,0)!=1 || EcgSingleRoundMultiplier(-1,1<<30,0)!=0) return 1;
    uint32_t state=42;
    for(int i=0;i<20000;++i) {
        state=1664525u*state+1013904223u;
        const int32_t x=static_cast<int32_t>(state%200001)-100000;
        const int32_t m=1073741824+static_cast<int32_t>((state>>3)%1073741824);
        const int shift=static_cast<int>(state%36)-31;
        if(EcgSingleRoundMultiplier(x,m,shift)!=MultiplyByQuantizedMultiplier(x,m,shift)) return 2;
    }
    puts("PASS: adapter equals actual TFLM single-round helper on20000 signed cases, right/left shifts and signed ties.");
}
