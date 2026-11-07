#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
#include <cstring>
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "test_data/ecg_test_metadata.h"
#if ECG_CONV_SINGLE_ROUNDING
#include "single_round_conv.h"
#include "single_round_fc.h"
#endif
int main(int argc,char** argv) {
    if(argc!=4 && argc!=5)return 2;
    const bool batch=argc==5 && strcmp(argv[4],"--batch")==0;
    const bool inspect=argc==5 && strcmp(argv[4],"--inspect")==0;
    if(argc==5 && !batch && !inspect)return 2;
    std::ifstream mf(argv[1],std::ios::binary),sf(argv[2],std::ios::binary);
    std::vector<uint8_t> model_data((std::istreambuf_iterator<char>(mf)),{}),samples((std::istreambuf_iterator<char>(sf)),{});
    if(model_data.size()!=kModelBytes || (batch?samples.size()%256!=0:inspect?samples.size()!=256:samples.size()!=kSampleCount*256))return 3;
    const auto* model=tflite::GetModel(model_data.data());
    tflite::MicroMutableOpResolver<7> resolver;
    auto conv=tflite::micro::Register_CONV_2D();
    auto fc=tflite::micro::Register_FULLY_CONNECTED();
#if ECG_CONV_SINGLE_ROUNDING
    conv=tflite::micro::Register_EcgConvSingleRound();
    fc=tflite::micro::Register_EcgFullyConnected();
#endif
    if(resolver.AddConv2D(conv)!=kTfLiteOk || resolver.AddExpandDims()!=kTfLiteOk || resolver.AddFullyConnected(fc)!=kTfLiteOk ||
       resolver.AddLogistic()!=kTfLiteOk || resolver.AddMaxPool2D()!=kTfLiteOk || resolver.AddMean()!=kTfLiteOk || resolver.AddReshape()!=kTfLiteOk)return 4;
    alignas(16) static uint8_t arena[128*1024];
    tflite::MicroInterpreter instance(model,resolver,arena,sizeof(arena),nullptr,nullptr,true);
    if(instance.AllocateTensors()!=kTfLiteOk)return 5;
    if(inspect) {
        memcpy(instance.input(0)->data.int8,samples.data(),256);
        if(instance.Invoke()!=kTfLiteOk)return 6;
        auto* graph=model->subgraphs()->Get(0);
        for(unsigned op=0;op<graph->operators()->size();++op) {
            auto* tensor=instance.GetTensor(graph->operators()->Get(op)->outputs()->Get(0));size_t bytes=1;
            if(!tensor || tensor->type!=kTfLiteInt8)return 7;
            for(int d=0;d<tensor->dims->size;++d)bytes*=tensor->dims->data[d];
            char path[1024];snprintf(path,sizeof(path),"%s/op%u.bin",argv[3],op);
            std::ofstream f(path,std::ios::binary);f.write(tensor->data.raw,bytes);
        }
        return 0;
    }
    if(batch) {
        std::ofstream output(argv[3],std::ios::binary);
        for(size_t i=0;i<samples.size()/256;++i) {
            memcpy(instance.input(0)->data.int8,samples.data()+i*256,256);
            if(instance.Invoke()!=kTfLiteOk)return 6;
            output.write(instance.output(0)->data.raw,1);
        }
        return output?0:8;
    }
    unsigned failed=0;
    for(unsigned i=0;i<kSampleCount;++i) {
        memcpy(instance.input(0)->data.int8,samples.data()+i*256,256);
        if(instance.Invoke()!=kTfLiteOk)return 6;
        int code=instance.output(0)->data.int8[0];
        bool stable=true;
        for(int repeat=1;repeat<33;++repeat) {
            memcpy(instance.input(0)->data.int8,samples.data()+i*256,256);
            if(instance.Invoke()!=kTfLiteOk)return 6;
            stable &= instance.output(0)->data.int8[0]==code;
        }
        bool exact=stable && code==kGolden[i].output && ((code-kOutputZero)*kOutputScale>=kThreshold)==static_cast<bool>(kGolden[i].predicted);failed+=!exact;
        printf("HOST_GOLDEN backend_single=%d conv_single=%d sample=%u code=%d reference=%d exact=%d repeats=33 stable=%d\n",TFLITE_SINGLE_ROUNDING,ECG_CONV_SINGLE_ROUNDING,i,code,kGolden[i].output,exact,stable);
        if(i==5) {
            auto* graph=model->subgraphs()->Get(0);
            for(unsigned op=0;op<graph->operators()->size();++op) {
                int index=graph->operators()->Get(op)->outputs()->Get(0);
                auto* tensor=instance.GetTensor(index);size_t bytes=1;
                if(!tensor || tensor->type!=kTfLiteInt8)return 7;
                for(int d=0;d<tensor->dims->size;++d)bytes*=tensor->dims->data[d];
                char name[512];snprintf(name,sizeof(name),"%s/op%u.bin",argv[3],op);
                std::ofstream f(name,std::ios::binary);f.write(tensor->data.raw,bytes);
            }
        }
    }
    printf("HOST_GOLDEN_DONE backend_single=%d conv_single=%d failed=%u\n",TFLITE_SINGLE_ROUNDING,ECG_CONV_SINGLE_ROUNDING,failed);
    return (TFLITE_SINGLE_ROUNDING || ECG_CONV_SINGLE_ROUNDING)?(failed?1:0):(failed==2?0:1);
}
