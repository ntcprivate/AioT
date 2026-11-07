# ESP32 AI TEST_ONLY — kết quả bench

Ngày UTC: 2026-11-06T13:41:28.837150+00:00. ESP-IDF v5.4.4, ESP32-D0WD-V3 rev3.1, 240 MHz; COM3 CP210x; MAC b0:3f:d3:51:8b:ec.

Người dùng đã xác nhận bàn thử không có người kết nối và cho phép flash/reset. AI-live vẫn **LOCKED**. Không kích hoạt cảnh báo PVC bằng dữ liệu tham chiếu.

## Thay đổi

- `main/ai_test_only.cpp/.h`, `main/test_only/*`: 12 golden cũ + 8 input FC14 duy nhất; 3 warm-up + 30 lần đo/ca. Kiểm tra byte input sau preprocessing và output code chính xác; không sửa reference.
- `main/Kconfig.projbuild`, `main/CMakeLists.txt`: TEST_ONLY mặc định OFF, fixture chỉ nhúng khi bật. Hai sdkconfig/build TEST_ONLY riêng trong debug; cấu hình thường giữ TEST_ONLY OFF.
- `main/model.cpp/.h`: callback đo golden và đọc arena; log rõ cả hai đường FC single rounding đã có từ 2B. `main/pipeline.cpp`: chạy bài thử trong task AI hiện hữu, giữ khóa live.
- `main/telemetry.cpp/.h`: getter chỉ đọc atomic/clock snapshot; không đổi UART v2, ADC, queue, GPIO, detector, preprocessing hoặc FSM. CMake gốc chỉ sửa mô tả kernel cho đúng code đã có.
- `tools/ecg_monitor/generate_ai_test_only_fixtures.py`, `run_ai_test_only_bench.py`, `summarize_ai_test_only.py`, `tests/test_ai_test_only.py`: fixture, flash/capture/restore có timeout và kiểm chứng log. SDK config sinh lại chỉ thêm tùy chọn TEST_ONLY mặc định OFF.

## Lỗi tìm thấy và sửa

Lượt đầu: cả 20 ca output EXACT nhưng stress FAIL. Burst báo cáo case 0–11 làm task TX ưu tiên thấp không tiêu thụ kịp FIFO 6 gói: ADC rơi 4 gói/128 mẫu, Synthetic rơi 5 gói/160 mẫu. Gaps đầu tiên xuất hiện sau case 11 trong cả hai log; ADC missed_est=0. Đây là mất dữ liệu telemetry, không phải mất nhịp timer. Bằng chứng giữ nguyên ở `debug/esp32_ai_test_only/attempt1/` và `first_attempt_drop_evidence.json`.

Sửa riêng TEST_ONLY: nhường task 300 ms sau mỗi dòng CASE, ngoài khoảng đo. Không tăng queue, không giảm lấy mẫu, không dừng telemetry. Kết quả lượt lại bên dưới kiểm chứng tác động của pacing.

Sao lưu toàn flash ở baud cao bị timeout lặp tại 221.184 byte; vùng 0x30000 cũng dừng sau 24.576 byte. Đọc vùng nhỏ ở 115200 thành công, mỗi vùng được esptool xác minh MD5. Chưa đủ bằng chứng quy nguyên nhân vật lý cho UART/flash. Đã sao lưu chính xác vùng 0–0x70000, bao phủ mọi sector được hai image ghi; phần còn lại không bị ghi.

## HOST và build

68 regression tests PASS; 10 test kiểm chứng log chạy lại PASS. Bao gồm dữ liệu thiếu ký tự, thiếu DONE/case, duplicate, sai code/SHA và lỗi telemetry giả lập: đều bị từ chối. 20 fixture preprocessing và TensorFlow EXACT; bài FC14 host kiểm tra đủ 16 operator/8 input. Các số parity 9.425/9.425 và 33.586/33.586 là bằng chứng đã lưu từ 2B, không chạy lại toàn corpus trong nhiệm vụ này.

