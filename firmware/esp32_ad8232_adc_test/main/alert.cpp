#include "alert.h"
#include <cstdio>
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

namespace {
constexpr gpio_num_t kLed = GPIO_NUM_23;
constexpr gpio_num_t kBuzzer = GPIO_NUM_25;
constexpr TickType_t kOn = pdMS_TO_TICKS(150);
constexpr TickType_t kOff = pdMS_TO_TICKS(350);
static_assert(kOn > 0 && kOff > 0, "Tick rate too low for alert timing");
enum class State { Invalid, Normal, Pvc };
QueueHandle_t commands = nullptr;

void message(const char* text) {
    // Same stdout lock used by ADC_BUFFER logger; no fragmented test log.
    flockfile(stdout);
    fprintf(stdout, "ALERT_TEST: %s\n", text);
    fflush(stdout);
    funlockfile(stdout);
}

esp_err_t outputs(bool led, bool buzzer) {
    // Always attempt both writes, including on error shutdown.
    const esp_err_t a = gpio_set_level(kLed, led ? 1 : 0);
    const esp_err_t b = gpio_set_level(kBuzzer, buzzer ? 1 : 0);
    return a != ESP_OK ? a : b;
}

void fault(esp_err_t error) {
    const esp_err_t off_error = outputs(false, false);
    flockfile(stdout);
    fprintf(stdout, "ALERT_TEST: GPIO ERROR %s shutdown=%s\n",
            esp_err_to_name(error), esp_err_to_name(off_error));
    fflush(stdout);
    funlockfile(stdout);
    // Fail latched: never drive outputs again until reboot. ADC task continues.
    while (true) vTaskDelay(portMAX_DELAY);
}

void apply(bool led, bool buzzer) {
    const esp_err_t error = outputs(led, buzzer);
    if (error != ESP_OK) fault(error);
}

void alert_task(void*) {
    message("LED NORMAL TEST");
    apply(true, false);
    vTaskDelay(pdMS_TO_TICKS(2000));
    apply(false, false);
    message("LED BLINK + BUZZER TEST");
    for (int pulse = 0; pulse < 6; ++pulse) {
        apply(true, true);
        vTaskDelay(kOn);
        apply(false, false);
        vTaskDelay(kOff);
    }
    apply(false, false);
    message("SELF TEST COMPLETE");

    State state = State::Invalid;
    bool phase_on = false;
    TickType_t phase_started = xTaskGetTickCount();
    while (true) {
        State requested;
        const TickType_t duration = phase_on ? kOn : kOff;
        const TickType_t elapsed = xTaskGetTickCount() - phase_started;
        const TickType_t wait = state == State::Pvc ?
            (elapsed >= duration ? 0 : duration - elapsed) : portMAX_DELAY;
        if (xQueueReceive(commands, &requested, wait) == pdTRUE) {
            // Repeated PVC requests must not restart/extend the ON phase.
            if (requested == state) continue;
            state = requested;
            phase_on = state == State::Pvc;
            phase_started = xTaskGetTickCount();
            apply(state == State::Normal || phase_on, phase_on);
        } else if (state == State::Pvc) {
            phase_on = !phase_on;
            phase_started = xTaskGetTickCount();
            apply(phase_on, phase_on);
        }
    }
}

esp_err_t request(State state) {
    if (!commands) return ESP_ERR_INVALID_STATE;
    return xQueueOverwrite(commands, &state) == pdPASS ? ESP_OK : ESP_FAIL;
}
} // namespace

esp_err_t alert_init() {
    if (commands) return ESP_ERR_INVALID_STATE;
    // Preload output latches LOW before enabling output direction.
    esp_err_t error = outputs(false, false);
    if (error != ESP_OK) return error;
    gpio_config_t config = {};
    config.pin_bit_mask = (1ULL << kLed) | (1ULL << kBuzzer);
    config.mode = GPIO_MODE_OUTPUT;
    config.pull_up_en = GPIO_PULLUP_DISABLE;
    config.pull_down_en = GPIO_PULLDOWN_DISABLE;
    config.intr_type = GPIO_INTR_DISABLE;
    error = gpio_config(&config);
    if (error != ESP_OK) return error;
    error = outputs(false, false);
    if (error != ESP_OK) return error;
    commands = xQueueCreate(1, sizeof(State));
    if (!commands) return ESP_ERR_NO_MEM;
    if (xTaskCreate(alert_task, "alert_control", 3072, nullptr, 2, nullptr) != pdPASS) {
        vQueueDelete(commands);
        commands = nullptr;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t alert_set_normal() { return request(State::Normal); }
esp_err_t alert_set_pvc() { return request(State::Pvc); }
esp_err_t alert_set_invalid() { return request(State::Invalid); }
