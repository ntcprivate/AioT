idf_component_register(SRCS "main.cpp" "pipeline.cpp" "model.cpp" "signal.cpp" "trace_transport.cpp" "single_round_conv.cpp" "single_round_fc.cpp" "telemetry.cpp"
    INCLUDE_DIRS "."
    REQUIRES esp_adc esp_driver_gpio esp_driver_gptimer esp_timer esp_system esp_hw_support heap mbedtls esp-tflite-micro
    EMBED_FILES "model/ecg_cnn_int8.tflite" "test_data/ecg_test_samples_int8.bin")
target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
# Effective kernel log is derived from the actual TFLM target's compiler options
# in the project CMakeLists, after all components have been configured.