| Build | Bytes | TEST_ONLY | Synthetic | AI-live |
|---|---:|---|---|---|
| normal_adc | 317808 | False | False | LOCKED |
| normal_synthetic | 316368 | False | True | LOCKED |
| test_adc | 348576 | True | False | LOCKED |
| test_synthetic | 346816 | True | True | LOCKED |

Bốn cấu hình build thành công; SHA image/ELF trong JSON. Hai bản TEST_ONLY đã flash và đối chiếu SHA ELF nhận từ board. Bản normal ADC/Synthetic mới chỉ build hồi quy, không flash riêng. Firmware gốc trước thử được khôi phục và đo lại bên dưới.

## ESP32 HARDWARE — lượt sau pacing

| Phép đo | ADC thật + reference | Synthetic + reference |
|---|---:|---:|
| Trạng thái | PASS | PASS |
| Golden / FC14 | 12/12 + 8/8 EXACT | 12/12 + 8/8 EXACT |
| Inference mean / µs | 81001.057 | 81046.158 |
| Inference p95 / µs | 81359 | 81380 |
| Inference max / µs | 81379 | 81415 |
| Preprocessing mean / µs | 2306.143 | 2305.855 |
| Preprocessing p95 / µs | 2349 | 2349 |
| Preprocessing max / µs | 2772 | 2875 |
| Arena used / bytes | 6124 | 6124 |
| Heap internal free / bytes | 161104 | 167356 |
| Heap internal minimum since boot / bytes | 152360 | 158520 |
| Heap largest free block / bytes | 110592 | 110592 |
| AI stack minimum free / bytes | 7600 | 7704 |
| ADC attempts trong bài thử | 17243 | 17303 |
| Acquisition Hz (buffer cuối) | 250.000000 | 250.000000 |
| ADC errors | 0 | 0 |
| Missed samples | 0 | 0 |
| Late counter | 11 | 20 |
| TX queue drops | 0 | 0 |
| Thời gian stress / µs | 68993430 | 69235024 |
| CRC lỗi | 0 | 0 |
| Mẫu thiếu trên host | 0 | 0 |
| Gói thiếu | 0 | 0 |
| Synthetic pattern lỗi | 0 | 0 |
| Mẫu nhận trên host | 18496 | 18560 |
| Hz từ timestamp toàn capture | 250.0 | 250.0000134705541 |
| dt nhỏ nhất / µs | 2843 | 2813 |
| dt lớn nhất / µs | 5158 | 5187 |
| dt p95 / µs | 4000 | 4000 |
| Khoảng dt lệch >500 µs | 26 | 42 |

600 inference và 600 preprocessing được đo mỗi cấu hình; 60 warm-up kiểm tra exact nhưng không đưa vào latency. Preprocessing = z-score + quantization, không gồm copy fixture. Thời gian Invoke gồm ảnh hưởng lịch task/ngắt; chưa đo CPU utilization. Arena cấp 65.536 byte, used theo TFLM. Stack watermark tính byte theo ESP-IDF; heap minimum tính từ boot. Late là trễ lịch lấy mẫu theo code hiện hữu, khác missed; không tuyên bố không có jitter.

## Từng ca trên board ADC

