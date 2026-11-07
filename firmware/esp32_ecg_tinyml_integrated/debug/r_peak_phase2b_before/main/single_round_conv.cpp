// CPU builtin Conv uses single rounding for this model; keep the remainder of
// the TFLM backend unchanged. No sample-specific correction or model mutation.
#include "single_round_conv.h"
#include "single_round_math.h"
#include "tensorflow/lite/micro/kernels/conv.h"
#include "tensorflow/lite/micro/kernels/kernel_util.h"
#include "tensorflow/lite/micro/kernels/internal/common.h"
#include <cstdint>
#ifndef ECG_HOST_TEST
#include "trace_transport.h"
#endif

namespace {
bool diagnostic_enabled=false;
struct Diagnostic { bool valid=false; int index=0,input[5]={},weight[5]={},bias=0,acc=0,m=0,shift=0,single=0,stock=0,actual=0,input_zero=0,output_zero=0,minimum=0,maximum=0; };
Diagnostic diagnostic[3];
}
void ecg_conv_diagnostic_enable(bool enabled) {
    diagnostic_enabled=enabled;
    if(enabled) for(auto& record:diagnostic) record=Diagnostic{};
}
void ecg_conv_diagnostic_print() {
#ifndef ECG_HOST_TEST
    console_trace_start();
    for(const auto& d:diagnostic) {
        console_trace_line("ECG_CONV_ARITH valid=%d index=%d x=%d,%d,%d,%d,%d w=%d,%d,%d,%d,%d bias=%d acc=%d multiplier=%d shift=%d stock_double=%d conv_single=%d input_zero=%d output_zero=%d clamp=%d,%d actual=%d",
            d.valid,d.index,d.input[0],d.input[1],d.input[2],d.input[3],d.input[4],d.weight[0],d.weight[1],d.weight[2],d.weight[3],d.weight[4],d.bias,d.acc,d.m,d.shift,d.stock,d.single,d.input_zero,d.output_zero,d.minimum,d.maximum,d.actual);
    }
    console_trace_stop();
#endif
}

// Reuse the actual vendor reference convolution loop. Give the specialized
// inline functions unique names to avoid ODR collisions with the stock kernel.
// common.h is already included: no global declarations are renamed.
#define MultiplyByQuantizedMultiplier EcgSingleRoundMultiplier
#define ConvPerChannel EcgConvPerChannelSingle
#include "tensorflow/lite/micro/kernels/internal/reference/integer_ops/conv.h"
#undef ConvPerChannel
#undef MultiplyByQuantizedMultiplier

namespace tflite { namespace micro {
namespace {
TfLiteStatus EvalEcgConv(TfLiteContext* context,TfLiteNode* node) {
    const auto* input=GetEvalInput(context,node,kConvInputTensor);
    const auto* filter=GetEvalInput(context,node,kConvWeightsTensor);
    const auto* bias=GetEvalInput(context,node,kConvBiasTensor);
    auto* output=GetEvalOutput(context,node,kConvOutputTensor);
    if(!input || !filter || !bias || !output || !node->user_data || !node->builtin_data ||
       input->type!=kTfLiteInt8 || filter->type!=kTfLiteInt8 || bias->type!=kTfLiteInt32 || output->type!=kTfLiteInt8)
        return kTfLiteError;
    const auto& data=*static_cast<const OpDataConv*>(node->user_data);
    const auto& params=*static_cast<const TfLiteConvParams*>(node->builtin_data);
    // The checked model uses symmetric INT8 filters; fail instead of pretending
    // to support another quantization contract.
    if(data.filter_zero_point!=0 || input->dims->size!=4 || filter->dims->size!=4 || output->dims->size!=4)
        return kTfLiteError;
    reference_integer_ops::EcgConvPerChannelSingle(ConvParamsQuantized(params,data),
        data.per_channel_output_multiplier,data.per_channel_output_shift,
        GetTensorShape(input),GetTensorData<int8_t>(input),GetTensorShape(filter),GetTensorData<int8_t>(filter),
        GetTensorShape(bias),GetTensorData<int32_t>(bias),GetTensorShape(output),GetTensorData<int8_t>(output));
    if(diagnostic_enabled && input->dims->data[1]==1 && input->dims->data[2]==256 && input->dims->data[3]==1 &&
       filter->dims->data[0]==8 && filter->dims->data[1]==1 && filter->dims->data[2]==5 && filter->dims->data[3]==1) {
        // Diagnostics only. These positions never influence tensor output or class.
        const int positions[]={292,820,1455};
        for(int j=0;j<3;++j) {
            auto& d=diagnostic[j];d.index=positions[j];int time=d.index/8,channel=d.index%8;
            d.bias=GetTensorData<int32_t>(bias)[channel];d.acc=d.bias;
            for(int k=0;k<5;++k) {
                d.input[k]=GetTensorData<int8_t>(input)[time+k];
                d.weight[k]=GetTensorData<int8_t>(filter)[channel*5+k];
                d.acc+=(d.input[k]-data.input_zero_point)*d.weight[k];
            }
            d.m=data.per_channel_output_multiplier[channel];d.shift=data.per_channel_output_shift[channel];
            d.single=EcgSingleRoundMultiplier(static_cast<int32_t>(d.acc),static_cast<int32_t>(d.m),d.shift);
            d.stock=MultiplyByQuantizedMultiplier(static_cast<int32_t>(d.acc),static_cast<int32_t>(d.m),d.shift);
            d.actual=GetTensorData<int8_t>(output)[d.index];d.input_zero=data.input_zero_point;d.output_zero=data.output_zero_point;
            d.minimum=data.output_activation_min;d.maximum=data.output_activation_max;d.valid=true;
        }
    }
    return kTfLiteOk;
}
}
TFLMRegistration Register_EcgConvSingleRound() {
    return RegisterOp(ConvInit,ConvPrepare,EvalEcgConv);
}
} }
