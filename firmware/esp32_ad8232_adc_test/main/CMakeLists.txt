idf_component_register(
    SRCS "main.cpp" "alert.cpp"
    INCLUDE_DIRS "."
    REQUIRES esp_adc esp_driver_gpio esp_driver_gptimer esp_timer
)
