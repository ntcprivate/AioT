#include "trace_transport.h"
#include "pipeline.h"
#include "model.h"
#include "signal.h"
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

namespace {
#if CONFIG_ECG_ENABLE_EXPERIMENTAL_LIVE
constexpr bool kLiveOption=true;
#else
constexpr bool kLiveOption=false;
#endif
using State=EcgState;
struct Status {
    State state=State::Waiting;
    const char* reason="COLLECTING";
    uint32_t generation=0, good=0, revision=1;
    int64_t last_sample=0, last_ai=0, pvc_until=0;
    float score=0;
    int64_t latency=0;
    bool model_ready=false, demo=false, output_fault=false,system_fault=false;
    bool led=false,buzzer=false,self_test=false,quality_known=false;
    unsigned good_blocks=0;
    SignalMetrics metrics={};int64_t quality_time=0;
    State demo_state=State::Waiting;
};
portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
Status status;
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
    status.state=State::Invalid; status.reason=reason;
    status.good=0; status.good_blocks=0; status.pvc_until=0; status.last_ai=0;
}
void fault(const char* reason) {
    portENTER_CRITICAL(&lock);
    status.system_fault=true;status.state=State::Fault;status.reason=reason;
    status.good=status.good_blocks=0;status.last_ai=status.pvc_until=0;++status.revision;++status.generation;
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
[[maybe_unused]] bool publish(float score,int64_t latency,uint32_t generation) {
    const int64_t now=esp_timer_get_time();
    bool accepted=false;
    portENTER_CRITICAL(&lock);
    if(classification_allowed(status.model_ready,kLiveOption,kLivePipelineValidated,
       !status.output_fault && !status.system_fault && status.good>=512 && status.good_blocks>=2 && status.state!=State::Invalid,
       now-status.last_sample<20000,status.generation==generation)) {
        bool pvc=score>=0.52f;
        if(pvc || now>=status.pvc_until) {
            status.state=pvc?State::Pvc:State::Normal;
            if(pvc) status.pvc_until=now+2000000;
            status.score=score; status.latency=latency; status.last_ai=now;
            status.reason="EXPERIMENTAL_BENCH_ONLY"; ++status.revision; accepted=true;
        }
    }
    portEXIT_CRITICAL(&lock);
    return accepted;
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
        if(status.state==State::Pvc && now>=status.pvc_until) {
            status.state=State::Waiting; status.reason="PVC_HOLD_COMPLETE_WAITING_NEW_BEAT"; ++status.revision;
        } else if(status.state==State::Normal && now-status.last_ai>2000000) {
            status.state=State::Waiting; status.reason="RESULT_STALE"; ++status.revision;
        }
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
            if(s.state==State::Normal || s.state==State::Pvc)
                printf("ECG_AI state=%s p_pvc=%.9f inference_ms=%.3f reason=%s score_calibrated=0\n",name,s.score,s.latency/1000.0,s.reason);
            else printf("ECG_STATUS state=%s reason=%s\n",name,s.reason);
            console_unlock();
        }
        vTaskDelay(std::max<TickType_t>(1,pdMS_TO_TICKS(20)));
    }
}

void worker(void*) {
    portENTER_CRITICAL(&lock);
    if(!status.system_fault && status.state==State::Waiting) {status.reason="MODEL_VALIDATION_PENDING";++status.revision;}
    portEXIT_CRITICAL(&lock);
    bool ready=model_init() && model_golden_test();
    portENTER_CRITICAL(&lock); status.model_ready=ready; portEXIT_CRITICAL(&lock);
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
    static BeatDetector detector;
    static Block block;
    [[maybe_unused]] static float beat[256];
    uint32_t last_id=0,last_generation=UINT32_MAX;
    int64_t last_time=0;
    while(true) {
        if(xQueueReceive(blocks,&block,portMAX_DELAY)!=pdTRUE) continue;
        if(!ready) continue;
        if(hash_block(block)!=block.hash) { fault("PROCESS_QUEUE_INTEGRITY"); detector.reset(); continue; }
        const Status health=snapshot();
        if(block.generation!=health.generation || health.system_fault) {
            detector.reset(); last_time=0; last_id=block.id; continue;
        }
        if(last_id && block.id!=last_id+1) {
            invalid("PROCESS_BLOCK_GAP"); detector.reset(); last_time=0; last_id=block.id; continue;
        }
        if(last_generation!=block.generation) { detector.reset(); last_time=0; }
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
            detector.reset();last_time=0;continue;
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
#if !CONFIG_ECG_ENABLE_EXPERIMENTAL_LIVE
        waiting("R_DETECTOR_UNVALIDATED_LIVE_DISABLED");
        continue;
#else
        if(!kLivePipelineValidated) {waiting("R_DETECTOR_UNVALIDATED_LIVE_DISABLED");continue;}
        waiting("COLLECTING_R_ALIGNED_BEAT");
        for(int i=0;i<256;++i) {
            issue=nullptr;
            bool complete=detector.push(block.raw[i],block.timestamps[i],beat,issue);
            if(issue) { invalid(issue); break; }
            if(!complete) continue;
            float score; int64_t latency; unsigned clipped=0;
            const int64_t window_end=block.timestamps[i];
            if(esp_timer_get_time()-window_end>1500000) { invalid("BEAT_TOO_OLD"); break; }
            if(!model_invoke_beat(beat,score,latency,clipped)) { invalid("INFERENCE_OR_NORMALIZATION_FAILED"); break; }
            if(clipped) { invalid("INPUT_QUANTIZATION_CLIPPING"); break; }
            // A new invalid sample during Invoke changes generation; reject stale result.
            if(publish(score,latency,block.generation)) {
                console_lock(); printf("ECG_BEAT source=EXPERIMENTAL_ADC window_end_us=%lld clipped=%u stack_watermark_bytes=%u heap_internal_free=%u\n",
                    static_cast<long long>(window_end),clipped,static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)),
                    static_cast<unsigned>(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT))); console_unlock();
            }
        }
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
    if(xQueueSend(blocks,&outgoing,0)!=pdTRUE) invalid("PROCESS_QUEUE_FULL");
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
    if(xTaskCreatePinnedToCore(worker,"ecg_ai",12288,nullptr,4,nullptr,0)!=pdPASS) { invalid("AI_TASK_ALLOCATION_FAILED"); return ESP_ERR_NO_MEM; }
    return ESP_OK;
}
