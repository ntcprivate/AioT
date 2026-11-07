#pragma once
#include "esp_err.h"

// Call once from app_main before starting acquisition. Pins default LOW.
esp_err_t alert_init();
// Task-context, nonblocking latest-state requests; no task is created per call.
// During startup self-test, the latest request is applied after completion.
esp_err_t alert_set_normal();
esp_err_t alert_set_pvc();
esp_err_t alert_set_invalid();
