#include "telemetry.h"
#include "telemetry_codec.h"
#include "trace_transport.h"
#include "pipeline.h"
#include "sdkconfig.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
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
std::atomic<uint32_t> format_errors{0},uart_write_errors{0},uart_tx_timeouts{0};
std::atomic<uint32_t> adc_errors_total{0},missed_total{0},late_total{0},snapshot_errors{0};
#if CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST
constexpr bool kSynthetic=true;
constexpr const char* kSource="SYNTHETIC_TEST";
#else
constexpr bool kSynthetic=false;
constexpr const char* kSource="HARDWARE";
#endif
struct Clock {uint32_t intervals;int64_t first,last,minimum,maximum;};
Clock acquisition={};portMUX_TYPE clock_lock=portMUX_INITIALIZER_UNLOCKED;
std::atomic<uint32_t> attempts{0};
uint32_t tx_samples=0,tx_bytes=0;
uint32_t uart_baud_actual=0;
struct Completion {uint32_t samples;int64_t time;};
Completion completed[32]={};unsigned completed_count=0,completed_next=0;
bool emit(const char* json) {
    char framed[1800];const int n=ecg_wire::frame(json,framed,sizeof(framed));
    if(n<0) {++format_errors;++write_errors;return false;}
    console_lock();
    if(console_trace_active()) {console_unlock();return false;}
    const int written=uart_write_bytes(UART_NUM_0,framed,static_cast<size_t>(n));
    console_unlock(); // Do not hold the app/stdio lock while waiting for the wire.
    if(written!=n) {++uart_write_errors;++write_errors;return false;}
    if(uart_wait_tx_done(UART_NUM_0,pdMS_TO_TICKS(500))!=ESP_OK) {++uart_tx_timeouts;++write_errors;return false;}
    tx_bytes+=static_cast<uint32_t>(n);return true;
}
[[maybe_unused]] void tx_task(void*) {
    Packet packet;char json[1600],hex[ecg_wire::kBatch*ecg_wire::kStride*2+1];
    constexpr char digits[]="0123456789abcdef";
    int64_t last_status=0;
    while(true) {
        if(xQueueReceive(queue,&packet,pdMS_TO_TICKS(100))==pdTRUE) {
            for(size_t i=0;i<sizeof(packet.bytes);++i) {hex[2*i]=digits[packet.bytes[i]>>4];hex[2*i+1]=digits[packet.bytes[i]&15];}
            hex[sizeof(hex)-1]=0;
            const int n=snprintf(json,sizeof(json),"{\"v\":2,\"type\":\"samples\",\"boot\":\"%08lx\",\"seq\":%lu,\"first\":%lu,\"t0\":%lld,\"fs\":250,\"n\":32,\"data\":\"%s\",\"source\":\"%s\",\"pattern\":\"%s\",\"dropped\":%lu}",
                static_cast<unsigned long>(boot),static_cast<unsigned long>(sequence++),static_cast<unsigned long>(packet.first),static_cast<long long>(packet.t0),hex,kSource,kSynthetic?"saw17-v1":"none",static_cast<unsigned long>(dropped.load()));
            if(n>0 && static_cast<size_t>(n)<sizeof(json)) {
                if(emit(json)) {
                    tx_samples+=ecg_wire::kBatch;completed[completed_next]={tx_samples,esp_timer_get_time()};
                    completed_next=(completed_next+1)%32;if(completed_count<32)++completed_count;
                }
            }else {++format_errors;++write_errors;}
        }
        const int64_t now=esp_timer_get_time();
        if(now-last_status>=500000) {
            last_status=now;const auto s=pipeline_telemetry();
            Clock clock;portENTER_CRITICAL(&clock_lock);clock=acquisition;portEXIT_CRITICAL(&clock_lock);
            char hz[32]="null",mean[32]="null",txhz[32]="null";
            if(clock.intervals && clock.last>clock.first) {
                snprintf(hz,sizeof(hz),"%.6f",clock.intervals*1000000.0/(clock.last-clock.first));
                snprintf(mean,sizeof(mean),"%.3f",static_cast<double>(clock.last-clock.first)/clock.intervals);
            }
            if(completed_count>=2) {
                const auto& first=completed[completed_count==32?completed_next:0];
                const auto& last=completed[(completed_next+31)%32];
                if(last.time>first.time)snprintf(txhz,sizeof(txhz),"%.6f",static_cast<uint32_t>(last.samples-first.samples)*1000000.0/(last.time-first.time));
            }
            const int n=snprintf(json,sizeof(json),"{\"v\":2,\"type\":\"status\",\"boot\":\"%08lx\",\"seq\":%lu,\"t_us\":%lld,\"firmware\":\"ecg-monitor-2\",\"source\":\"%s\",\"state\":\"%s\",\"reason\":\"%s\",\"model\":\"%s\",\"golden\":%s,\"classification\":\"UNKNOWN\",\"p_pvc\":null,\"threshold\":0.52,\"r_validated\":false,\"bpm\":null,\"rr_ms\":null,\"led\":%s,\"buzzer\":%s,\"self_test\":%s,\"clip_count\":%lu,\"ptp\":%d,\"diff_percent\":%.4f,\"power50_ratio\":%.6f,\"baseline_delta\":%.4f,\"quality_known\":%s,\"quality_t_us\":%lld,\"tx_dropped\":%lu,\"write_errors\":%lu}",
                static_cast<unsigned long>(boot),static_cast<unsigned long>(sequence++),static_cast<long long>(now),kSource,s.state,kSynthetic && strcmp(s.state,"SYSTEM_FAULT")!=0?"SYNTHETIC_TELEMETRY_TEST":s.reason,s.model_ready?"LOCKED":"DISABLED",s.model_ready?"true":"false",s.led?"true":"false",s.buzzer?"true":"false",s.self_test?"true":"false",static_cast<unsigned long>(s.clips),s.ptp,s.diff_percent,s.power50_ratio,s.baseline_delta,s.quality_known?"true":"false",static_cast<long long>(s.quality_time),static_cast<unsigned long>(dropped.load()),static_cast<unsigned long>(write_errors.load()));
            // Append cumulative sampler health before the closing brace.
            if(n>0 && static_cast<size_t>(n)<sizeof(json)) {
                const int extra=snprintf(json+n-1,sizeof(json)-n+1,",\"quality_valid\":%s,\"r_peaks\":[],\"adc_errors\":%lu,\"missed_est\":%lu,\"late\":%lu,\"snapshot_errors\":%lu,\"rail_margin\":%d,\"diff_limit\":%d,\"baud\":115200,\"uart_baud_actual\":%lu,\"sample_attempts\":%lu,\"tx_samples\":%lu,\"tx_bytes\":%lu,\"acq_hz\":%s,\"tx_hz\":%s,\"dt_mean_us\":%s,\"dt_min_us\":%lld,\"dt_max_us\":%lld,\"clock_last_us\":%lld,\"format_errors\":%lu,\"uart_write_errors\":%lu,\"uart_tx_timeouts\":%lu}",
                    s.quality_valid?"true":"false",static_cast<unsigned long>(adc_errors_total.load()),static_cast<unsigned long>(missed_total.load()),static_cast<unsigned long>(late_total.load()),static_cast<unsigned long>(snapshot_errors.load()),CONFIG_ECG_ADC_RAIL_MARGIN,CONFIG_ECG_MAX_DIFF_PERCENT,
                    static_cast<unsigned long>(uart_baud_actual),static_cast<unsigned long>(attempts.load()),static_cast<unsigned long>(tx_samples),static_cast<unsigned long>(tx_bytes),hz,txhz,mean,
                    static_cast<long long>(clock.minimum),static_cast<long long>(clock.maximum),static_cast<long long>(clock.last),static_cast<unsigned long>(format_errors.load()),static_cast<unsigned long>(uart_write_errors.load()),static_cast<unsigned long>(uart_tx_timeouts.load()));
                if(extra>0 && static_cast<size_t>(extra)<sizeof(json)-n+1)emit(json);else {++format_errors;++write_errors;}
            }else {++format_errors;++write_errors;}
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
    ++attempts;
    if(!count) {pending.first=sample_index;pending.t0=timestamp;}
    ecg_wire::sample(pending.bytes+count*ecg_wire::kStride,static_cast<uint32_t>(timestamp-pending.t0),raw,
        static_cast<uint8_t>((plus?1:0)|(minus?2:0)|(adc_error?4:0)|(missed?8:0)));
    ++sample_index;
    if(++count==ecg_wire::kBatch) {if(xQueueSend(queue,&pending,0)!=pdTRUE)++dropped;count=0;}
}
void telemetry_health(uint32_t adc_errors,uint32_t missed,uint32_t late,bool snapshot_ok,
    uint32_t intervals,int64_t first_us,int64_t last_us,int64_t dt_min,int64_t dt_max) {
    adc_errors_total.fetch_add(adc_errors);missed_total.fetch_add(missed);late_total.fetch_add(late);
    if(!snapshot_ok)++snapshot_errors;
    portENTER_CRITICAL(&clock_lock);acquisition={intervals,first_us,last_us,dt_min,dt_max};portEXIT_CRITICAL(&clock_lock);
}

esp_err_t telemetry_uart_init() {
#if CONFIG_ECG_TELEMETRY
    if(uart_is_driver_installed(UART_NUM_0))return ESP_ERR_INVALID_STATE;
    uart_config_t config={};config.baud_rate=115200;config.data_bits=UART_DATA_8_BITS;
    config.parity=UART_PARITY_DISABLE;config.stop_bits=UART_STOP_BITS_1;config.flow_ctrl=UART_HW_FLOWCTRL_DISABLE;
    config.source_clk=UART_SCLK_DEFAULT;
    esp_err_t error=uart_param_config(UART_NUM_0,&config);if(error!=ESP_OK)return error;
    error=uart_driver_install(UART_NUM_0,256,4096,0,nullptr,0);if(error!=ESP_OK)return error;
    uart_vfs_dev_use_driver(UART_NUM_0); // All stdout writers share the UART driver's TX lock.
    if(uart_vfs_dev_port_set_tx_line_endings(UART_NUM_0,ESP_LINE_ENDINGS_LF)!=0)return ESP_FAIL;
    uint32_t baud=0;error=uart_get_baudrate(UART_NUM_0,&baud);
    if(error!=ESP_OK)return error;
    uart_baud_actual=baud;
    // The fractional hardware divider can report a nearby integer baud.
    if(baud<114624 || baud>115776)return ESP_FAIL;
#endif
    return ESP_OK;
}
TelemetryTestHealth telemetry_test_health() {
    Clock clock;portENTER_CRITICAL(&clock_lock);clock=acquisition;portEXIT_CRITICAL(&clock_lock);
    const double hz=clock.intervals && clock.last>clock.first?clock.intervals*1000000.0/(clock.last-clock.first):0;
    return {attempts.load(),dropped.load(),adc_errors_total.load(),missed_total.load(),late_total.load(),snapshot_errors.load(),
        write_errors.load(),format_errors.load(),uart_write_errors.load(),uart_tx_timeouts.load(),hz};
}
