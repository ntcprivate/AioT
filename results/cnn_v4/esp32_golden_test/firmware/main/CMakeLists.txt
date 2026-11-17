idf_component_register(SRCS "main.cpp" "single_round_conv.cpp" "single_round_fc.cpp"
    INCLUDE_DIRS "." REQUIRES esp_timer esp_system heap mbedtls esp-tflite-micro
    EMBED_FILES "assets/v4_model.tflite" "assets/v4_inputs.bin" "assets/v4_raw.bin")
target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)
