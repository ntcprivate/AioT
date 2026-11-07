// Extended labeled-window parity found double rounding at per-channel FC.
// Keep per-tensor FC and every other backend operator unchanged.
#include "single_round_fc.h"
#include "single_round_math.h"
#include "tensorflow/lite/micro/kernels/fully_connected.h"
#include "tensorflow/lite/micro/kernels/kernel_util.h"
#include "tensorflow/lite/micro/kernels/internal/common.h"
#define MultiplyByQuantizedMultiplier EcgSingleRoundMultiplier
#define FullyConnectedPerChannel EcgFullyConnectedPerChannelSingle
#define FullyConnected EcgFullyConnectedSingle
#include "tensorflow/lite/micro/kernels/internal/reference/integer_ops/fully_connected.h"
#undef FullyConnected
#undef FullyConnectedPerChannel
#undef MultiplyByQuantizedMultiplier
namespace tflite { namespace micro {
namespace {
TfLiteStatus (*stock_invoke)(TfLiteContext*,TfLiteNode*)=nullptr;
TfLiteStatus Eval(TfLiteContext* context,TfLiteNode* node) {
    if(!node || !node->user_data || !stock_invoke)return kTfLiteError;
    const auto& data=*static_cast<const OpDataFullyConnected*>(node->user_data);
    if(!data.is_per_channel)return stock_invoke(context,node);
    const auto* input=GetEvalInput(context,node,kFullyConnectedInputTensor);
    const auto* filter=GetEvalInput(context,node,kFullyConnectedWeightsTensor);
    const auto* bias=GetEvalInput(context,node,kFullyConnectedBiasTensor);
    auto* output=GetEvalOutput(context,node,kFullyConnectedOutputTensor);
    if(!input || !filter || !bias || !output || input->type!=kTfLiteInt8 || filter->type!=kTfLiteInt8 ||
       bias->type!=kTfLiteInt32 || output->type!=kTfLiteInt8 || data.filter_zero_point!=0)return kTfLiteError;
    reference_integer_ops::EcgFullyConnectedPerChannelSingle(FullyConnectedParamsQuantized(data),
        data.per_channel_output_multiplier,reinterpret_cast<const int*>(data.per_channel_output_shift),
        GetTensorShape(input),GetTensorData<int8_t>(input),GetTensorShape(filter),GetTensorData<int8_t>(filter),
        GetTensorShape(bias),GetTensorData<int32_t>(bias),GetTensorShape(output),GetTensorData<int8_t>(output));
    return kTfLiteOk;
}
}
TFLMRegistration Register_EcgFullyConnected() {
    auto registration=Register_FULLY_CONNECTED();
    stock_invoke=registration.invoke;registration.invoke=Eval;
    return registration; // Original init/prepare, allocation and quantization.
}
} }
