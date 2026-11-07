#include "trace_transport.h"
#include "pipeline.h"
#include "model.h"
#include "ai_test_only.h"
#include "signal.h"
#include "preprocessing.h"
#include "research_shadow.h"
#include "test_data/ecg_test_metadata.h"
#include "system_state.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#if CONFIG_ECG_AI_LIVE && (CONFIG_ECG_AI_TEST_ONLY || CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST)
#error "ADC AI LIVE, reference suite and synthetic sources are separate"
#endif

namespace {
using State=EcgState;
struct Status {
    State state=State::Waiting;
    const char* reason="COLLECTING";
    uint32_t generation=0, good=0, revision=1;
    int64_t last_sample=0;
    bool model_ready=false, demo=false, output_fault=false,system_fault=false;
    bool led=false,buzzer=false,self_test=false,quality_known=false;
    unsigned good_blocks=0;
    SignalMetrics metrics={};int64_t quality_time=0;
    State demo_state=State::Waiting;
#if CONFIG_ECG_AI_LIVE
    ecg_ai::View ai;
#endif
};
portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
Status status;
TaskHandle_t ai_task_handle=nullptr;
struct Block { uint32_t id,generation; int raw[256]; int64_t timestamps[256]; uint32_t hash; };
QueueHandle_t blocks=nullptr;
Block outgoing; // Sampling producer owns this; queue makes full value copies.
uint32_t hash_block(const Block& b) {
    uint32_t h=2166136261u;
    const auto* p=reinterpret_cast<const uint8_t*>(&b);
    for(size_t i=0;i<offsetof(Block,hash);++i) h=(h^p[i])*16777619u;
    return h;
}
void invalid_locked(const char* reason) {
    if(status.system_fault)return; // Hardware/model faults outrank signal recovery.
    if(status.state!=State::Invalid || strcmp(status.reason,reason)!=0) {
        ++status.generation; ++status.revision;
    }
#if CONFIG_ECG_AI_LIVE
    ecg_ai::clear(status.ai,reason,true);
#endif
    status.state=State::Invalid; status.reason=reason;
    status.good=0; status.good_blocks=0; 
}
void fault(const char* reason) {
    portENTER_CRITICAL(&lock);
#if CONFIG_ECG_AI_LIVE
    ecg_ai::clear(status.ai,reason,true);
#endif
    status.system_fault=true;status.state=State::Fault;status.reason=reason;
    status.good=status.good_blocks=0;++status.revision;++status.generation;
    portEXIT_CRITICAL(&lock);
}
void invalid(const char* reason) {
    portENTER_CRITICAL(&lock); invalid_locked(reason); portEXIT_CRITICAL(&lock);
}
Status snapshot() {
    portENTER_CRITICAL(&lock); Status copy=status; portEXIT_CRITICAL(&lock); return copy;
}
void waiting(const char* reason) {
    portENTER_CRITICAL(&lock);
    if(status.good>=512 && status.good_blocks>=2 && !status.system_fault && status.state!=State::Invalid && status.state!=State::Pvc) {
        if(status.state!=State::Waiting || strcmp(status.reason,reason)!=0) ++status.revision;
        status.state=State::Waiting; status.reason=reason;
    }
    portEXIT_CRITICAL(&lock);
}
void alert_task(void*) {
    uint32_t logged=0;
    State previous=State::Invalid;
    int64_t phase_start=0;
#if CONFIG_ECG_HARDWARE_SELF_TEST
    const int64_t self_test_start=esp_timer_get_time();
    bool self_test=true;
    bool blink_announced=false;
    console_lock();
    printf("ALERT_TEST: LED NORMAL TEST source=HARDWARE_SELF_TEST not_ai=1\n");
    console_unlock();
#endif
    while(true) {
        const int64_t now=esp_timer_get_time();
        portENTER_CRITICAL(&lock);
        if(status.last_sample && now-status.last_sample>20000) invalid_locked("SAMPLING_STALLED");
        Status s=status;
        portEXIT_CRITICAL(&lock);
        const State physical=s.demo?s.demo_state:s.state;
        if(physical!=previous) {phase_start=now;previous=physical;}
        const auto pattern=alert_pattern(physical,now-phase_start);
        bool led=pattern.led,buzzer=pattern.buzzer;
#if CONFIG_ECG_HARDWARE_SELF_TEST
        // Explicit boot-only hardware test overrides physical output, not AI state.
        // Timer-driven elapsed-time state machine: no delay in ADC or AI tasks.
        if(self_test) {
            const int64_t elapsed=now-self_test_start;
            if(elapsed<2000000) { led=true; buzzer=false; }
            else if(elapsed<5000000) {
                if(!blink_announced) {
                    console_lock();
                    printf("ALERT_TEST: LED BLINK + BUZZER TEST source=HARDWARE_SELF_TEST not_ai=1\n");
                    console_unlock();
                    blink_announced=true;
                }
                led=buzzer=((elapsed-2000000)%500000)<150000;
            } else {
                led=buzzer=false; self_test=false; logged=0;
                console_lock();
                printf("ALERT_TEST: SELF TEST COMPLETE source=HARDWARE_SELF_TEST not_ai=1 restore_ai_state=1\n");
                console_unlock();
            }
        }
#endif
        const esp_err_t a=gpio_set_level(GPIO_NUM_23,led), b=gpio_set_level(GPIO_NUM_25,buzzer);
        if(a!=ESP_OK || b!=ESP_OK) {
            portENTER_CRITICAL(&lock);status.output_fault=true;status.self_test=false;status.led=false;status.buzzer=false;portEXIT_CRITICAL(&lock);
            fault("ALERT_GPIO_ERROR");
            const auto off_a=gpio_set_level(GPIO_NUM_23,0),off_b=gpio_set_level(GPIO_NUM_25,0);
            console_lock(); printf("ECG_ERROR reason=ALERT_GPIO_ERROR led=%s buzzer=%s off_led=%s off_buzzer=%s\n",esp_err_to_name(a),esp_err_to_name(b),esp_err_to_name(off_a),esp_err_to_name(off_b)); console_unlock();
            while(true) vTaskDelay(portMAX_DELAY);
        }
        portENTER_CRITICAL(&lock);status.led=led;status.buzzer=buzzer;
#if CONFIG_ECG_HARDWARE_SELF_TEST
        status.self_test=self_test;
#endif
        portEXIT_CRITICAL(&lock);
        if(logged!=s.revision) {
            logged=s.revision;
            const char* name=state_name(s.state);
            console_lock();
            printf("ECG_STATUS state=%s reason=%s\n",name,s.reason);
            console_unlock();
        }
        vTaskDelay(std::max<TickType_t>(1,pdMS_TO_TICKS(20)));
    }
}

void worker(void*) {
    portENTER_CRITICAL(&lock);
    if(!status.system_fault && status.state==State::Waiting) {status.reason="MODEL_VALIDATION_PENDING";++status.revision;}
    portEXIT_CRITICAL(&lock);
#if CONFIG_ECG_AI_TEST_ONLY
    bool ready=model_init();
    if(ready) {
        ready=ai_test_only_begin();
        const bool golden=ready && model_golden_test();
        ready=ai_test_only_finish(golden) && golden;
    }
#else
    bool ready=model_init() && model_golden_test();
#endif
    portENTER_CRITICAL(&lock); status.model_ready=ready;
#if CONFIG_ECG_AI_LIVE
    if(status.state!=State::Invalid && !status.system_fault)
        ecg_ai::clear(status.ai,ready?"COLLECTING_R_ALIGNED_BEAT":"MODEL_OR_GOLDEN_FAILED");
#endif
    portEXIT_CRITICAL(&lock);
    if(!ready) fault("MODEL_OR_GOLDEN_FAILED");
#if CONFIG_ECG_GOLDEN_ALERT_DEMO
    if(ready) {
        // Explicit static-test display; no live classification is published here.
        for(State test : {State::Normal,State::Pvc}) {
            console_lock(); printf("ECG_TEST source=STATIC_GOLDEN_DATA alert=%s duration_ms=2000 not_live=1\n",test==State::Pvc?"PVC":"NORMAL"); console_unlock();
            portENTER_CRITICAL(&lock); status.demo=true; status.demo_state=test; portEXIT_CRITICAL(&lock);
            vTaskDelay(pdMS_TO_TICKS(2000));
        }
        portENTER_CRITICAL(&lock); status.demo=false; invalid_locked("COLLECTING_AFTER_GOLDEN_DEMO"); portEXIT_CRITICAL(&lock);
    }
#endif
#if CONFIG_ECG_AI_LIVE
    static ecg_ai::Engine ai_engine;
    static ecg_ai::Window ai_window;
    static int8_t ai_quantized[256];
    bool ai_reset=true;
    uint32_t engine_rejections=0;
    auto reset_ai=[&]() {ai_engine.reset();ai_reset=false;};
#endif
    static Block block;
    uint32_t last_id=0,last_generation=UINT32_MAX;
    int64_t last_time=0;
    while(true) {
        if(xQueueReceive(blocks,&block,portMAX_DELAY)!=pdTRUE) continue;
        if(!ready) continue;
        if(hash_block(block)!=block.hash) { fault("PROCESS_QUEUE_INTEGRITY"); 
#if CONFIG_ECG_AI_LIVE
            ai_reset=true;
#endif
 continue; }
        const Status health=snapshot();
        if(block.generation!=health.generation || health.system_fault) {
            
#if CONFIG_ECG_AI_LIVE
            ai_reset=true;
#endif
 last_time=0; last_id=block.id; continue;
        }
        if(last_id && block.id!=last_id+1) {
            invalid("PROCESS_BLOCK_GAP"); 
#if CONFIG_ECG_AI_LIVE
            ai_reset=true;
#endif
 last_time=0; last_id=block.id; continue;
        }
        if(last_generation!=block.generation) { 
#if CONFIG_ECG_AI_LIVE
            ai_reset=true;
#endif
 last_time=0; }
        last_id=block.id; last_generation=block.generation;
        const char* issue=signal_block_reason(block.raw,block.timestamps);
        const auto metrics=signal_metrics(block.raw);
        portENTER_CRITICAL(&lock);
        if(status.generation==block.generation && !status.system_fault) {
            status.metrics=metrics;status.quality_known=true;status.quality_time=block.timestamps[255];
        }
        portEXIT_CRITICAL(&lock);
        if(!issue && last_time && (block.timestamps[0]-last_time<2000 || block.timestamps[0]-last_time>6000)) issue="BLOCK_BOUNDARY_GAP";
        last_time=block.timestamps[255];
        if(issue) {
            // A newer instantaneous lead-off/ADC fault must not be overwritten
            // by an old buffer's quality result computed outside the lock.
            portENTER_CRITICAL(&lock);
            if(status.generation==block.generation)invalid_locked(issue);
            portEXIT_CRITICAL(&lock);
            
#if CONFIG_ECG_AI_LIVE
            ai_reset=true;
#endif
last_time=0;continue;
        }
        // Recovery requires two complete quality-passing blocks, not merely
        // individual non-clipped samples. Invalid/lead-off remains immediate.
        portENTER_CRITICAL(&lock);
        if(status.generation==block.generation && !status.system_fault) {
            if(status.good_blocks<2)++status.good_blocks;
            if(status.state==State::Waiting && status.good_blocks<2) {
                status.state=State::Collecting;status.reason="COLLECTING";++status.revision;
            }
            if(recovery_allowed(status.state,status.system_fault,status.good,status.good_blocks,status.generation==block.generation)) {
                status.state=State::Collecting;status.reason="COLLECTING";++status.revision;
            }
        }
        portEXIT_CRITICAL(&lock);
        if(snapshot().state==State::Invalid)continue;
#if CONFIG_ECG_AI_LIVE
        waiting("COLLECTING_R_ALIGNED_BEAT");
        if(ai_reset)reset_ai();
        bool blocked=false;
        for(int i=0;i<256;++i) {
            issue=ai_engine.push(block.raw[i],block.timestamps[i],(static_cast<int64_t>(block.id)-1)*256+i,block.generation);
            if(issue) {
                portENTER_CRITICAL(&lock);ecg_ai::clear(status.ai,issue);portEXIT_CRITICAL(&lock);
                if(strcmp(issue,"NO_RELIABLE_R_PEAK")!=0){ai_reset=true;blocked=true;break;}
            }
        }
        if(blocked)reset_ai();
        while(ai_engine.pop(ai_window)) {
            const auto h=snapshot();const int64_t now=esp_timer_get_time();
            const bool safe=h.generation==ai_window.generation && !h.system_fault && !h.output_fault &&
                h.state!=State::Invalid && h.good>=512 && h.good_blocks>=2 && now-h.last_sample<20000;
            const char* reject=nullptr;
            if(!safe)reject="SIGNAL_CHANGED_BEFORE_INFERENCE";
            else if(now<ai_window.end_us || now-ai_window.end_us>ecg_ai::kMaxWindowAgeUs)reject="BEAT_TOO_OLD";
            unsigned clipped=0;const int64_t prep_start=esp_timer_get_time();
            if(!reject && !ecg_preprocessing::quantize(ai_window.raw,ai_quantized,kInputScale,kInputZero,clipped))reject="NORMALIZATION_FAILED";
            if(!reject && clipped)reject="INPUT_QUANTIZATION_CLIPPING";
            const int64_t prep=esp_timer_get_time()-prep_start;
            // Quantization takes time too. Recheck instantaneous gate at launch,
            // then recheck again after Invoke to reject any in-flight invalidation.
            const int64_t launch=esp_timer_get_time();
            portENTER_CRITICAL(&lock);
            const bool launch_safe=status.model_ready && status.generation==ai_window.generation && !status.system_fault && !status.output_fault &&
                status.state!=State::Invalid && status.good>=512 && status.good_blocks>=2 && launch-status.last_sample<20000;
            if(!reject && !launch_safe)reject="SIGNAL_CHANGED_BEFORE_INFERENCE";
            if(!reject)++status.ai.inference_calls;
            portEXIT_CRITICAL(&lock);
            float score=0;int code=0;int64_t latency=0;
            if(!reject && !model_invoke_quantized(ai_quantized,score,code,latency))reject="INFERENCE_FAILED";
            const int64_t end=esp_timer_get_time();
            portENTER_CRITICAL(&lock);
            const bool still_safe=status.generation==ai_window.generation && !status.system_fault && !status.output_fault &&
                status.state!=State::Invalid && status.good>=512 && status.good_blocks>=2 && end-status.last_sample<20000;
            if(reject){++status.ai.rejected;ecg_ai::clear(status.ai,reject,!still_safe);}
            else if(!still_safe){++status.ai.rejected;ecg_ai::clear(status.ai,status.reason,true);}
            else ecg_ai::publish(status.ai,score,end,ai_window.r_sample,ai_window.r_us,ai_window.end_us,latency,prep,true);
            portEXIT_CRITICAL(&lock);
            vTaskDelay(1);
        }
        // Diagnostics are read outside the ADC task; only scalar copy is locked.
        const uint32_t free=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        const uint32_t minimum=heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        const uint32_t stack=uxTaskGetStackHighWaterMark(nullptr);
        portENTER_CRITICAL(&lock);
        status.ai.rejected+=ai_engine.total_rejected()-engine_rejections;engine_rejections=ai_engine.total_rejected();
        status.ai.detected=ai_engine.detected();status.ai.queue_depth=ai_engine.depth();
        status.ai.queue_high_water=ai_engine.high_water;status.ai.queue_drops=ai_engine.drops;
        status.ai.heap_free=free;status.ai.heap_min=minimum;status.ai.stack_free=stack;
        portEXIT_CRITICAL(&lock);
#else
        waiting("AI_DIAGNOSTIC_MODE");
#endif
        vTaskDelay(1); // Worker only; sampling has no delays or inference.
    }
}
} // namespace

