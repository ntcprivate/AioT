#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "sdkconfig.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"
#include "test_data/ecg_test_metadata.h"

extern const uint8_t model_start[] asm("_binary_ecg_cnn_int8_tflite_start");
extern const uint8_t model_end[] asm("_binary_ecg_cnn_int8_tflite_end");
extern const uint8_t samples_start[] asm("_binary_ecg_test_samples_int8_bin_start");
extern const uint8_t samples_end[] asm("_binary_ecg_test_samples_int8_bin_end");

namespace {
constexpr size_t kArenaBytes = CONFIG_ECG_ARENA_KIB * 1024;

void heap_log(const char* stage) {
    const uint32_t caps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
    printf("ECG_HEAP stage=%s free=%u minimum=%u largest=%u\n", stage,
           static_cast<unsigned>(heap_caps_get_free_size(caps)),
           static_cast<unsigned>(heap_caps_get_minimum_free_size(caps)),
           static_cast<unsigned>(heap_caps_get_largest_free_block(caps)));
}

bool verify_hash(const uint8_t* bytes, size_t length, const char* expected, const char* kind) {
    uint8_t digest[32];
    char hex[65];
    if (mbedtls_sha256(bytes, length, digest, 0) != 0) return false;
    for (int i = 0; i < 32; ++i) snprintf(hex + i * 2, 3, "%02x", digest[i]);
    hex[64] = '\0';
    const bool ok = strcmp(hex, expected) == 0;
    printf("ECG_HASH kind=%s sha256=%s status=%s\n", kind, hex, ok ? "PASS" : "FAILED");
    return ok;
}

bool valid_tensor(const TfLiteTensor* t, bool input) {
    if (!t || t->type != kTfLiteInt8 || !t->data.int8 || !t->dims) return false;
    const bool shape = input ? (t->dims->size == 3 && t->dims->data[0] == 1 &&
        t->dims->data[1] == 256 && t->dims->data[2] == 1 && t->bytes == 256) :
        (t->dims->size == 2 && t->dims->data[0] == 1 && t->dims->data[1] == 1 && t->bytes == 1);
    const float scale = input ? kInputScale : kOutputScale;
    const int zero = input ? kInputZero : kOutputZero;
    return shape && std::isfinite(t->params.scale) && t->params.scale > 0 &&
        fabsf(t->params.scale - scale) <= 1e-9f && t->params.zero_point == zero;
}
}  // namespace