| ID | Record | Nhãn | Code TF / ESP32 | P(PVC) | Dự đoán | So nhãn thật | Exact |
|---|---|---|---|---:|---|---|---|
| golden0 | 115 | N | -126 / -126 | 0.007812500 | NORMAL | đúng | PASS |
| golden1 | 233 | N | 50 / 50 | 0.695312500 | PVC | sai đã có ở reference | PASS |
| golden2 | 214 | V | -66 / -66 | 0.242187500 | NORMAL | sai đã có ở reference | PASS |
| golden3 | 233 | V | 68 / 68 | 0.765625000 | PVC | đúng | PASS |
| golden4 | 121 | N | 7 / 7 | 0.527343750 | PVC | sai đã có ở reference | PASS |
| golden5 | 210 | V | 7 / 7 | 0.527343750 | PVC | đúng | PASS |
| golden6 | 210 | N | -124 / -124 | 0.015625000 | NORMAL | đúng | PASS |
| golden7 | 234 | N | -126 / -126 | 0.007812500 | NORMAL | đúng | PASS |
| golden8 | 121 | N | -125 / -125 | 0.011718750 | NORMAL | đúng | PASS |
| golden9 | 233 | V | 47 / 47 | 0.683593750 | PVC | đúng | PASS |
| golden10 | 210 | N | -126 / -126 | 0.007812500 | NORMAL | đúng | PASS |
| golden11 | 115 | N | -126 / -126 | 0.007812500 | NORMAL | đúng | PASS |
| fc14_118_5613 | 118 | R | -53 / -53 | 0.292968750 | NORMAL | OTHER, không chấm N/V | PASS |
| fc14_118_12239 | 118 | R | 68 / 68 | 0.765625000 | PVC | OTHER, không chấm N/V | PASS |
| fc14_118_416969 | 118 | R | -115 / -115 | 0.050781250 | NORMAL | OTHER, không chấm N/V | PASS |
| fc14_210_200430 | 210 | V | 105 / 105 | 0.910156250 | PVC | đúng | PASS |
| fc14_214_22287 | 214 | L | -108 / -108 | 0.078125000 | NORMAL | OTHER, không chấm N/V | PASS |
| fc14_233_20069 | 233 | V | -3 / -3 | 0.488281250 | NORMAL | sai đã có ở reference | PASS |
| fc14_233_59286 | 233 | N | -20 / -20 | 0.421875000 | NORMAL | đúng | PASS |
| fc14_233_291311 | 233 | N | -92 / -92 | 0.140625000 | NORMAL | đúng | PASS |

**Exact parity không phải classification accuracy.** 4/16 ca N/V vẫn sai nhãn (golden1, golden2, golden4, fc14_233_20069), đúng như reference TensorFlow; 4 ca OTHER không có nhãn N/V. Đây là bộ fixture chọn để debug, không dùng tỷ lệ này ước lượng accuracy. Không train/tuning hay dùng Test độc lập.

## Khôi phục và bảo toàn

Khôi phục firmware trước thử: **PASS**. Ghi lại đúng vùng backup và được esptool kiểm tra MD5; vùng ngoài 0x70000 không bị chạm. Không để TEST_ONLY lưu vĩnh viễn trên board. Manifest/hash/log nằm trong `debug/esp32_ai_test_only/`.
Capture sau khôi phục: 11072 mẫu, CRC=0, missing=0, source=HARDWARE; golden 12/12 PASS, không có marker TEST_ONLY. Đây là byte firmware thực tế trước thử, không phải binary mới vừa build.
Toàn bộ 11072/11072 mẫu sau khôi phục có lead-off; 5527 mẫu chạm 0/4095. Firmware báo SIGNAL_INVALID/LEADS_OFF. Không dùng những mẫu này để kết luận NORMAL/PVC; CNN chỉ chạy fixture tham chiếu trong bài thử.

Model SHA-256: `38705f5399ada9b87f466725608a053ae2305295a8a3cae7bda01f4928f4a394`. Golden gốc SHA-256: `12d63c89086b3615a92bee11914825cce9fd0d5bd11f41599d1281f00475b758`. Các file model, golden, preprocessing, signal detector, main lấy mẫu và state safety được xác minh hash không đổi; danh sách đầy đủ trong JSON.

## Kết luận và PENDING

Parity INT8 và khả năng chạy bài reference dưới tải được đánh giá bằng log board đính kèm. Không có kết luận AI-live đủ điều kiện. Record 121 vẫn có điểm yếu PPV; kết quả end-to-end cũ PVC recall 87,70%, F1 78,93% chưa thay đổi. Cần tiêu chí nghiệm thu được thống nhất trước đánh giá độc lập, kiểm chứng signal-quality/R-peak trên nguồn mô phỏng và đo tải dài hạn. Chưa đo CPU utilization độc lập. Không có thử nghiệm trên người; AI-live giữ LOCKED.

Dữ liệu: `debug/esp32_ai_test_only_results.json`; log raw/current tại `debug/esp32_ai_test_only/hardware_adc.bin`, `hardware_synthetic.bin`, `restored_firmware.bin`. Lượt FAIL giữ nguyên dưới `attempt1/`.