void pipeline_observe(int raw,bool adc_error,bool leads,bool missed,int64_t timestamp) {
    portENTER_CRITICAL(&lock);
    const int64_t delta=timestamp-status.last_sample;
    const bool had_sample=status.last_sample!=0;
    status.last_sample=timestamp;
    if(leads) invalid_locked("LEADS_OFF");
    else if(adc_error) invalid_locked("ADC_READ_ERROR");
    else if(raw<=CONFIG_ECG_ADC_RAIL_MARGIN || raw>=4095-CONFIG_ECG_ADC_RAIL_MARGIN) invalid_locked("ADC_SATURATION");
    else if(missed || (had_sample && (delta<2000 || delta>6000))) invalid_locked("SAMPLE_GAP");
    else {
        if(status.good<512) ++status.good;
    }
    portEXIT_CRITICAL(&lock);
}
void pipeline_offer(uint32_t number,const int* raw,const int64_t* timestamps,bool integrity_ok) {
    if(!blocks) return;
    if(!integrity_ok) {
        if(snapshot().state!=State::Invalid) invalid("ADC_BUFFER_INTEGRITY_OR_GAP");
        return;
    }
    // Golden validation can take seconds. Raw telemetry/instant safety checks
    // continue, but do not manufacture PROCESS_QUEUE_FULL faults at startup.
    const auto health=snapshot();
    if(!health.model_ready || health.system_fault)return;
    memset(&outgoing,0,sizeof(outgoing));
    outgoing.id=number;
    outgoing.generation=snapshot().generation;
    memcpy(outgoing.raw,raw,sizeof(outgoing.raw));
    memcpy(outgoing.timestamps,timestamps,sizeof(outgoing.timestamps));
    outgoing.hash=hash_block(outgoing);
    if(xQueueSend(blocks,&outgoing,0)!=pdTRUE) {
#if CONFIG_ECG_AI_LIVE
        portENTER_CRITICAL(&lock);++status.ai.block_drops;portEXIT_CRITICAL(&lock);
#endif
        invalid("PROCESS_QUEUE_FULL");
    }
}
void pipeline_sampling_fault() { fault("SAMPLING_INIT_FAILED"); }
PipelineTelemetry pipeline_telemetry() {
    const auto s=snapshot();
    return {s.self_test?"SELF_TEST":state_name(s.state),s.reason,s.model_ready,s.led,s.buzzer,s.self_test,
        s.quality_known,s.good_blocks>=2 && s.good>=512 && s.state!=State::Invalid && s.state!=State::Fault,
        s.metrics.clips,s.metrics.ptp,s.metrics.diff_percent,s.metrics.power50_ratio,s.metrics.baseline_delta,s.quality_time};
}
esp_err_t pipeline_init() {
    esp_err_t a=gpio_set_level(GPIO_NUM_23,0),b=gpio_set_level(GPIO_NUM_25,0);
    if(a!=ESP_OK || b!=ESP_OK) return a!=ESP_OK?a:b;
    gpio_config_t config={}; config.pin_bit_mask=(1ULL<<23)|(1ULL<<25);
    config.mode=GPIO_MODE_OUTPUT; config.pull_up_en=GPIO_PULLUP_DISABLE; config.pull_down_en=GPIO_PULLDOWN_DISABLE;
    config.intr_type=GPIO_INTR_DISABLE;
    esp_err_t error=gpio_config(&config);
    if(error!=ESP_OK) return error;
    blocks=xQueueCreate(2,sizeof(Block));
    if(!blocks) return ESP_ERR_NO_MEM;
    if(xTaskCreatePinnedToCore(alert_task,"ecg_alert",4096,nullptr,2,nullptr,0)!=pdPASS) return ESP_ERR_NO_MEM;
    if(xTaskCreatePinnedToCore(worker,"ecg_ai",12288,nullptr,4,&ai_task_handle,0)!=pdPASS) { invalid("AI_TASK_ALLOCATION_FAILED"); return ESP_ERR_NO_MEM; }
    return ESP_OK;
}
int pipeline_ai_json(char* output,size_t capacity) {
#if CONFIG_ECG_AI_LIVE
    const auto s=snapshot();auto v=s.ai;const int64_t now=esp_timer_get_time();
    if(!s.model_ready || s.system_fault)ecg_ai::clear(v,s.reason,s.system_fault);
    else if(s.state==State::Invalid || s.output_fault || !s.last_sample || now-s.last_sample>20000)
        ecg_ai::clear(v,s.state==State::Invalid?s.reason:"SAMPLING_STALLED",true);
    else if(s.good<512 || s.good_blocks<2)ecg_ai::clear(v,"QUALITY_RECOVERY_PENDING");
    else if(v.has_result && !ecg_ai::fresh(v,now))ecg_ai::clear(v,"PREDICTION_STALE");
    char probability[32]="null";
    if(v.has_result)snprintf(probability,sizeof(probability),"%.9f",v.probability);
    return snprintf(output,capacity,
        ",\"ai\":{\"mode\":\"AI_LIVE\",\"source\":\"ADC_CNN\",\"experimental\":true,\"state\":\"%s\",\"reason\":\"%s\",\"p_pvc\":%s,"
        "\"r_index\":%lld,\"r_t_us\":%lld,\"window_end_us\":%lld,\"result_t_us\":%lld,\"valid_until_us\":%lld,\"latency_us\":%lld,\"prep_us\":%lld,"
        "\"classified\":%lu,\"rejected\":%lu,\"queue_drops\":%lu,\"block_drops\":%lu,\"q_depth\":%lu,\"q_high\":%lu,\"detected\":%lu,\"inference_calls\":%lu,"
        "\"heap_free\":%u,\"heap_min\":%u,\"stack_free\":%u}}",
        v.state,v.reason,probability,static_cast<long long>(v.r_sample),static_cast<long long>(v.r_us),static_cast<long long>(v.window_end_us),
        static_cast<long long>(v.result_us),static_cast<long long>(v.valid_until_us),static_cast<long long>(v.latency_us),static_cast<long long>(v.prep_us),
        static_cast<unsigned long>(v.classified),static_cast<unsigned long>(v.rejected),static_cast<unsigned long>(v.queue_drops),
        static_cast<unsigned long>(v.block_drops),static_cast<unsigned long>(v.queue_depth),static_cast<unsigned long>(v.queue_high_water),static_cast<unsigned long>(v.detected),static_cast<unsigned long>(v.inference_calls),
        static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
        static_cast<unsigned>(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),
        ai_task_handle?static_cast<unsigned>(uxTaskGetStackHighWaterMark(ai_task_handle)):0);
#else
    (void)output;(void)capacity;return 0;
#endif
}