extern "C" void app_main() {
    printf("ECG_BOOT firmware=step8_v1 idf=%s target=esp32 cpu_mhz=%d component=1.4.2\n",
           esp_get_idf_version(), CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ);
#if CONFIG_ESP_TFLITE_MICRO_USE_ESP_NN
    printf("ECG_CONFIG esp_nn=ENABLED_BUILD_OPTION actual_kernel_paths=NEEDS_VERIFICATION\n");
#else
    printf("ECG_CONFIG esp_nn=DISABLED_BUILD_OPTION\n");
#endif
    heap_log("before_init");
    const size_t model_bytes = model_end - model_start;
    if (model_bytes != kModelBytes || static_cast<size_t>(samples_end - samples_start) != kSampleCount * kSamplesPerBeat ||
        !verify_hash(model_start, model_bytes, kModelSha, "model") ||
        !verify_hash(samples_start, samples_end - samples_start, kSamplesSha, "samples")) {
        printf("ECG_ERROR stage=integrity\n"); return;
    }
    // Embedded read-only binary remains flash-mapped; no model-sized RAM copy.
    const tflite::Model* model = tflite::GetModel(model_start);
    printf("ECG_INIT stage=model_loaded bytes=%u\n", static_cast<unsigned>(model_bytes));
    if (model->version() != TFLITE_SCHEMA_VERSION) { printf("ECG_ERROR stage=schema\n"); return; }
    printf("ECG_INIT stage=schema_valid version=%u\n", static_cast<unsigned>(model->version()));
    static tflite::MicroMutableOpResolver<7> resolver;
    if (resolver.AddConv2D() != kTfLiteOk || resolver.AddExpandDims() != kTfLiteOk ||
        resolver.AddFullyConnected() != kTfLiteOk || resolver.AddLogistic() != kTfLiteOk ||
        resolver.AddMaxPool2D() != kTfLiteOk || resolver.AddMean() != kTfLiteOk ||
        resolver.AddReshape() != kTfLiteOk) { printf("ECG_ERROR stage=operator_registration\n"); return; }
    printf("ECG_INIT stage=operators_registered count=7\n");
    for (const auto* op : *model->operator_codes()) {
        printf("ECG_OPERATOR code=%d version=%d\n", static_cast<int>(op->builtin_code()), static_cast<int>(op->version()));
    }
    auto* arena = static_cast<uint8_t*>(heap_caps_aligned_alloc(16, kArenaBytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (!arena) { printf("ECG_ERROR stage=arena_allocation requested=%u\n", static_cast<unsigned>(kArenaBytes)); return; }
    printf("ECG_INIT stage=arena_allocated bytes=%u\n", static_cast<unsigned>(kArenaBytes));
    static tflite::MicroInterpreter interpreter(model, resolver, arena, kArenaBytes);
    if (interpreter.AllocateTensors() != kTfLiteOk) {
        printf("ECG_ERROR stage=AllocateTensors hint=check_kernel_quantization_or_arena\n"); return;
    }
    printf("ECG_ARENA allocated=%u used=%u\n", static_cast<unsigned>(kArenaBytes),
           static_cast<unsigned>(interpreter.arena_used_bytes()));
    if (interpreter.inputs_size() != 1 || interpreter.outputs_size() != 1) {
        printf("ECG_ERROR stage=io_count\n"); return;
    }
    TfLiteTensor* input = interpreter.input(0);
    TfLiteTensor* output = interpreter.output(0);
    if (!valid_tensor(input, true) || !valid_tensor(output, false)) { printf("ECG_ERROR stage=io_validation\n"); return; }
    printf("ECG_INIT stage=input_valid dtype=int8 shape=1,256,1 scale=%.12g zero=%d\n", input->params.scale, static_cast<int>(input->params.zero_point));
    printf("ECG_INIT stage=output_valid dtype=int8 shape=1,1 scale=%.12g zero=%d\n", output->params.scale, static_cast<int>(output->params.zero_point));
    printf("ECG_INIT stage=interpreter_ready threshold=%.9f samples=%u\n", kThreshold, static_cast<unsigned>(kSampleCount));
    heap_log("after_init");
    bool all_classes_match = true;
    bool all_exact = true;
    for (size_t id = 0; id < kSampleCount; ++id) {
        const uint8_t* source = samples_start + id * kSamplesPerBeat;
        memcpy(input->data.int8, source, kSamplesPerBeat);
        if (memcmp(input->data.int8, source, kSamplesPerBeat) != 0) { printf("ECG_ERROR stage=input_copy\n"); return; }
        for (int warm = 0; warm < 3; ++warm) {
            memcpy(input->data.int8, source, kSamplesPerBeat);
            if (interpreter.Invoke() != kTfLiteOk) { printf("ECG_ERROR stage=warmup sample_id=%u\n", static_cast<unsigned>(id)); return; }
            vTaskDelay(1);
        }
        int64_t timings[CONFIG_ECG_REPEATS];
        int first_code = 0;
        bool consistent = true;
        for (int run = 0; run < CONFIG_ECG_REPEATS; ++run) {
            memcpy(input->data.int8, source, kSamplesPerBeat);
            if (memcmp(input->data.int8, source, kSamplesPerBeat) != 0) {
                printf("ECG_ERROR stage=input_copy sample_id=%u\n", static_cast<unsigned>(id)); return;
            }
            const int64_t begin = esp_timer_get_time();
            const TfLiteStatus status = interpreter.Invoke();
            const int64_t duration = esp_timer_get_time() - begin;
            if (status != kTfLiteOk) { printf("ECG_ERROR stage=invoke sample_id=%u\n", static_cast<unsigned>(id)); return; }
            timings[run] = duration;
            const int code = output->data.int8[0];
            if (run == 0) first_code = code;
            consistent = consistent && code == first_code;
            vTaskDelay(1);  // Outside timed region; allow idle/watchdog service.
        }
        // Emit measured values after Invoke timing, never inside timed region.
        for (int run = 0; run < CONFIG_ECG_REPEATS; ++run)
            printf("ECG_TIME sample_id=%u run=%d latency_us=%lld\n", static_cast<unsigned>(id), run, static_cast<long long>(timings[run]));
        std::sort(timings, timings + CONFIG_ECG_REPEATS);
        double total = 0;
        for (auto duration : timings) total += duration;
        const double median = (CONFIG_ECG_REPEATS % 2) ? timings[CONFIG_ECG_REPEATS/2] :
            (timings[CONFIG_ECG_REPEATS/2 - 1] + timings[CONFIG_ECG_REPEATS/2]) / 2.0;
        printf("ECG_LATENCY sample_id=%u count=%d min=%lld mean=%.3f median=%.3f p95=%lld max=%lld\n",
            static_cast<unsigned>(id), CONFIG_ECG_REPEATS, static_cast<long long>(timings[0]), total/CONFIG_ECG_REPEATS,
            median, static_cast<long long>(timings[(CONFIG_ECG_REPEATS * 95 + 99)/100 - 1]),
            static_cast<long long>(timings[CONFIG_ECG_REPEATS - 1]));
        const float score = (first_code - output->params.zero_point) * output->params.scale;
        const int prediction = score >= kThreshold;
        const auto& golden = kGolden[id];
        const int lsb = std::abs(first_code - golden.output);
        const bool label_ok = prediction == golden.predicted;
        all_classes_match = all_classes_match && label_ok && consistent;
        all_exact = all_exact && lsb == 0;
        printf("ECG_RESULT sample_id=%u dataset_index=%d record=%s true=%d output_int8=%d score=%.9f predicted=%d python_int8=%d lsb=%d input_match=1 stable=%d status=%s\n",
            static_cast<unsigned>(id), golden.dataset_index, golden.record, golden.label, first_code, score, prediction,
            golden.output, lsb, consistent, !label_ok || !consistent ? "FAILED" : lsb ? "NEEDS_REVIEW" : "EXACT_MATCH");
        heap_log("after_sample");
    }
    heap_log("final");
    printf("ECG_DONE samples=%u status=%s\n", static_cast<unsigned>(kSampleCount),
           !all_classes_match ? "FAILED" : all_exact ? "EXACT_MATCH" : "NEEDS_REVIEW");
}
