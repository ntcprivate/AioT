#include "telemetry.h"
#include "telemetry_codec.h"
#include "trace_transport.h"
#include "pipeline.h"
#include "sdkconfig.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include <atomic>
#include <cstdio>
#include <cstring>
namespace {
static_assert(std::atomic<uint32_t>::is_always_lock_free,"Sampling diagnostics must not wait for a software mutex");
struct Packet {uint32_t first;int64_t t0;uint8_t bytes[ecg_wire::kBatch*ecg_wire::kStride];};
QueueHandle_t queue=nullptr;
Packet pending={};unsigned count=0;uint32_t sample_index=0,sequence=0,boot=0;
std::atomic<uint32_t> dropped{0},write_errors{0};
std::atomic<uint32_t> adc_errors_total{0},missed_total{0},late_total{0},snapshot_errors{0};
void emit(const char* json) {
    console_lock();
    if(!console_trace_active()) {
        if(fprintf(stdout,"ECG1 %08lx %s\n",static_cast<unsigned long>(ecg_wire::crc32(reinterpret_cast<const uint8_t*>(json),strlen(json))),json)<0 || fflush(stdout)!=0) {
            ++write_errors;clearerr(stdout);
        }
    }
    console_unlock();
}
[[maybe_unused]] void tx_task(void*) {
    Packet packet;char json[1200],hex[ecg_wire::kBatch*ecg_wire::kStride*2+1];
    constexpr char digits[]="0123456789abcdef";
    int64_t last_status=0;
    while(true) {
        if(xQueueReceive(queue,&packet,pdMS_TO_TICKS(100))==pdTRUE) {
            for(size_t i=0;i<sizeof(packet.bytes);++i) {hex[2*i]=digits[packet.bytes[i]>>4];hex[2*i+1]=digits[packet.bytes[i]&15];}
            hex[sizeof(hex)-1]=0;
            const int n=snprintf(json,sizeof(json),"{\"v\":1,\"type\":\"samples\",\"boot\":\"%08lx\",\"seq\":%lu,\"first\":%lu,\"t0\":%lld,\"fs\":250,\"n\":32,\"data\":\"%s\",\"dropped\":%lu}",
                static_cast<unsigned long>(boot),static_cast<unsigned long>(sequence++),static_cast<unsigned long>(packet.first),static_cast<long long>(packet.t0),hex,static_cast<unsigned long>(dropped.load()));
            if(n>0 && static_cast<size_t>(n)<sizeof(json))emit(json);else ++write_errors;
        }
        const int64_t now=esp_timer_get_time();
        if(now-last_status>=500000) {
            last_status=now;const auto s=pipeline_telemetry();
            const int n=snprintf(json,sizeof(json),"{\"v\":1,\"type\":\"status\",\"boot\":\"%08lx\",\"seq\":%lu,\"t_us\":%lld,\"firmware\":\"ecg-monitor-1\",\"source\":\"HARDWARE\",\"state\":\"%s\",\"reason\":\"%s\",\"model\":\"%s\",\"golden\":%s,\"classification\":\"UNKNOWN\",\"p_pvc\":null,\"threshold\":0.52,\"r_validated\":false,\"bpm\":null,\"rr_ms\":null,\"led\":%s,\"buzzer\":%s,\"self_test\":%s,\"clip_count\":%lu,\"ptp\":%d,\"diff_percent\":%.4f,\"power50_ratio\":%.6f,\"baseline_delta\":%.4f,\"quality_known\":%s,\"quality_t_us\":%lld,\"tx_dropped\":%lu,\"write_errors\":%lu}",
                static_cast<unsigned long>(boot),static_cast<unsigned long>(sequence++),static_cast<long long>(now),s.state,s.reason,s.model_ready?"LOCKED":"DISABLED",s.model_ready?"true":"false",s.led?"true":"false",s.buzzer?"true":"false",s.self_test?"true":"false",static_cast<unsigned long>(s.clips),s.ptp,s.diff_percent,s.power50_ratio,s.baseline_delta,s.quality_known?"true":"false",static_cast<long long>(s.quality_time),static_cast<unsigned long>(dropped.load()),static_cast<unsigned long>(write_errors.load()));
            // Append cumulative sampler health before the closing brace.
            if(n>0 && static_cast<size_t>(n)<sizeof(json)) {
                const int extra=snprintf(json+n-1,sizeof(json)-n+1,",\"quality_valid\":%s,\"r_peaks\":[],\"adc_errors\":%lu,\"missed_est\":%lu,\"late\":%lu,\"snapshot_errors\":%lu,\"rail_margin\":%d,\"diff_limit\":%d}",
                    s.quality_valid?"true":"false",static_cast<unsigned long>(adc_errors_total.load()),static_cast<unsigned long>(missed_total.load()),static_cast<unsigned long>(late_total.load()),static_cast<unsigned long>(snapshot_errors.load()),CONFIG_ECG_ADC_RAIL_MARGIN,CONFIG_ECG_MAX_DIFF_PERCENT);
                if(extra>0 && static_cast<size_t>(extra)<sizeof(json)-n+1)emit(json);else ++write_errors;
            }else ++write_errors;
        }
    }
}
}
esp_err_t telemetry_init() {
#if CONFIG_ECG_TELEMETRY
    boot=esp_random();queue=xQueueCreate(6,sizeof(Packet));if(!queue)return ESP_ERR_NO_MEM;
    if(xTaskCreatePinnedToCore(tx_task,"ecg_tx",6144,nullptr,2,nullptr,0)!=pdPASS) {vQueueDelete(queue);queue=nullptr;return ESP_ERR_NO_MEM;}
#endif
    return ESP_OK;
}
void telemetry_sample(int raw,int64_t timestamp,uint8_t plus,uint8_t minus,bool adc_error,bool missed) {
    if(!queue)return;
    if(!count) {pending.first=sample_index;pending.t0=timestamp;}
    ecg_wire::sample(pending.bytes+count*ecg_wire::kStride,static_cast<uint32_t>(timestamp-pending.t0),raw,
        static_cast<uint8_t>((plus?1:0)|(minus?2:0)|(adc_error?4:0)|(missed?8:0)));
    ++sample_index;
    if(++count==ecg_wire::kBatch) {if(xQueueSend(queue,&pending,0)!=pdTRUE)++dropped;count=0;}
}
void telemetry_health(uint32_t adc_errors,uint32_t missed,uint32_t late,bool snapshot_ok) {
    adc_errors_total.fetch_add(adc_errors);missed_total.fetch_add(missed);late_total.fetch_add(late);
    if(!snapshot_ok)++snapshot_errors;
}
