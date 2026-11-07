#include "trace_transport.h"
#include "model.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "sdkconfig.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "test_data/ecg_test_metadata.h"
#include "single_round_conv.h"
#include "preprocessing.h"
#include "single_round_fc.h"
#if CONFIG_ECG_AI_TEST_ONLY
#include "ai_test_only.h"
#endif
#if !defined(TFLITE_SINGLE_ROUNDING) || TFLITE_SINGLE_ROUNDING != 0 || !ECG_CONV_SINGLE_ROUNDING
#error "Require Conv-only single rounding; stock backend stays double rounding"
#endif
#if CONFIG_ECG_OPERATOR_TRACE
#include "operator_trace.h"
#endif

extern const uint8_t model_start[] asm("_binary_ecg_cnn_int8_tflite_start");
extern const uint8_t model_end[] asm("_binary_ecg_cnn_int8_tflite_end");
extern const uint8_t samples_start[] asm("_binary_ecg_test_samples_int8_bin_start");
extern const uint8_t samples_end[] asm("_binary_ecg_test_samples_int8_bin_end");
namespace {
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;
#if CONFIG_ECG_OPERATOR_TRACE
ecg_debug::Trace operator_trace;
#endif
bool hash_ok(const uint8_t* data, size_t size, const char* expected) {
    uint8_t digest[32]; char hex[65];
    if (mbedtls_sha256(data, size, digest, 0) != 0) return false;
    for (int i=0; i<32; ++i) snprintf(hex + 2*i, 3, "%02x", digest[i]);
    return strcmp(hex, expected) == 0;
}
bool valid(TfLiteTensor* t, bool is_input) {
    if (!t || !t->dims || t->type != kTfLiteInt8 || !t->data.int8) return false;
    bool shape = is_input ? (t->dims->size==3 && t->dims->data[0]==1 && t->dims->data[1]==256 && t->dims->data[2]==1 && t->bytes==256) :
        (t->dims->size==2 && t->dims->data[0]==1 && t->dims->data[1]==1 && t->bytes==1);
    return shape && std::isfinite(t->params.scale) && t->params.scale>0 &&
        fabsf(t->params.scale-(is_input?kInputScale:kOutputScale))<1e-9f &&
        t->params.zero_point==(is_input?kInputZero:kOutputZero);
}
}
bool model_init() {
    console_lock();
    printf("ECG_KERNELS reference_active=%d esp_nn_effective=%d single_rounding=%d conv_single_rounding=%d fc_per_channel_single=1 fc_per_tensor_single=1 tflm=1.4.2 esp_nn_component=1.3.0\n",
           ECG_REFERENCE_KERNELS_ACTIVE, !ECG_REFERENCE_KERNELS_ACTIVE,TFLITE_SINGLE_ROUNDING,ECG_CONV_SINGLE_ROUNDING);
    console_unlock();
    if (static_cast<size_t>(model_end-model_start)!=kModelBytes ||
        !hash_ok(model_start,model_end-model_start,kModelSha)) return false;
    const auto* model=tflite::GetModel(model_start);
    if (model->version()!=TFLITE_SCHEMA_VERSION) return false;
    static tflite::MicroMutableOpResolver<7> resolver;
    if (resolver.AddConv2D(tflite::micro::Register_EcgConvSingleRound())!=kTfLiteOk || resolver.AddExpandDims()!=kTfLiteOk ||
        resolver.AddFullyConnected(tflite::micro::Register_EcgFullyConnected())!=kTfLiteOk || resolver.AddLogistic()!=kTfLiteOk ||
        resolver.AddMaxPool2D()!=kTfLiteOk || resolver.AddMean()!=kTfLiteOk || resolver.AddReshape()!=kTfLiteOk) return false;
    constexpr size_t size=CONFIG_ECG_ARENA_KIB*1024;
    auto* arena=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    if (!arena) return false;
#if CONFIG_ECG_OPERATOR_TRACE
    static ecg_debug::Interpreter instance(model,resolver,arena,size,nullptr,&operator_trace);
    operator_trace.attach(&instance,model);
#else
    static tflite::MicroInterpreter instance(model,resolver,arena,size);
#endif
    if (instance.AllocateTensors()!=kTfLiteOk || instance.inputs_size()!=1 || instance.outputs_size()!=1) return false;
    input=instance.input(0); output=instance.output(0);
    if (!valid(input,true) || !valid(output,false)) return false;
    interpreter=&instance;
    console_lock();
    printf("ECG_MODEL ready=1 arena_allocated=%u arena_used=%u input_scale=%.12g input_zero=%d output_scale=%.12g output_zero=%d threshold=%.9f class_1=PVC\n",
           static_cast<unsigned>(size), static_cast<unsigned>(instance.arena_used_bytes()), input->params.scale,
           static_cast<int>(input->params.zero_point),output->params.scale,static_cast<int>(output->params.zero_point),kThreshold);
    console_unlock();
    return true;
}
bool model_invoke_quantized(const int8_t* data,float& score,int& code,int64_t& latency) {
    if (!interpreter) return false;
    memcpy(input->data.int8,data,256);
    if(memcmp(input->data.int8,data,256)!=0) return false;
    const int64_t start=esp_timer_get_time();
    const auto status=interpreter->Invoke();
    latency=esp_timer_get_time()-start;
    if (status!=kTfLiteOk) return false;
    code=output->data.int8[0];
    score=(code-output->params.zero_point)*output->params.scale;
    return std::isfinite(score) && score>=0 && score<=1;
}
bool model_memory_usage(uint32_t& allocated,uint32_t& used) {
    if(!interpreter)return false;
    allocated=CONFIG_ECG_ARENA_KIB*1024;used=interpreter->arena_used_bytes();return true;
}
bool model_invoke_beat(const float* beat,float& score,int64_t& latency,unsigned& clipped) {
    if(!interpreter || !input) return false;
    int8_t quantized[256];
    if(!ecg_preprocessing::quantize(beat,quantized,input->params.scale,input->params.zero_point,clipped))return false;
    int code;
    return model_invoke_quantized(quantized,score,code,latency);
}
bool model_golden_test() {
    if (static_cast<size_t>(samples_end-samples_start)!=kSampleCount*256 ||
        !hash_ok(samples_start,samples_end-samples_start,kSamplesSha)) return false;
    console_lock();
    printf("ECG_ASSETS model_sha256=%s samples_sha256=%s verified=1\n",kModelSha,kSamplesSha);
    console_unlock();
    bool passed=true, predicted_n=false, predicted_v=false;
    unsigned failed=0;
    for(size_t i=0;i<kSampleCount;++i) {
        float score=0; int code=0; int64_t latency=0;
        const auto* data=reinterpret_cast<const int8_t*>(samples_start+i*256);
#if CONFIG_ECG_CONV_ARITHMETIC_LOG
        if(i==CONFIG_ECG_CONV_DIAGNOSTIC_SAMPLE) {
            float diagnostic_score=0;int diagnostic_code=0;int64_t diagnostic_time=0;
            ecg_conv_diagnostic_enable(true);
            const bool diagnostic_ok=model_invoke_quantized(data,diagnostic_score,diagnostic_code,diagnostic_time);
            ecg_conv_diagnostic_enable(false);
            if(diagnostic_ok) ecg_conv_diagnostic_print();
            else passed=false; // Do not hide a diagnostic Invoke failure.
        }
#endif
#if CONFIG_ECG_OPERATOR_TRACE
        if(i==CONFIG_ECG_TRACE_SAMPLE) {
            float traced_score=0; int traced_code=0; int64_t traced_time=0;
            operator_trace.begin(static_cast<unsigned>(i));
            const bool traced_ok=model_invoke_quantized(data,traced_score,traced_code,traced_time);
            operator_trace.finish_and_print(data,traced_ok,traced_code);
            // Diagnostic Invoke is extra; all original golden checks below remain.
        }
#endif
        // Match Step 8: three warm-ups, then 30 measured passes with input recopy.
        bool invoked=true, stable=true, warm_exact=true;
        int cold_code=0;
        for(int warm=0;warm<3;++warm) {
            bool ok=model_invoke_quantized(data,score,code,latency);
            invoked &= ok;
            warm_exact &= ok && code==kGolden[i].output;
            if(warm==0) cold_code=code;
            vTaskDelay(1); // Outside Invoke timing; identical scheduling pause to Step 8.
        }
        int first_code=0;
        for(int run=0;run<30;++run) {
            bool ok=model_invoke_quantized(data,score,code,latency);
            invoked &= ok;
            if(run==0) first_code=code;
            stable &= code==first_code;
            // Every pass must match. Warm-up is not permission to hide a mismatch.
            stable &= ok && code==kGolden[i].output;
#if CONFIG_ECG_AI_TEST_ONLY
            ai_test_only_note_golden(static_cast<unsigned>(i),static_cast<unsigned>(run),code,latency,ok);
#endif
            vTaskDelay(1);
        }
        bool exact=invoked && warm_exact && stable && code==kGolden[i].output && static_cast<int>(score>=kThreshold)==kGolden[i].predicted;
#if CONFIG_ECG_AI_TEST_ONLY
        ai_test_only_note_golden_result(static_cast<unsigned>(i),exact);
#endif
        passed &= exact;
        if(!exact) ++failed;
        predicted_n |= exact && kGolden[i].predicted==0;
        predicted_v |= exact && kGolden[i].predicted==1;
        console_lock();
        printf("ECG_GOLDEN source=STATIC_VALIDATION_TEST sample=%u true=%d reference_predicted=%d code=%d reference_code=%d p_pvc=%.9f inference_ms=%.3f cold_code=%d warm_exact=%d repeats=30 stable_exact=%d lsb=%d predicted=%d class_match=%d status=%s\n",
            static_cast<unsigned>(i), kGolden[i].label,kGolden[i].predicted,code,kGolden[i].output,score,latency/1000.0,
            cold_code, warm_exact, stable, code-kGolden[i].output,static_cast<int>(score>=kThreshold),
            static_cast<int>(score>=kThreshold)==kGolden[i].predicted,exact?"EXACT_MATCH":"FAILED");
        console_unlock();
    }
    // Golden includes previously misclassified samples: match reference, not truth!
    const bool success=passed && predicted_n && predicted_v;
    console_lock();
    printf("ECG_GOLDEN_DONE samples=%u failed=%u status=%s live_mode_unchanged=1\n",
           static_cast<unsigned>(kSampleCount),failed,success?"PASSED":"FAILED");
    console_unlock();
    return success;
}
