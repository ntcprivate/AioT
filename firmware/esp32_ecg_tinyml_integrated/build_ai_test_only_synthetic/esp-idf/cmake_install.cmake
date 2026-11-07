# Install script for directory: C:/esp/v5.4.4/esp-idf

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "C:/Program Files (x86)/esp32_ecg_tinyml_integrated")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set path to fallback-tool for dependency-resolution.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "C:/Espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121/xtensa-esp-elf/bin/xtensa-esp32-elf-objdump.exe")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/xtensa/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_gpio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_pm/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/mbedtls/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/bootloader/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esptool_py/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/partition_table/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_app_format/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_bootloader_format/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/app_update/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_partition/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/efuse/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/bootloader_support/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_mm/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/spi_flash/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_system/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_common/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_rom/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/hal/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/log/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/heap/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/soc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_security/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_hw_support/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/freertos/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/newlib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/pthread/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/cxx/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_timer/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_gptimer/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_ringbuf/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_uart/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/app_trace/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_event/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/nvs_flash/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_pcnt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_spi/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_mcpwm/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_ana_cmpr/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_i2s/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/sdmmc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_sdmmc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_sdspi/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_sdio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_dac/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_rmt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_tsens/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_sdm/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_i2c/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_ledc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_parlio/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_usb_serial_jtag/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/driver/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_phy/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_vfs_console/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/vfs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/lwip/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_netif_stack/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_netif/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/wpa_supplicant/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_coex/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_wifi/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_gdbstub/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/bt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/unity/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/cmock/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/console/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/http_parser/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp-tls/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_adc/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_isp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_cam/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_psram/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_jpeg/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_ppa/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_driver_touch_sens/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_eth/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_hal_ieee802154/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_hid/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/tcp_transport/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_http_client/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_http_server/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_https_ota/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_https_server/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_lcd/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/protobuf-c/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/protocomm/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/esp_local_ctrl/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/espcoredump/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/wear_levelling/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/fatfs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/idf_test/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/ieee802154/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/json/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/mqtt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/nvs_sec_provider/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/openthread/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/perfmon/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/rt/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/spiffs/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/ulp/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/usb/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/wifi_provisioning/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/espressif__esp-nn/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/espressif__esp-tflite-micro/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/main/cmake_install.cmake")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
if(CMAKE_INSTALL_LOCAL_ONLY)
  file(WRITE "D:/Code Part Two/AIoT/firmware/esp32_ecg_tinyml_integrated/build_ai_test_only_synthetic/esp-idf/install_local_manifest.txt"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")
endif()
