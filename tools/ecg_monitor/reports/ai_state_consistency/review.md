# Đồng bộ trạng thái AI trong ECG Monitor

Nguyên nhân: header đọc FSM `status.state` của firmware (WAITING/LOCKED), còn
panel phân loại đọc RESEARCH_SHADOW, nên hai nhãn có thể trái nhau.

`update_status()` nay chỉ gọi `Session.research_display()` một lần rồi truyền
cùng snapshot cho header và panel. Không để FSM/cờ nghiệm thu AI-live cũ ghi
đè kết quả nghiên cứu hợp lệ.

| Snapshot AI | Header | Phân loại |
|---|---|---|
| Inference hợp lệ, còn hạn | AI LIVE | NORMAL (N) hoặc PVC (V) |
| Đang chờ prediction mới | WAITING | UNKNOWN |
| Lead-off | LEADS_OFF | UNKNOWN |
| Signal invalid | SIGNAL_INVALID | UNKNOWN |
| Prediction hết hạn | PREDICTION_STALE | UNKNOWN |
| Mất kết nối/timeout | DISCONNECTED | UNKNOWN |

Giữ trạng thái DEMO/SYNTHETIC_TEST/SELF_TEST và lỗi hệ thống thực khi phù hợp;
không lấy NORMAL/PVC của kênh cũ làm dữ liệu thay thế. Xác suất và latency được
xóa khi UNKNOWN; bộ đếm tổng vẫn giữ ý nghĩa số liệu phiên/firmware.

Sửa `ecg_monitor/app.py`, `tests/test_ai_unification.py`, `tests/test_gui.py`.
**26 test GUI/state PASS**, gồm chuyển WAITING→AI LIVE, N/PVC, inference sai nhãn
tham chiếu, TTL, lead-off/noise, timeout, disconnect/reconnect và kiểm tra chỉ
resolve một snapshot. Không chạy benchmark, toàn bộ regression, CNN, COM hoặc
build/flash. Không sửa firmware, detector, model hay threshold.

Đóng GUI cũ rồi mở lại `Start_ECG_Monitor.bat` → HARDWARE MONITOR → COM3 →
Connect → Start Monitoring. Test này dùng fixture/output đã lưu, không phải
kiểm thử mới trên board hoặc trên người. Backup trước sửa nằm trong `before/`;
chi tiết test ở `tests.log`, `results.json`.
