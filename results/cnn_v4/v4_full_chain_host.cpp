#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "single_round_conv.h"
#include "single_round_fc.h"

int main(int argc, char** argv) {
    if (argc != 4) return 2;
    std::ifstream mf(argv[1], std::ios::binary), sf(argv[2], std::ios::binary);
    std::vector<uint8_t> model_data((std::istreambuf_iterator<char>(mf)), {});
    std::vector<uint8_t> samples((std::istreambuf_iterator<char>(sf)), {});
    if (model_data.empty() || samples.size() % 256 != 0) return 3;
    const auto* model = tflite::GetModel(model_data.data());
    tflite::MicroMutableOpResolver<7> resolver;
    if (resolver.AddConv2D(tflite::micro::Register_EcgConvSingleRound()) != kTfLiteOk ||
        resolver.AddExpandDims() != kTfLiteOk ||
        resolver.AddFullyConnected(tflite::micro::Register_EcgFullyConnected()) != kTfLiteOk ||
        resolver.AddLogistic() != kTfLiteOk || resolver.AddMaxPool2D() != kTfLiteOk ||
        resolver.AddMean() != kTfLiteOk || resolver.AddReshape() != kTfLiteOk) return 4;
    alignas(16) static uint8_t arena[128 * 1024];
    tflite::MicroInterpreter instance(model, resolver, arena, sizeof(arena), nullptr, nullptr, true);
    if (instance.AllocateTensors() != kTfLiteOk) return 5;
    std::ofstream output(argv[3], std::ios::binary);
    for (size_t i = 0; i < samples.size() / 256; ++i) {
        std::memcpy(instance.input(0)->data.int8, samples.data() + i * 256, 256);
        if (instance.Invoke() != kTfLiteOk) return 6;
        output.write(instance.output(0)->data.raw, 1);
    }
    return output ? 0 : 7;
}
