// Electronic bench test only. No electrodes on a person; no validated ECG.
#include <algorithm>
#include <climits>
#include <cstddef>
#include <cstring>
#include <cstdio>
#include <cstdint>
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_attr.h"
#include "esp_err.h"
#include "esp_idf_version.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "alert.h"

#if ESP_IDF_VERSION != ESP_IDF_VERSION_VAL(5, 4, 4)
#error "Use ESP-IDF v5.4.4 for this project."
#endif

namespace {
constexpr char kTag[] = "ADC_250HZ";
constexpr int64_t kPeriodUs = 4000;
constexpr int64_t kLateUs = 500; // Diagnostic tolerance, not a clinical criterion.
constexpr size_t kCount = 256;
constexpr adc_channel_t kChannel = ADC_CHANNEL_6; // ADC1_CHANNEL_6 = GPIO34.
constexpr gpio_num_t kLoPlus = GPIO_NUM_26, kLoMinus = GPIO_NUM_27;
struct Sample { int raw; int64_t timestamp_us; int64_t read_duration_us; uint8_t lo_plus, lo_minus; };
struct Summary {
    uint32_t number, samples, adc_ok, adc_errors, leads, late, missed, pending_missed;
    uint32_t summaries_dropped_total;
    int minimum, maximum, first[10];
    int64_t adc_sum, dt_sum, dt_min, dt_max, first_us, last_us, max_lateness;
    uint32_t intervals;
    esp_err_t last_adc_error;
    int64_t boundary_dt_us, read_duration_max_us;
    uint32_t consistency_errors;
    uint32_t checksum; // Last member: checksum covers the exact queued bytes before it.
};
adc_oneshot_unit_handle_t adc = nullptr;
gptimer_handle_t timer = nullptr;
QueueHandle_t summaries = nullptr;
TaskHandle_t sampling_handle = nullptr, logging_handle = nullptr;
// Only the sampling task owns this buffer. It is not queued/copied to Serial.
Sample buffer[kCount];

bool check(esp_err_t error, const char* operation) {
    if (error == ESP_OK) return true;
    ESP_LOGE(kTag, "%s: %s", operation, esp_err_to_name(error));
    return false;
}

bool IRAM_ATTR alarm_callback(gptimer_handle_t, const gptimer_alarm_event_data_t*, void* context) {
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(static_cast<TaskHandle_t>(context), &wake);
    return wake == pdTRUE; // GPTimer driver performs the required ISR yield.
}

uint32_t checksum(const void* data, size_t size) {
    const auto* bytes = static_cast<const uint8_t*>(data);
    uint32_t result = 2166136261u;
    for (size_t i = 0; i < size; ++i) result = (result ^ bytes[i]) * 16777619u;
    return result; // FNV-1a, diagnostic corruption detector, not cryptographic.
}

bool summary_valid(const Summary& s) {
    if (s.samples != kCount || s.adc_ok + s.adc_errors != kCount || s.leads > kCount ||
        s.intervals != kCount - 1 || s.last_us <= s.first_us || s.dt_sum != s.last_us - s.first_us ||
        s.dt_min <= 0 || s.dt_min > s.dt_max || s.consistency_errors) return false;
    if (s.adc_ok && (s.minimum < 0 || s.maximum > 4095 || s.minimum > s.maximum ||
        s.adc_sum < static_cast<int64_t>(s.minimum) * s.adc_ok ||
        s.adc_sum > static_cast<int64_t>(s.maximum) * s.adc_ok)) return false;
    for (int raw : s.first) {
        if (raw == -1) { if (!s.adc_errors) return false; }
        else if (!s.adc_ok || raw < s.minimum || raw > s.maximum) return false;
    }
    return true;
}

void log_task(void*) {
    Summary s;
    uint32_t previous_id = 0, write_errors = 0;
    while (true) {
        if (xQueueReceive(summaries, &s, portMAX_DELAY) != pdTRUE) continue;
        const bool hash_ok = checksum(&s, offsetof(Summary, checksum)) == s.checksum;
        const bool valid = hash_ok && summary_valid(s);
        const bool sequence_ok = s.number > previous_id;
        const uint32_t id_gap = sequence_ok ? s.number - previous_id - 1 : 0;
        previous_id = s.number;
        const double mean_dt = s.intervals ? static_cast<double>(s.dt_sum) / s.intervals : 0;
        const double hz = s.last_us > s.first_us ?
            (s.samples - 1) * 1000000.0 / (s.last_us - s.first_us) : 0;
        // Format one bounded record, including FIRST10; never print it in fragments.
        char line[1536];
        const int length = snprintf(line, sizeof(line),
            "ADC_BUFFER id=%lu samples=%lu adc_ok=%lu adc_errors=%lu min=%d max=%d mean=%.3f "
            "dt_mean_us=%.3f dt_min_us=%lld dt_max_us=%lld interval_count=%lu actual_hz=%.6f "
            "first_us=%lld last_us=%lld boundary_dt_us=%lld read_max_us=%lld "
            "lo_any=%lu late=%lu missed_est=%lu pending_missed=%lu max_lateness_us=%lld "
            "summary_dropped_total=%lu id_gap=%lu uart_write_errors=%lu last_adc_error=%s "
            "leads=%s continuity=%s integrity=%s snapshot_hash=%08lx first10=%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",
            static_cast<unsigned long>(s.number), static_cast<unsigned long>(s.samples),
            static_cast<unsigned long>(s.adc_ok), static_cast<unsigned long>(s.adc_errors),
            s.adc_ok ? s.minimum : -1, s.adc_ok ? s.maximum : -1,
            s.adc_ok ? static_cast<double>(s.adc_sum) / s.adc_ok : 0,
            mean_dt, static_cast<long long>(s.dt_min), static_cast<long long>(s.dt_max),
            static_cast<unsigned long>(s.intervals), hz,
            static_cast<long long>(s.first_us), static_cast<long long>(s.last_us),
            static_cast<long long>(s.boundary_dt_us), static_cast<long long>(s.read_duration_max_us),
            static_cast<unsigned long>(s.leads), static_cast<unsigned long>(s.late),
            static_cast<unsigned long>(s.missed), static_cast<unsigned long>(s.pending_missed),
            static_cast<long long>(s.max_lateness), static_cast<unsigned long>(s.summaries_dropped_total),
            static_cast<unsigned long>(id_gap), static_cast<unsigned long>(write_errors),
            esp_err_to_name(s.last_adc_error), s.leads ? "INVALID_LEADS" : "LEADS_NOT_ASSERTED",
            s.missed || s.adc_errors ? "GAPPED_OR_ADC_ERROR" : "NO_GAP_DETECTED",
            valid && sequence_ok ? "OK" : "FAILED", static_cast<unsigned long>(s.checksum),
            s.first[0], s.first[1], s.first[2], s.first[3], s.first[4],
            s.first[5], s.first[6], s.first[7], s.first[8], s.first[9]);
        // Protect full record + newline/flush against other cooperative stdout writers.
        flockfile(stdout);
        if (length < 0 || static_cast<size_t>(length) >= sizeof(line) - 32) {
            ++write_errors;
            fprintf(stdout, "ADC_WARNING reason=FORMAT_OVERFLOW\n");
        } else {
            const uint32_t line_hash = checksum(line, static_cast<size_t>(length));
            const int suffix = snprintf(line + length, sizeof(line) - length,
                                        " line_fnv1a=%08lx\n", static_cast<unsigned long>(line_hash));
            if (suffix <= 0 || static_cast<size_t>(suffix) >= sizeof(line) - length ||
                fwrite(line, 1, length + suffix, stdout) != static_cast<size_t>(length + suffix)) ++write_errors;
        }
        if (!valid || !sequence_ok) fprintf(stdout, "ADC_WARNING reason=SNAPSHOT_OR_SEQUENCE_INCONSISTENT id=%lu\n", static_cast<unsigned long>(s.number));
        if (fflush(stdout) != 0) { ++write_errors; clearerr(stdout); }
        funlockfile(stdout);
    }
}

void sampling_task(void*) {
    // app_main finishes configuration before releasing this task.
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    const int64_t before_start = esp_timer_get_time();
    if (!check(gptimer_start(timer), "gptimer_start")) {
        check(gptimer_disable(timer), "gptimer_disable after start failure");
        vTaskDelete(nullptr);
        return;
    }
    const int64_t after_start = esp_timer_get_time();
    const int64_t epoch = before_start + (after_start - before_start) / 2;
    // Bounds the uncertainty of the software timestamp used for the timer start.
    ESP_LOGI(kTag, "Timer started; epoch uncertainty <= %lld us; late tolerance=%lld us",
             static_cast<long long>(after_start - before_start), static_cast<long long>(kLateUs));
    uint64_t previous_slot = 0, notifications_total = 0;
    int64_t previous_timestamp = 0;
    uint32_t number = 0, dropped = 0;
    while (true) {
        Summary s;
        // Explicitly initialize padding too: the byte checksum survives queue memcpy.
        memset(&s, 0, sizeof(s));
        s.number = ++number;
        s.minimum = INT_MAX;
        s.maximum = INT_MIN;
        s.dt_min = INT64_MAX;
        for (size_t i = 0; i < kCount; ++i) {
            const uint32_t pending = ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
            Sample& sample = buffer[i];
            sample.raw = -1;
            // Actual software read-call bounds, never an expected alarm timestamp.
            sample.timestamp_us = esp_timer_get_time();
            const esp_err_t error = adc_oneshot_read(adc, kChannel, &sample.raw);
            const int64_t read_end = esp_timer_get_time();
            sample.read_duration_us = read_end - sample.timestamp_us;
            sample.lo_plus = gpio_get_level(kLoPlus);
            sample.lo_minus = gpio_get_level(kLoMinus);
            const int64_t timestamp = sample.timestamp_us;
            notifications_total += pending;
            const uint64_t elapsed_slot = static_cast<uint64_t>(std::max<int64_t>(0, timestamp - epoch) / kPeriodUs);
            // Use absolute notification count, not previous estimated slot + pending:
            // otherwise a coalesced hardware alarm can be counted again next time.
            const uint64_t slot = std::max(notifications_total, elapsed_slot);
            const uint64_t skipped = slot > previous_slot ? slot - previous_slot - 1 : 0;
            s.missed += static_cast<uint32_t>(skipped);
            s.pending_missed += pending > 0 ? pending - 1 : 0;
            const int64_t lateness = std::max<int64_t>(0, timestamp - epoch - static_cast<int64_t>(slot) * kPeriodUs);
            s.max_lateness = std::max(s.max_lateness, lateness);
            if (lateness > kLateUs || skipped > 0 || pending > 1) ++s.late;
            previous_slot = std::max(previous_slot, slot);
            s.read_duration_max_us = std::max(s.read_duration_max_us, sample.read_duration_us);
            if (error != ESP_OK) { sample.raw = -1; ++s.adc_errors; s.last_adc_error = error; }
            else {
                ++s.adc_ok;
                s.adc_sum += sample.raw;
                s.minimum = std::min(s.minimum, sample.raw);
                s.maximum = std::max(s.maximum, sample.raw);
            }
            if (sample.lo_plus || sample.lo_minus) ++s.leads;
            if (i < 10) s.first[i] = sample.raw;
            if (i == 0) s.first_us = timestamp;
            s.last_us = timestamp;
            if (i == 0 && previous_timestamp) s.boundary_dt_us = timestamp - previous_timestamp;
            // Same-buffer intervals: exactly 255, matching actual_hz denominator.
            if (i > 0) {
                const int64_t dt = timestamp - previous_timestamp;
                s.dt_sum += dt;
                s.dt_min = std::min(s.dt_min, dt);
                s.dt_max = std::max(s.dt_max, dt);
                ++s.intervals;
            }
            previous_timestamp = timestamp;
            ++s.samples;
        }
        // Buffer is now frozen: only this task owns it; logger never reads it.
        // Independently recompute all ADC aggregates from that same completed buffer.
        int64_t sum = 0;
        int minimum = INT_MAX, maximum = INT_MIN;
        uint32_t ok = 0, leads = 0;
        for (size_t i = 0; i < kCount; ++i) {
            const Sample& sample = buffer[i];
            if (sample.raw >= 0 && sample.raw <= 4095) {
                ++ok; sum += sample.raw;
                minimum = std::min(minimum, sample.raw);
                maximum = std::max(maximum, sample.raw);
            } else if (sample.raw != -1) ++s.consistency_errors;
            if (sample.lo_plus || sample.lo_minus) ++leads;
            if (i < 10 && s.first[i] != sample.raw) ++s.consistency_errors;
            if (i > 0 && sample.timestamp_us <= buffer[i - 1].timestamp_us) ++s.consistency_errors;
        }
        if (sum != s.adc_sum || ok != s.adc_ok || minimum != s.minimum || maximum != s.maximum || leads != s.leads)
            ++s.consistency_errors;
        s.summaries_dropped_total = dropped;
        if (!summary_valid(s)) ++s.consistency_errors;
        s.checksum = checksum(&s, offsetof(Summary, checksum));
        // Never stall sampling waiting for UART; count summary loss instead.
        if (xQueueSend(summaries, &s, 0) != pdTRUE) ++dropped;
    }
}
} // namespace

