#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "single_round_conv.h"
#include "single_round_fc.h"
#include "preprocessing.h"
#include "fixtures.h"
extern const uint8_t model_start[] asm("_binary_v4_model_tflite_start");
extern const uint8_t model_end[] asm("_binary_v4_model_tflite_end");
extern const uint8_t inputs_start[] asm("_binary_v4_inputs_bin_start");
extern const uint8_t inputs_end[] asm("_binary_v4_inputs_bin_end");
extern const uint8_t raw_start[] asm("_binary_v4_raw_bin_start");
extern const uint8_t raw_end[] asm("_binary_v4_raw_bin_end");
bool hash_ok(const uint8_t* p,size_t n,const char* expected){
 uint8_t digest[32];char hex[65];if(mbedtls_sha256(p,n,digest,0)!=0)return false;
 for(int i=0;i<32;++i){snprintf(hex+2*i,3,"%02x",digest[i]);}
 return strcmp(hex,expected)==0;
}
void failure(const char* why){printf("V4_GOLDEN_RESULT status=FAILED reason=%s\n",why);fflush(stdout);}
extern "C" void app_main(){
 printf("V4_GOLDEN_BEGIN source=STATIC_FIXTURES adc_live=0 model=V4 reference_active=1 esp_nn_effective=0 threshold_code=98\n");
 if(size_t(model_end-model_start)!=8688 || !hash_ok(model_start,8688,kModelSha) ||
 size_t(inputs_end-inputs_start)!=kCount*256 || !hash_ok(inputs_start,kCount*256,kInputsSha) ||
 size_t(raw_end-raw_start)!=kCount*256*sizeof(float) || !hash_ok(raw_start,kCount*256*sizeof(float),kRawSha)){failure("ASSET_HASH");return;}
 const auto* model=tflite::GetModel(model_start);if(model->version()!=TFLITE_SCHEMA_VERSION){failure("SCHEMA");return;}
 static tflite::MicroMutableOpResolver<7> resolver;
 if(resolver.AddConv2D(tflite::micro::Register_EcgConvSingleRound())!=kTfLiteOk ||
 resolver.AddFullyConnected(tflite::micro::Register_EcgFullyConnected())!=kTfLiteOk ||
 resolver.AddExpandDims()!=kTfLiteOk || resolver.AddReshape()!=kTfLiteOk ||
 resolver.AddMaxPool2D()!=kTfLiteOk || resolver.AddMean()!=kTfLiteOk || resolver.AddLogistic()!=kTfLiteOk){failure("RESOLVER");return;}
 const size_t before=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
 constexpr size_t arena_size=64*1024;auto* arena=static_cast<uint8_t*>(heap_caps_aligned_alloc(16,arena_size,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
 if(!arena){failure("ARENA_ALLOCATION");return;}
 static tflite::MicroInterpreter interpreter(model,resolver,arena,arena_size);
 if(interpreter.AllocateTensors()!=kTfLiteOk || interpreter.inputs_size()!=1 || interpreter.outputs_size()!=1){failure("ALLOCATE_TENSORS");return;}
 auto* in=interpreter.input(0);auto* out=interpreter.output(0);
 if(!in || !out || in->type!=kTfLiteInt8 || out->type!=kTfLiteInt8 || in->bytes!=256 || out->bytes!=1 ||
 in->dims->size!=3 || in->dims->data[0]!=1 || in->dims->data[1]!=256 || in->dims->data[2]!=1 ||
 in->params.zero_point!=-8 || fabsf(in->params.scale-0.06217966973781586f)>1e-9f ||
 out->params.zero_point!=-128 || out->params.scale!=1.f/256){failure("IO_CONTRACT");return;}
 printf("V4_GOLDEN_MODEL sha256=%s arena_allocated=%u arena_used=%u internal_heap_before=%u internal_heap_after=%u\n",kModelSha,unsigned(arena_size),unsigned(interpreter.arena_used_bytes()),unsigned(before),unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)));
 static float raw[256];static int8_t q[256];unsigned exact=0,prep_exact=0;int maxdelta=0;int64_t total=0,min_us=INT64_MAX,max_us=0;
 for(unsigned i=0;i<kCount;++i){
  memcpy(raw,raw_start+i*256*sizeof(float),sizeof(raw));unsigned clipped=0;
  bool prep=ecg_preprocessing::quantize(raw,q,in->params.scale,in->params.zero_point,clipped) && memcmp(q,inputs_start+i*256,256)==0;
  prep_exact+=prep;memcpy(in->data.int8,inputs_start+i*256,256);int64_t start=esp_timer_get_time();auto ok=interpreter.Invoke();int64_t elapsed=esp_timer_get_time()-start;
  if(ok!=kTfLiteOk){failure("INVOKE");return;}
  int code=out->data.int8[0];int delta=abs(code-kReference[i]);exact+=delta==0;maxdelta=std::max(maxdelta,delta);total+=elapsed;min_us=std::min(min_us,elapsed);max_us=std::max(max_us,elapsed);
  printf("V4_GOLDEN_SAMPLE i=%u label=%d code=%d reference=%d probability=%.9f predicted=%d expected_predicted=%d delta=%d prep_exact=%d clipped=%u inference_us=%lld status=%s\n",i,kLabels[i],code,kReference[i],(code+128)/256.f,code>=98,kReference[i]>=98,delta,int(prep),clipped,(long long)elapsed,delta==0 && prep?"EXACT":"FAILED");
  vTaskDelay(1);
 }
 printf("V4_GOLDEN_MEMORY arena_used=%u arena_allocated=%u internal_heap_min=%u stack_high_water_bytes=%u\n",unsigned(interpreter.arena_used_bytes()),unsigned(arena_size),unsigned(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),unsigned(uxTaskGetStackHighWaterMark(nullptr)));
 printf("V4_GOLDEN_RESULT status=%s exact=%u total=%u prep_exact=%u max_code_delta=%d latency_mean_us=%lld latency_min_us=%lld latency_max_us=%lld model_sha256=%s\n",exact==kCount && prep_exact==kCount?"PASS":"FAILED",exact,kCount,prep_exact,maxdelta,(long long)(total/kCount),(long long)min_us,(long long)max_us,kModelSha);
 printf("V4_GOLDEN_END\n");fflush(stdout);
}
