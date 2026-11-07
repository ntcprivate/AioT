if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/test_data/ecg_test_samples_int8.bin")
    message(FATAL_ERROR
        "Missing ECG test samples: ${CMAKE_CURRENT_LIST_DIR}/test_data/ecg_test_samples_int8.bin"
    )
endif()

idf_component_register(
    SRCS "main.cpp"
    INCLUDE_DIRS "."
    REQUIRES esp_timer esp_system heap mbedtls esp-tflite-micro
    EMBED_FILES
        "model/ecg_cnn_int8.tflite"
        "test_data/ecg_test_samples_int8.bin"
)

target_compile_features(${COMPONENT_LIB} PUBLIC cxx_std_17)