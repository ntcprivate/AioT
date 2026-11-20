set(common "single_round_conv.cpp" "single_round_fc.cpp")
if(ECG_EXPERIMENT_MODE MATCHES "^BENCH_")
set(sources "benchmark.cpp" ${common})
set(assets "assets/v4_raw.bin" "test_data/ecg_test_samples_int8.bin")
if(ECG_EXPERIMENT_MODE STREQUAL "BENCH_FP32")
list(APPEND assets "model/ecg_cnn_v4_fp32.tflite")
else()
list(APPEND assets "model/ecg_cnn_int8.tflite")
endif()
else()
set(sources "pipeline.cpp" "model.cpp" "signal.cpp" "trace_transport.cpp" "telemetry.cpp" "ai_test_only.cpp" ${common})
if(ECG_EXPERIMENT_MODE STREQUAL "REPLAY")
list(APPEND sources "replay_main.cpp")
else()
list(APPEND sources "main.cpp")
endif()
set(assets "model/ecg_cnn_int8.tflite" "test_data/ecg_test_samples_int8.bin")
if(ECG_EXPERIMENT_MODE STREQUAL "REPLAY")
list(APPEND assets "assets/${ECG_REPLAY_RECORD}.bin")
endif()
endif()
idf_component_register(SRCS ${sources} INCLUDE_DIRS "."
REQUIRES esp_adc esp_driver_gpio esp_driver_gptimer esp_driver_uart esp_timer esp_system esp_hw_support esp_app_format heap mbedtls esp-tflite-micro EMBED_FILES ${assets})
target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
V4_REPLAY=$<STREQUAL:${ECG_EXPERIMENT_MODE},REPLAY>
V4_BENCH_FLOAT=$<STREQUAL:${ECG_EXPERIMENT_MODE},BENCH_FP32>
V4_REPLAY_INCART=$<STREQUAL:${ECG_REPLAY_RECORD},INCART_I08>
V4_REPLAY_PVC=$<STREQUAL:${ECG_REPLAY_RECORD},INCART_PVC_V1>
ECG_HOST_TEST=1)
