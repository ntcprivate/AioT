# Hợp nhất giao diện AI ECG

Chỉ còn **AI ECG CLASSIFICATION**, chữ lớn **NORMAL (N)**, **PVC (V)** hoặc
**UNKNOWN**. Có PVC probability, CNN latency, R-peak count, total classified
beats, tuổi prediction và lý do. Dòng nhỏ: “Research prototype — Not for medical
diagnosis”. Đã bỏ panel RESEARCH AI, các dòng phân loại/AI mode trùng lặp và lựa
chọn VALIDATED AI TEST trong GUI.

Kết quả lấy duy nhất từ object `research` / RESEARCH_SHADOW hợp lệ. Không dùng
classification của kênh cũ làm dữ liệu thay thế. Các cờ AI-live, r_validated,
ai_validated hoặc F1 không chặn kết quả nghiên cứu. Giữ nguyên output/xác suất
CNN, kể cả các golden N→PVC và V→NORMAL sai nhãn thật. Source, CRC, golden
readiness, quality, lead-off, clipping, sample gap, TTL và epoch kết nối vẫn
được kiểm tra. Stop/Disconnect/Reconnect không khôi phục prediction cũ.

## File sửa/thêm và phần dọn

- `ecg_monitor/app.py`: hợp nhất panel, gỡ logic hiển thị AI cũ, import `json`,
  biến `filter_state` chỉ được gán nhưng không dùng; chỉnh xuống dòng tránh cắt
  lý do ở panel hẹp. Không sửa đường vẽ ECG hoặc xử lý UART.
- `ecg_monitor/research.py`: decoder/display của kênh Shadow độc lập trạng thái
  nghiệm thu cũ. Thay thông báo chung NO_RESEARCH_TELEMETRY bằng trạng thái rõ:
  chờ AI telemetry, status timeout, firmware không gửi AI, hoặc lỗi tín hiệu.
  Capture đã lưu có object research đầy đủ; leads-off được báo LEADS_OFF.
- `gui_research_board_smoke.py`: cập nhật API panel mới, output QA chuyển sang
  thư mục này để không ghi đè bằng chứng hardware của giai đoạn trước. Không
  chạy script mở COM trong lượt sửa này.
- `tests/test_gui.py`, `tests/test_research_shadow.py`, `tests/test_telemetry_fix.py`:
  cập nhật kỳ vọng giao diện; thêm `tests/test_ai_unification.py` cho một panel,
  output sai nhãn vẫn hiển thị, tính độc lập với cờ nghiệm thu, lý do thiếu
  telemetry và bố cục.
- `README.md`: hướng dẫn hai nguồn DEMO/HARDWARE và panel hợp nhất.

**Không xóa file.** Không cần dọn cache/build; giữ training, dataset, model,
golden/evaluation, TEST_ONLY/Synthetic, CSV, raw capture và báo cáo cũ. Hàm
`valid_classification` trong session còn phục vụ CSV/kênh chính thức nên giữ
lại, chỉ bỏ đường gọi trùng lặp từ GUI. Backup trước sửa ở `before/`.

## Kiểm tra

**44 test PASS** liên quan GUI, decoder, protocol và chuyển trạng thái. Kiểm tra
NORMAL/PVC và xác suất bằng output golden thật đã lưu; kiểm tra fixture sai nhãn
vẫn hiện nguyên kết quả. Replay capture UART có sẵn cho UNKNOWN/LEADS_OFF, CRC
không lỗi; không mở COM hoặc suy luận CNN mới. Không chạy benchmark, regression
toàn dự án, train, build/flash firmware hoặc push GitHub.

Ảnh `reference_normal.png` / `reference_pvc.png` là **GUI QA replay output golden
đã lưu**, có banner phân biệt, không phải đo mới trên ESP32. Ảnh
`recorded_uart_invalid.png` dùng capture UART đã lưu. Không tạo prediction giả
để thay thế tín hiệu INVALID. Chưa thử lại end-to-end analog trên board trong
lượt GUI này; không suy diễn test GUI thành accuracy hoặc nghiệm thu y tế.

## Chạy

Đóng cửa sổ ECG Monitor cũ rồi mở `tools/ecg_monitor/Start_ECG_Monitor.bat` →
**HARDWARE MONITOR** → **COM3** → **Connect** → **Start Monitoring**. Với firmware
RESEARCH_SHADOW hiện có, kết quả hợp lệ sẽ hiện trực tiếp; leads-off/invalid/hết
hạn/mất kết nối hiện UNKNOWN và lý do. Nếu firmware không gửi `research`, hiện
FIRMWARE AI TELEMETRY UNAVAILABLE, không dựng kết quả từ kênh khác.

Danh sách test, kết quả và file sửa có trong `tests.json`, `tests.log`,
`results.json`. Các báo cáo lịch sử không bị viết lại.
