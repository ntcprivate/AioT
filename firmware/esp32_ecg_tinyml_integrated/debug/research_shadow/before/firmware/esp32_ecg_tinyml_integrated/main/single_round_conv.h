#pragma once
#include "tensorflow/lite/micro/micro_common.h"
namespace tflite { namespace micro {
TFLMRegistration Register_EcgConvSingleRound();
} }
void ecg_conv_diagnostic_enable(bool enabled);
void ecg_conv_diagnostic_print();
