#include "sdkconfig.h"
#if CONFIG_ECG_AI_TEST_ONLY
#if CONFIG_ECG_AI_LIVE || CONFIG_ECG_GOLDEN_ALERT_DEMO
#error "Reference TEST_ONLY cannot enable live AI or prediction alerts"
#endif
#include "ai_test_only.h"
#include "model.h"
#include "preprocessing.h"
#include "telemetry.h"
#include "trace_transport.h"
#include "system_state.h"
#include "test_data/ecg_test_metadata.h"
#include "test_only/ai_test_metadata.h"
#include "esp_app_desc.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
extern const uint8_t raw_start[] asm("_binary_ai_test_raw_bin_start");
extern const uint8_t raw_end[] asm("_binary_ai_test_raw_bin_end");
extern const uint8_t extended_start[] asm("_binary_ai_test_extended_int8_bin_start");
extern const uint8_t extended_end[] asm("_binary_ai_test_extended_int8_bin_end");
extern const uint8_t golden_start[] asm("_binary_ecg_test_samples_int8_bin_start");
namespace {
#if CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST
constexpr int kSynthetic=1;
#else
constexpr int kSynthetic=0;
#endif
static_assert(kAiTestCount==20 && kSampleCount==12 && sizeof(float)==4,"Reviewed fixtures only");
uint32_t inference[kAiTestCount*30]={},preprocessing[kAiTestCount*30]={};
int observed[kAiTestCount]={};
bool exact[kAiTestCount]={},prep_exact[kAiTestCount]={},started=false;
TelemetryTestHealth initial={};int64_t begin_us=0;
bool hash(const uint8_t* data,size_t length,const char* expected) {
    uint8_t digest[32];char hex[65];constexpr char digits[]="0123456789abcdef";
    if(mbedtls_sha256(data,length,digest,0)!=0)return false;
    for(int i=0;i<32;++i){hex[2*i]=digits[digest[i]>>4];hex[2*i+1]=digits[digest[i]&15];}hex[64]=0;
    return strcmp(hex,expected)==0;
}
struct Stats {uint32_t minimum,maximum,p95;double mean;};
Stats statistics(const uint32_t* values,unsigned n) {
    uint32_t sorted[kAiTestCount*30];uint64_t sum=0;
    for(unsigned i=0;i<n;++i){sorted[i]=values[i];sum+=values[i];}
    std::sort(sorted,sorted+n);return {sorted[0],sorted[n-1],sorted[(95*n+99)/100-1],double(sum)/n};
}
const int8_t* expected_input(unsigned i) {
    return reinterpret_cast<const int8_t*>(i<12?golden_start+i*256:extended_start+(i-12)*256);
}
}
bool ai_test_only_begin() {
    const int64_t deadline=esp_timer_get_time()+5000000;
    while(telemetry_test_health().attempts<512 && esp_timer_get_time()<deadline)vTaskDelay(1);
    const bool valid=raw_end-raw_start==kAiTestCount*256*4 && extended_end-extended_start==8*256 &&
        hash(raw_start,raw_end-raw_start,kAiTestRawSha) && hash(extended_start,extended_end-extended_start,kAiTestExtendedSha);
    initial=telemetry_test_health();started=valid && initial.attempts>=512;begin_us=esp_timer_get_time();
    for(unsigned i=0;i<kAiTestCount;++i)exact[i]=prep_exact[i]=true;
    char elf_sha[65];constexpr char digits[]="0123456789abcdef";const auto* app=esp_app_get_description();
    for(unsigned i=0;i<32;++i){elf_sha[2*i]=digits[app->app_elf_sha256[i]>>4];elf_sha[2*i+1]=digits[app->app_elf_sha256[i]&15];}elf_sha[64]=0;
    console_lock();printf("ECG_AI_TEST_BEGIN source=REFERENCE_TEST_ONLY not_live=1 cases=20 golden=12 extended=8 repeats=30 warmups=3 synthetic=%d live_inference=0 assets_ok=%d adc_started=%d app_elf_sha=%s idf=%s t_us=%lld\n",
        kSynthetic,valid,initial.attempts>=512,elf_sha,app->idf_ver,static_cast<long long>(begin_us));console_unlock();
    return started;
}
void ai_test_only_note_golden(unsigned sample,unsigned run,int code,int64_t latency,bool ok) {
    if(sample>=12 || run>=30)return;
    inference[sample*30+run]=static_cast<uint32_t>(latency);observed[sample]=code;
    exact[sample] &= ok && code==kAiTestCases[sample].code;
}
void ai_test_only_note_golden_result(unsigned sample,bool passed) {if(sample<12)exact[sample] &= passed;}
bool ai_test_only_finish(bool golden_passed) {
    if(!started){console_lock();printf("ECG_AI_TEST_DONE source=REFERENCE_TEST_ONLY not_live=1 status=FAILED reason=TEST_BEGIN_FAILED live_inference=0\n");console_unlock();return false;}
    float raw[256];int8_t quantized[256];unsigned failed=0,truth_errors=0,known_labels=0;
    for(unsigned i=0;i<kAiTestCount;++i) {
        memcpy(raw,raw_start+i*256*4,sizeof(raw));
        for(unsigned run=0;run<33;++run) {
            unsigned clipped=0;const int64_t start=esp_timer_get_time();
            const bool ok=ecg_preprocessing::quantize(raw,quantized,kInputScale,kInputZero,clipped);
            const auto elapsed=esp_timer_get_time()-start;
            if(run>=3)preprocessing[i*30+run-3]=static_cast<uint32_t>(elapsed);
            prep_exact[i] &= ok && clipped==0 && memcmp(quantized,expected_input(i),256)==0;
        }
        int code=observed[i];float score=(code-kOutputZero)*kOutputScale;
        if(i>=12)for(unsigned run=0;run<33;++run) {
            int64_t latency=0;const bool ok=model_invoke_quantized(quantized,score,code,latency);
            exact[i] &= ok && code==kAiTestCases[i].code;
            if(run>=3)inference[i*30+run-3]=static_cast<uint32_t>(latency);
            vTaskDelay(1); // Existing golden scheduling pattern; never inside timing.
        }
        const auto inf=statistics(inference+i*30,30),prep=statistics(preprocessing+i*30,30);
        const bool pass=exact[i] && prep_exact[i];failed+=!pass;
        const int predicted=score>=kThreshold,truth_ok=kAiTestCases[i].label<0?-1:predicted==kAiTestCases[i].label;
        if(kAiTestCases[i].label>=0){++known_labels;truth_errors+=!truth_ok;}
        console_lock();printf("ECG_AI_TEST_CASE source=REFERENCE_TEST_ONLY not_live=1 case=%u id=%s record=%s true_label=%c reference_code=%d code=%d p_pvc=%.9f predicted=%s reference_predicted=%s truth_match=%d preprocessing_exact=%d repeats=30 stable_exact=%d inf_mean_us=%.3f inf_p95_us=%lu inf_max_us=%lu prep_mean_us=%.3f prep_p95_us=%lu prep_max_us=%lu status=%s\n",
            i,kAiTestCases[i].id,kAiTestCases[i].record,kAiTestCases[i].symbol,kAiTestCases[i].code,code,score,predicted?"PVC":"NORMAL",
            ((kAiTestCases[i].code-kOutputZero)*kOutputScale)>=kThreshold?"PVC":"NORMAL",truth_ok,prep_exact[i],exact[i],inf.mean,
            static_cast<unsigned long>(inf.p95),static_cast<unsigned long>(inf.maximum),prep.mean,static_cast<unsigned long>(prep.p95),static_cast<unsigned long>(prep.maximum),pass?"PASS":"FAIL");console_unlock();
        // Reporting the first 12 cases back-to-back can starve the lower-priority
        // telemetry writer and overflow its unchanged six-packet FIFO. Pace only
        // TEST_ONLY reports, outside all measured preprocessing/Invoke intervals.
        vTaskDelay(pdMS_TO_TICKS(300));
    }
    vTaskDelay(pdMS_TO_TICKS(1250)); // Allow last health buffer/TX to drain while ADC continues.
    const auto end=telemetry_test_health();uint32_t allocated=0,used=0;const bool memory=model_memory_usage(allocated,used);
    const auto inf=statistics(inference,kAiTestCount*30),prep=statistics(preprocessing,kAiTestCount*30);
    const bool stress=end.attempts>initial.attempts && end.drops==initial.drops && end.adc_errors==initial.adc_errors && end.missed==initial.missed &&
        end.snapshot_errors==initial.snapshot_errors && end.write_errors==initial.write_errors &&
        end.format_errors==initial.format_errors && end.uart_errors==initial.uart_errors && end.timeouts==initial.timeouts &&
        end.acquisition_hz>=249 && end.acquisition_hz<=251;
    console_lock();
    printf("ECG_AI_TEST_PERF source=REFERENCE_TEST_ONLY not_live=1 measured=600 inf_mean_us=%.3f inf_p95_us=%lu inf_max_us=%lu prep_mean_us=%.3f prep_p95_us=%lu prep_max_us=%lu arena_allocated=%lu arena_used=%lu heap_internal_free=%u heap_internal_min_boot=%u heap_internal_largest=%u stack_free_bytes=%u memory_ok=%d\n",
        inf.mean,static_cast<unsigned long>(inf.p95),static_cast<unsigned long>(inf.maximum),prep.mean,static_cast<unsigned long>(prep.p95),static_cast<unsigned long>(prep.maximum),
        static_cast<unsigned long>(allocated),static_cast<unsigned long>(used),static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
        static_cast<unsigned>(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),static_cast<unsigned>(heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)),memory);
    printf("ECG_AI_TEST_STRESS source=REFERENCE_TEST_ONLY not_live=1 adc_attempts_delta=%lu acq_hz=%.6f adc_errors_delta=%lu missed_delta=%lu late_delta=%lu queue_drops_delta=%lu snapshot_errors_delta=%lu uart_errors_delta=%lu format_errors_delta=%lu uart_timeouts_delta=%lu duration_us=%lld status=%s\n",
        static_cast<unsigned long>(end.attempts-initial.attempts),end.acquisition_hz,static_cast<unsigned long>(end.adc_errors-initial.adc_errors),static_cast<unsigned long>(end.missed-initial.missed),static_cast<unsigned long>(end.late-initial.late),
        static_cast<unsigned long>(end.drops-initial.drops),static_cast<unsigned long>(end.snapshot_errors-initial.snapshot_errors),static_cast<unsigned long>(end.write_errors-initial.write_errors),static_cast<unsigned long>(end.format_errors-initial.format_errors),static_cast<unsigned long>(end.timeouts-initial.timeouts),static_cast<long long>(esp_timer_get_time()-begin_us),stress?"PASS":"FAIL");
    printf("ECG_AI_TEST_DONE source=REFERENCE_TEST_ONLY not_live=1 cases=20 failed=%u golden_passed=%d known_truth_cases=%u truth_misclassified=%u exact_status=%s stress_status=%s status=%s live_inference=0\n",
        failed,golden_passed,known_labels,truth_errors,failed==0 && golden_passed?"PASS":"FAIL",stress?"PASS":"FAIL",failed==0 && golden_passed && stress && memory?"PASS":"FAIL");
    console_unlock();return failed==0 && golden_passed && stress && memory;
}
#endif
