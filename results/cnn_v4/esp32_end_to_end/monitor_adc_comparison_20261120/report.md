# Đối chiếu UART gốc — ECG Monitor — ADC V4

Chỉ đọc capture đã lưu; không mở COM3, flash/reset, đo mới, chạy CNN, benchmark/replay hay sửa firmware/GUI. Script python/audit_v4_monitor_saved_adc.py dùng parser/session và biểu đồ Qt offscreen hiện hành; độc lập giải mã byte và CRC để so sánh. Đây là phát lại dữ liệu vào GUI để chẩn đoán phần mềm, không phải phép thử ECG replay trên ESP32.

## Kết luận

Không tìm thấy lỗi ECG Monitor tự tạo/clamp4095 hoặc đảo bit lead-off trong các capture kiểm tra. 4095 tồn tại trong UART CRC hợp lệ trước khi vào ứng dụng. Xác nhận ADC raw chạm toàn thang; chưa xác định được điện áp OUT hay nguyên nhân phần cứng cụ thể từ raw counts.

| Capture | Mẫu được giải mã | Bằng4095 | LO+HIGH | LO-HIGH | R/classified cuối hoặc max |
|---|---:|---:|---:|---:|---|
| board_runs/ADC_V4_20261120_173711/uart_raw.log |30144|27348|5598|139|0/0|
| captures/20261120T120914Z_5a1c16ff.bin |61568|35064|33505|26474|0/0|
| captures/20261120T110601Z_7d859e74.bin |41472|15201|8541|3633|34/31 tích lũy|

Capture thứ hai là file đã đóng bắt đầu khoảng19:09 giờ Việt Nam, boot c7a1f7ed; có LEADS_OFF265 và ADC_SATURATION216 bản tin status. Các mức LO không cố định: (LO+,LO-)=(0,0):27967 mẫu; (1,0):7127; (0,1):96; (1,1):26378. Không thể kết luận cả hai luôn HIGH chỉ từ nhãn LEADS_OFF. Đây là logic level ESP32 đọc được, không phải điện áp đo bằng thiết bị độc lập.

Số30144 ở dòng đầu bao gồm mọi sample frame hoàn chỉnh trong UART. Báo cáo phiên17:37 trước đây dùng30080 mẫu thuộc khoảng measurement sau status khởi đầu; thêm64 mẫu trước mốc đó không thay đổi kết quả cũ. Không ghi đè các artifact cũ.

## Byte gốc và đường hiển thị

- Ví dụ capture19:09: sample92051, timestamp368632334µs, packed record `e0280100ff0f01`: delta LE, ADC bytes `ff0f` =4095, flags01=LO+HIGH/LO-LOW. Frame CRC hợp lệ. comparison.json lưu line273 để truy vết.
- protocol.py:46 giải mã `<IHB`; adc giữ nguyên0..4095. Giá trị65535 chỉ hợp lệ với ADC-error bit, được session chuyển thành NaN, không chuyển thành4095.
- session.py:69 diễn giải bit0=LO+, bit1=LO-, rồi ADC-error, gap, saturation. session.py:73 đưa raw vào buffer, không clamp.
- app.py:224 truyền raw buffer trực tiếp cho curve. Giá trị session so với mẫu giải mã:0 sai khác trên cả3file. Curve Raw cuối buffer so với session: khớp trên cả3file. Chế độ filtered preview chỉ đổi đường xem trước, không sửa UART hay gửi tín hiệu vào CNN.
- Không phát hiện schema reject trên các frame CRC hợp lệ. StreamParser thực tế: file17:37 và19:09 không có CRC/schema/frame/sequence error; file18:06 có38CRC reject. Các phép đếm theo splitlines còn thấy1 fragment cuối chưa kết thúc mỗi file; không coi fragment đó là frame hoàn chỉnh và không sửa nó. Frame lỗi bị bỏ, không được lấp bằng4095.

## Firmware và GUI diễn giải trạng thái

main/main.cpp:229 đọc adc_oneshot_read ADC1_CHANNEL_6=GPIO34; dòng236–237 đọc GPIO lead-off. main/lead_off.h:7–10: LO+GPIO27, LO-GPIO26, activeHIGH, phép OR. main.cpp:363–364 cấu hình12bit/12dB. Đây là raw ADC, không phải mV đã hiệu chuẩn.

pipeline_observe (pipeline.cpp): ưu tiên lead-off, ADC error, raw<=16 hoặc>=4079, rồi lỗi khoảng mẫu. signal.cpp:25 cũng loại block có mẫu rail. Vì thế LEADS_OFF và ADC_SATURATION có thể luân phiên dù cả hai tồn tại trong cùng giai đoạn. LO LOW không chứng minh morphology ECG tốt.

Monitor giữ trạng thái invalid đến khi firmware gửi quality mới hợp lệ; do đó nhãn cảnh báo có thể chưa hết ngay khi một mẫu LO trở lạiLOW. Đây là latch/recovery, không phải parser biến LOW thànhHIGH. Cần xem cả flags hiện tại, reason, quality_valid và quality_t_us.

## Inference và nguyên nhân tiếp theo

Hai capture17:37 và19:09: R0/inference0, dữ liệu bị gate chặn. Capture18:06 bắt đầu đã có25peak/24classified và tăng lên34/31: chỉ thêm9candidate,7nhịp công bố; không nhầm31 là số inference mới trong file này. Phân tích trước tại analog_interruption_analysis_20261120 chỉ ra các khoảng được công bố có waveform tuần hoàn đáng nghi, không đủ bằng chứng ECG/PVC thật.

Nguyên nhân cần kiểm tra tiếp là đầu vào analog/bias/common-mode, dây OUT/GND, tiếp xúc cáp/điện cực hoặc module AD8232, không phải lỗi GUI clamp4095. UART không thể phân biệt chắc chắn module bão hòa, dây sai/đứt hay ADC bị đưa ngoài dải. Đối chứng trên bench không nối người bằng nguồn ECG mô phỏng phù hợp hoặc cáp/module tốt đã biết; không bỏ gate hay đổi CNN/detector. Chưa cần thu thêm để trả lời câu hỏi ứng dụng hay dữ liệu gốc.

Các số và hash nguồn ở comparison.json. Không tuyên bố toàn bộ ứng dụng không còn mọi lỗi khác; kết luận giới hạn ở đường raw ADC/flags/plot đã kiểm chứng.
