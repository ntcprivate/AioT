# ECG TinyML research bench

Latest telemetry/GUI review: [báo cáo sửa lỗi và kiểm thử board](firmware/esp32_ecg_tinyml_integrated/docs/telemetry_reliability_review.md).
Hai build IDF5.4.4 PASS; firmware body v2 / GUI2.0. Chưa flash, AI-live vẫn LOCKED;
CRC thực tế và 250Hz end-to-end: **PENDING HARDWARE VALIDATION**.

Project ESP-IDF5.4.4: `firmware/esp32_ecg_tinyml_integrated`.
Ứng dụng Windows: **`tools/ecg_monitor/Start_ECG_Monitor.bat`**.

Môi trường GUI riêng đã cài/kiểm thử. Máy mới chạy `tools/ecg_monitor/setup.bat`
trước, dùng Python3.13. DEMO hoạt động không cần ESP32; HARDWARE MONITOR cần
firmware telemetry protocol1 được người dùng nạp. Không tự flash/reset board.

- [Hướng dẫn ECG Monitor](tools/ecg_monitor/README.md)
- [Audit firmware, bằng chứng và các phần chưa hoàn thành](firmware/esp32_ecg_tinyml_integrated/docs/system_audit.md)
- [Giao thức USB Serial](firmware/esp32_ecg_tinyml_integrated/docs/telemetry_protocol.md)
- [Quy trình kiểm thử simulator, không kết nối cơ thể](firmware/esp32_ecg_tinyml_integrated/docs/bench_validation.md)
- [Kết quả Validation offline](tools/ecg_monitor/reports/offline_validation.json)

CNN golden vẫn12/12 trên host. Detector R chưa đạt tiêu chí nên **AI-live vẫn
LOCKED**, không xuất NORMAL/PVC/BPM giả. Component parity không thay cho xác
minh hệ thống trên hardware. Đây là nguyên mẫu nghiên cứu, không phải thiết bị
y tế; không thử trên cơ thể với phần cứng chưa được đánh giá cách ly/dòng rò.
