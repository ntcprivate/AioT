// Same board/CPU/windows/repeats for FP32 vs INT8; no Serial input, ADC or labels.
#include <cstdio>
#include <cstring>
#include <cmath>
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "single_round_conv.h"
#include "single_round_fc.h"
#include "preprocessing.h"
#include "test_data/ecg_test_metadata.h"
extern const uint8_t raw_start[] asm("_binary_v4_raw_bin_start");
#if V4_BENCH_FLOAT
#include "fp32_identity.h"
extern const uint8_t model_start[] asm("_binary_ecg_cnn_v4_fp32_tflite_start");
extern const uint8_t model_end[] asm("_binary_ecg_cnn_v4_fp32_tflite_end");
#else
extern const uint8_t model_start[] asm("_binary_ecg_cnn_int8_tflite_start");
extern const uint8_t model_end[] asm("_binary_ecg_cnn_int8_tflite_end");
#endif
extern "C" void app_main(){
    const char* expected=kModelSha;
#if V4_BENCH_FLOAT
    expected=kFp32Sha;
#endif
    uint8_t digest[32];char hash[65];
    if(mbedtls_sha256(model_start,model_end-model_start,digest,0)){printf("V4_BENCH_FAILED reason=HASH_API\n");return;}
    for(unsigned i=0;i<32;++i){snprintf(hash+2*i,3,"%02x",digest[i]);}
    if(strcmp(hash,expected)){printf("V4_BENCH_FAILED reason=MODEL_HASH\n");return;}
    printf("V4_BENCH_IDENTITY sha256=%s\n",hash);
    printf("V4_BENCH_BEGIN backend=%s cpu_mhz=%d fixtures=22 warmup=3 measured=30 adc=0\n",V4_BENCH_FLOAT?"FP32":"INT8",CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);
    static tflite::MicroMutableOpResolver<7> resolver;
#if V4_BENCH_FLOAT
    if(resolver.AddConv2D()!=kTfLiteOk || resolver.AddFullyConnected()!=kTfLiteOk)return;
#else
    if(resolver.AddConv2D(tflite::micro::Register_EcgConvSingleRound())!=kTfLiteOk || resolver.AddFullyConnected(tflite::micro::Register_EcgFullyConnected())!=kTfLiteOk)return;
#endif
    if(resolver.AddExpandDims()!=kTfLiteOk || resolver.AddReshape()!=kTfLiteOk || resolver.AddMaxPool2D()!=kTfLiteOk || resolver.AddMean()!=kTfLiteOk || resolver.AddLogistic()!=kTfLiteOk)return;
    constexpr size_t arena_size=64*1024;
    auto* arena=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,arena_size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    if(!arena){printf("V4_BENCH_FAILED reason=ARENA\n");return;}
    static tflite::MicroInterpreter interpreter(tflite::GetModel(model_start),resolver,arena,arena_size);
    if(interpreter.AllocateTensors()!=kTfLiteOk){printf("V4_BENCH_FAILED reason=ALLOCATE_TENSORS\n");return;}
    auto* input=interpreter.input(0);auto* output=interpreter.output(0);
    if(input->bytes!=(V4_BENCH_FLOAT?1024:256) || input->type!=(V4_BENCH_FLOAT?kTfLiteFloat32:kTfLiteInt8) || output->type!=(V4_BENCH_FLOAT?kTfLiteFloat32:kTfLiteInt8)){printf("V4_BENCH_FAILED reason=IO\n");return;}
    static float raw[256],normalized[256];static int8_t q[256];bool exact=true;
    for(unsigned i=0;i<22;++i){
        memcpy(raw,raw_start+i*1024,1024);
        for(int run=-3;run<30;++run){
            int64_t t0=esp_timer_get_time();
            if(!ecg_preprocessing::normalize(raw,normalized))return;
            int64_t t1=esp_timer_get_time();unsigned clipped=0;
#if V4_BENCH_FLOAT
            memcpy(input->data.f,normalized,1024);
#else
            if(!ecg_preprocessing::quantize_normalized(normalized,q,kInputScale,kInputZero,clipped))return;
            memcpy(input->data.int8,q,256);
#endif
            int64_t t2=esp_timer_get_time();
            if(interpreter.Invoke()!=kTfLiteOk){printf("V4_BENCH_FAILED reason=INVOKE\n");return;}
            int64_t t3=esp_timer_get_time();
#if V4_BENCH_FLOAT
            const float score=output->data.f[0];const int code=0;
#else
            const int code=output->data.int8[0];const float score=(code+128)/256.f;exact &= code==kGolden[i].output;
#endif
            // Measurements finished before UART; same pause/output policy for both builds.
            printf("V4_BENCH_SAMPLE i=%u run=%d code=%d score=%.9f predicted=%d norm_us=%lld quant_copy_us=%lld invoke_us=%lld total_us=%lld clipped=%u\n",i,run,code,score,int(score>=kThreshold),(long long)(t1-t0),(long long)(t2-t1),(long long)(t3-t2),(long long)(t3-t0),clipped);
            vTaskDelay(1);
        }
    }
    printf("V4_BENCH_END int8_exact=%d arena_used=%u arena_allocated=%u heap_min=%u stack_free=%u status=MEASUREMENTS_ONLY\n",V4_BENCH_FLOAT?-1:int(exact),unsigned(interpreter.arena_used_bytes()),unsigned(arena_size),unsigned(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),unsigned(uxTaskGetStackHighWaterMark(nullptr)));
}
