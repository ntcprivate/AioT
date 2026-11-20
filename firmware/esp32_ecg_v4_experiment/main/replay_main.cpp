// Continuous Development stream, real 250 Hz pacing; NO ADC or annotation access.
#include <algorithm>
#include <cstdio>
#include <cstring>
#include "driver/gptimer.h"
#include "esp_attr.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "mbedtls/sha256.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "pipeline.h"
#include "telemetry.h"
#include "trace_transport.h"
#if V4_REPLAY_PVC
#include "pvc_replay_identity.h"
extern const uint8_t stream_start[] asm("_binary_INCART_PVC_V1_bin_start");
extern const uint8_t stream_end[] asm("_binary_INCART_PVC_V1_bin_end");
#else
#include "replay_identity.h"
#endif
#if V4_REPLAY_INCART
extern const uint8_t stream_start[] asm("_binary_INCART_I08_bin_start");
extern const uint8_t stream_end[] asm("_binary_INCART_I08_bin_end");
#elif !V4_REPLAY_PVC
extern const uint8_t stream_start[] asm("_binary_MITBIH_100_bin_start");
extern const uint8_t stream_end[] asm("_binary_MITBIH_100_bin_end");
#endif
namespace {
TaskHandle_t sampler=nullptr;gptimer_handle_t timer=nullptr;
bool IRAM_ATTR tick(gptimer_handle_t,const gptimer_alarm_event_data_t*,void*){
    BaseType_t wake=pdFALSE;vTaskNotifyGiveFromISR(sampler,&wake);return wake==pdTRUE;
}
bool asset_ok(){
    if(stream_end-stream_start!=15360*2)return false;
    uint8_t digest[32];char hex[65];if(mbedtls_sha256(stream_start,stream_end-stream_start,digest,0))return false;
    for(unsigned i=0;i<32;++i){snprintf(hex+2*i,3,"%02x",digest[i]);}
    return strcmp(hex,kReplaySha)==0;
}
void run(void*){
    // Golden test runs in model worker first; no replay input discarded during it.
    const int64_t deadline=esp_timer_get_time()+120000000;
    while(!pipeline_telemetry().model_ready && esp_timer_get_time()<deadline)vTaskDelay(pdMS_TO_TICKS(50));
    if(!pipeline_telemetry().model_ready){console_lock();printf("V4_REPLAY_ABORT reason=MODEL_NOT_READY\n");console_unlock();vTaskDelete(nullptr);return;}
    static int raw[256];static int64_t times[256];uint32_t missed=0;
    console_lock();printf("V4_REPLAY_BEGIN record=%s samples=15360 fs=250 sha256=%s source=LABELED_REPLAY analog_validated=0\n",kReplayRecord,kReplaySha);console_unlock();
    ESP_ERROR_CHECK(gptimer_start(timer));
    for(unsigned i=0;i<15360;++i){
        const uint32_t pending=ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        const int64_t now=esp_timer_get_time();
        if(pending!=1){missed+=pending?pending-1:1;pipeline_replay_stopped(false);break;}
        unsigned offset=i%256;raw[offset]=int(stream_start[2*i])|(int(stream_start[2*i+1])<<8);times[offset]=now;
        pipeline_observe(raw[offset],false,false,false,now);
        telemetry_sample(raw[offset],now,0,0,false,false);
        if(offset==255){
            int64_t minimum=INT64_MAX,maximum=0;
            for(unsigned j=1;j<256;++j){const int64_t dt=times[j]-times[j-1];minimum=std::min(minimum,dt);maximum=std::max(maximum,dt);}
            telemetry_health(0,missed,0,true,255,times[0],times[255],minimum,maximum);
            pipeline_offer(i/256+1,raw,times,true);
        }
    }
    ESP_ERROR_CHECK(gptimer_stop(timer));ESP_ERROR_CHECK(gptimer_disable(timer));
    // Wall-clock sample freshness is preserved: stopping a replay invalidates pending live outputs.
    vTaskDelay(pdMS_TO_TICKS(2000));pipeline_experiment_summary();pipeline_replay_stopped(missed==0);
    console_lock();printf("V4_REPLAY_END record=%s stream_complete=%d missed=%lu heap_free=%u heap_min=%u status=CAPTURE_ONLY_NOT_ACCURACY_PASS\n",kReplayRecord,int(missed==0),(unsigned long)missed,
        unsigned(heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)),unsigned(heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT)));console_unlock();
    vTaskDelete(nullptr);
}
}
extern "C" void app_main(){
    ESP_ERROR_CHECK(telemetry_uart_init());
    if(!asset_ok()){console_lock();printf("V4_REPLAY_ABORT reason=ASSET_HASH\n");console_unlock();return;}
    gptimer_config_t cfg={};cfg.clk_src=GPTIMER_CLK_SRC_DEFAULT;cfg.direction=GPTIMER_COUNT_UP;cfg.resolution_hz=1000000;
    ESP_ERROR_CHECK(gptimer_new_timer(&cfg,&timer));
    gptimer_event_callbacks_t cb={};cb.on_alarm=tick;ESP_ERROR_CHECK(gptimer_register_event_callbacks(timer,&cb,nullptr));
    gptimer_alarm_config_t alarm={};alarm.alarm_count=4000;alarm.flags.auto_reload_on_alarm=true;
    ESP_ERROR_CHECK(gptimer_set_alarm_action(timer,&alarm));ESP_ERROR_CHECK(gptimer_enable(timer));
    ESP_ERROR_CHECK(pipeline_init());ESP_ERROR_CHECK(telemetry_init());
    if(xTaskCreatePinnedToCore(run,"v4_replay",4096,nullptr,10,&sampler,1)!=pdPASS){pipeline_sampling_fault();ESP_ERROR_CHECK(gptimer_disable(timer));}
}
