// Executes the actual bundled TFLM ConvPerChannel and common.cc, not a rewrite.
#include <cstdio>
#include "conv_fixture.h"
#include "tensorflow/lite/micro/kernels/internal/reference/integer_ops/conv.h"
int main() {
    using namespace tflite::micro;
    int32_t in_dims[]={1,1,256,1},filter_dims[]={8,1,5,1},bias_dims[]={8},out_dims[]={1,1,252,8};
    RuntimeShape in(4,in_dims),filter(4,filter_dims),bias(1,bias_dims),out(4,out_dims);
    ConvParams p={};p.input_offset=kInputOffset;p.output_offset=kOutputOffset;
    p.stride_width=p.stride_height=p.dilation_width_factor=p.dilation_height_factor=1;
    p.quantized_activation_min=-128;p.quantized_activation_max=127;
    int8_t output[2016];
    reference_integer_ops::ConvPerChannel(p,kMultiplier,kShift,in,kInput,filter,kWeights,bias,kBias,out,output);
    unsigned mismatches=0;uint32_t hash=2166136261u;
    for(int i=0;i<2016;++i) { mismatches+=output[i]!=kExpected[i];hash=(hash^static_cast<uint8_t>(output[i]))*16777619u; }
    printf("TFLM_CONV single_rounding=%d bytes=2016 mismatches=%u fnv=%08x pos292=%d pos820=%d pos1455=%d\n",
        TFLITE_SINGLE_ROUNDING,mismatches,hash,output[292],output[820],output[1455]);
    if(TFLITE_SINGLE_ROUNDING) return mismatches==0 && hash==0xc1b69a54u?0:1;
    return mismatches==3 && hash==0x84bd53f7u?0:1;
}