extern "C" void app_main() {
    if (!check(alert_init(), "alert_init")) {
        ESP_LOGE(kTag, "Alert self-test unavailable; ADC initialization continues");
    }
    ESP_LOGW(kTag, "Electronic bench test only, no electrodes on a person; no validated ECG or AI input.");
    int pin = -1;
    if (!check(adc_oneshot_channel_to_io(ADC_UNIT_1, kChannel, &pin), "ADC mapping") || pin != 34) {
        ESP_LOGE(kTag, "Expected ADC1_CHANNEL_6 on GPIO34"); return;
    }
    gpio_config_t gpio = {};
    gpio.pin_bit_mask = (1ULL << kLoPlus) | (1ULL << kLoMinus);
    gpio.mode = GPIO_MODE_INPUT;
    gpio.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio.pull_down_en = GPIO_PULLDOWN_DISABLE;
    gpio.intr_type = GPIO_INTR_DISABLE;
    if (!check(gpio_config(&gpio), "gpio_config")) return;
    bool enabled = false;
    // A single cleanup path leaves the timer stopped on every setup failure.
    auto cleanup = [&]() {
        if (sampling_handle) vTaskDelete(sampling_handle);
        if (logging_handle) vTaskDelete(logging_handle);
        if (enabled) check(gptimer_disable(timer), "gptimer_disable cleanup");
        if (timer) check(gptimer_del_timer(timer), "gptimer_del_timer");
        if (adc) check(adc_oneshot_del_unit(adc), "adc_oneshot_del_unit");
        if (summaries) vQueueDelete(summaries);
    };
    adc_oneshot_unit_init_cfg_t unit = {};
    unit.unit_id = ADC_UNIT_1;
    unit.ulp_mode = ADC_ULP_MODE_DISABLE;
    if (!check(adc_oneshot_new_unit(&unit, &adc), "adc_oneshot_new_unit")) { cleanup(); return; }
    adc_oneshot_chan_cfg_t channel = {};
    channel.atten = ADC_ATTEN_DB_12;
    channel.bitwidth = ADC_BITWIDTH_12;
    if (!check(adc_oneshot_config_channel(adc, kChannel, &channel), "adc channel")) { cleanup(); return; }
    gptimer_config_t config = {};
    config.clk_src = GPTIMER_CLK_SRC_DEFAULT;
    config.direction = GPTIMER_COUNT_UP;
    config.resolution_hz = 1000000;
    if (!check(gptimer_new_timer(&config, &timer), "gptimer_new_timer")) { cleanup(); return; }
    uint32_t resolution = 0;
    if (!check(gptimer_get_resolution(timer, &resolution), "gptimer_get_resolution") || resolution != 1000000) {
        ESP_LOGE(kTag, "Expected 1 MHz GPTimer resolution"); cleanup(); return;
    }
    summaries = xQueueCreate(4, sizeof(Summary));
    if (!summaries) { ESP_LOGE(kTag, "Summary queue allocation failed"); cleanup(); return; }
    if (xTaskCreate(log_task, "adc_summary", 6144, nullptr, 3, &logging_handle) != pdPASS ||
        xTaskCreate(sampling_task, "adc_sampling", 4096, nullptr, 10, &sampling_handle) != pdPASS) {
        ESP_LOGE(kTag, "Task allocation failed"); cleanup(); return;
    }
    gptimer_event_callbacks_t callbacks = {};
    callbacks.on_alarm = alarm_callback;
    if (!check(gptimer_register_event_callbacks(timer, &callbacks, sampling_handle), "register callback")) { cleanup(); return; }
    gptimer_alarm_config_t alarm = {};
    alarm.alarm_count = kPeriodUs;
    alarm.reload_count = 0;
    alarm.flags.auto_reload_on_alarm = true;
    if (!check(gptimer_set_alarm_action(timer, &alarm), "gptimer_set_alarm_action")) { cleanup(); return; }
    if (!check(gptimer_enable(timer), "gptimer_enable")) { cleanup(); return; }
    enabled = true;
    // This is a startup gate; all subsequent notifications come from GPTimer ISR.
    xTaskNotifyGive(sampling_handle);
}
