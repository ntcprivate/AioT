# ECG Monitor cho Windows

## Bản sửa telemetry 2.0 — 2026-11-06

Xem [báo cáo mới và hướng dẫn capture/synthetic/flash](../../firmware/esp32_ecg_tinyml_integrated/docs/telemetry_reliability_review.md).
GUI mới tách ADC/generator, TX, RX theo device clock và RX theo host clock;
reset toàn bộ plot/session khi đổi nguồn. Firmware mới dùng body protocol **v2**
(prefix vẫn ECG1), source HARDWARE/SYNTHETIC_TEST bắt buộc; parser đọc được v1 cũ.
Đóng GUI cũ rồi chạy lại Start_ECG_Monitor.bat. Khi chủ động Connect, raw capture
tự lưu ở `captures/*.bin`, độc lập CSV; lỗi ở `*.rejects.jsonl`.
Chẩn đoán offline bằng `diagnose_capture.py FILE.bin --output reports/capture_analysis.json`.
42 tests PASS và hai build PASS chưa chứng minh board hết CRC/loss:
**PENDING HARDWARE VALIDATION**. AI-live vẫn LOCKED.

Ứng dụng bàn thử nghiên cứu: xem ADC qua USB Serial, hiển thị trạng thái và lưu
đủ mẫu/timestamp. Không phải thiết bị chẩn đoán. Không kết nối cơ thể với phần
cứng chưa được đánh giá cách ly điện/dòng rò, đặc biệt khi dùng USB laptop.

## Mở ứng dụng

1. Môi trường đã được cài và kiểm thử trong `tools/ecg_monitor/.venv` bằng
   Python **3.13** riêng. Không thay `.venv` Python3.11 ở thư mục dự án.
2. Nếu cài lại trên máy khác: cài Python3.13 có Python Launcher, nhấp đúp
   `setup.bat`. Cần Internet để tải các dependencies được ghim trong requirements.
3. Nhấp đúp **Start_ECG_Monitor.bat**. Chọn DEMO, bấm Start Monitoring để thử
   ngay mà không cần ESP32. Không phải mở PowerShell để sử dụng hàng ngày.
4. Nếu không mở được, xem `reports/startup_error.txt` hoặc chạy lại setup.bat.
   Chưa đóng gói/bảo chứng bản EXE PyInstaller.

## Ba chế độ

| Chế độ | Dữ liệu và điều kiện |
|---|---|
| DEMO | Sóng P-QRS-T tổng hợp để thử giao diện; luôn ghi DEMO, không chạy AI, không giả BPM/PVC |
| HARDWARE MONITOR | Mẫu ADC thật từ firmware telemetry; được xem sóng khi AI đang LOCKED |
| VALIDATED AI TEST | Hiện đang **LOCKED**; detector không đạt tiêu chí trên Validation, chưa có simulator/board validation |

Không tự mở COM, tự flash, tự reset hay tự bật AI-live. Danh sách COM chỉ được
liệt kê. Chọn HARDWARE MONITOR rồi chủ động Connect. Đóng idf.py monitor/Serial
Monitor khác trước vì chỉ một chương trình có thể giữ COM.

GUI hỗ trợ firmware `ECG1` body v1/v2, baud **115200,8N1**. Nếu sau5 giây chưa
có gói hợp lệ, ứng dụng báo cần kiểm tra firmware/baud/COM. Firmware cũ chỉ in
ADC_BUFFER/first10 không thể tạo đủ sóng250Hz và không được dùng để giả sóng.

Reconnect là tùy chọn, mặc định OFF. Worker đặt DTR/RTS=False trước open, không
gửi lệnh hoặc xung reset. Một số driver/OS vẫn có thể tạo glitch khi mở cổng;
không có bảo đảm phần mềm tuyệt đối cho mạch auto-reset của USB-UART. Cơ chế này
theo [tài liệu pySerial](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.open).
Nếu board reset khi người dùng mở COM, tắt auto reconnect và kiểm tra mạch/driver;
không vô hiệu hóa các cổng an toàn để che hiện tượng đó.

## Dashboard

- Sóng raw scrolling10 giây, ADC counts chưa hiệu chuẩn, không tự đổi sang mV.
- Filtered là preview causal bandpass0.5-40Hz **trên laptop**, không phải input
  CNN hoặc tín hiệu đã được chứng nhận hợp lệ. Có thể bật/tắt cả hai đường.
- Pause Display dừng vẽ nhưng vẫn nhận, xử lý và ghi CSV. Stop Monitoring dừng
  thu vào phiên và đóng CSV; Disconnect giải phóng COM. Không lệnh nào dừng ADC.
- Sampling rate tính từ timestamp các mẫu nhận được; mất gói/timestamp gap
  hiện riêng, đồ thị có khoảng trống thay vì tự nội suy. Khi raw quá2 giây không
  cập nhật, rate và lead status trở thành chưa xác định.
- Hiển thị state/reason, lead flags, clipping, PTP/diff metrics, ước lượng50Hz,
  baseline delta, các lỗi ADC/mất mẫu/mất gói, trạng thái model, LED/buzzer.
- BPM/RR và R/PVC markers chưa được bật vì detector chưa đạt kiểm chứng.
  Classification luôn UNKNOWN trong DEMO và khi AI bị khóa. Kết quả cũ bị
  xóa khi timeout/reconnect. Một gói tự khai NORMAL cũng không đủ để hiển thị
  NORMAL nếu thiếu đầy đủ golden/quality/detector/AI/source/freshness gates.
- Lead-off, clipping, lỗi ADC hoặc gap được phát hiện trên từng mẫu ở laptop
  cũng loại bỏ kết quả AI cũ, không đợi đến status packet tiếp theo.

## Ghi CSV và phân tích offline

Start Monitoring → Save session CSV → chọn **tên file mới**. CSV có source,
boot ID, sequence/sample index, timestamp thực, raw ADC, lead flags, errors và
snapshot trạng thái nhận gần nhất kèm `status_timestamp_us`. Không coi snapshot
0.5 giây một lần là state được đo độc lập cho từng mẫu. Lead/error flags là
theo từng mẫu; guard cục bộ có thể ghi SIGNAL_INVALID sớm hơn status firmware.
Stop Recording/Stop Monitoring/đóng app sẽ đóng CSV và tạo `.report.json` mô tả
phiên thử nghiệm. Không ghi đè CSV cũ; đây không phải báo cáo y khoa.

Analyze CSV mở tác vụ nền để tạo PSD, đồ thị raw/filtered, clipping, baseline
và các tỷ lệ phổ. Chỉ nhận chuỗi đầy đủ, đơn điệu, liên tục250Hz, một source/boot.
File thiếu mẫu, first10 hoặc lỗi ADC sẽ bị từ chối thay vì tự vá dữ liệu. Phân
tích thực tế50Hz cần capture mới đầy đủ; log first10 cũ không đủ để kết luận.

```powershell
# Tùy chọn dùng CLI một lần, không cần cho việc xem hàng ngày
.\.venv\Scripts\python.exe -m ecg_monitor.offline --csv my_session.csv --output reports/my_analysis
```

Notch50Hz Q30 + bandpass causal trong công cụ offline là **thử nghiệm**, có
transient và trễ pha. Nghiên cứu12459 cửa sổ có nhãn cho thấy morphology không
giữ nguyên; chưa cho phép dùng filter này trước CNN, không nới quality gate.

## Kiểm thử đã thực hiện

Xem `reports/monitor_tests.log`, `gui_*performance.json`, `transport_load.json`,
`gui_demo.png`, `offline_validation.json` và các báo cáo firmware. GUI được kiểm
thử Qt offscreen trên Windows, không mở COM. Có test parser/CRC/cắt gói/sequence,
reconnect mô phỏng/no-device, recording khi pause, ngăn NORMAL giả, raw/filtered
graph performance. Nhấp đúp Run_Tests.bat để chạy lại các test host.

Luồng tải 60 giây ảo dùng khoảng5.8KB/s, khoảng50% UART115200/8N1; đây là tính
toán và phép thử host, không phải số đo packet loss/CPU/timing trên ESP32.

## Validation nghiên cứu và các phần còn thiếu

`validate_offline.py` đọc **chỉ các record thuộc Validation đã lưu**, chạy mã
detector C++ hiện tại và quality-gated mirror trên host. Không dùng Test, không
đổi split. Đã thử7 record115/118/121/210/214/233/234: sensitivity78.55%, PPV99.32%.
Tiêu chí99%/99% cho từng record không đạt; detector cần được thay/hoàn thiện và
kiểm chứng lại. Pure50Hz/flat controls không có peak, nhưng điều đó không bù
cho các nhịp thật bị bỏ sót.

9425 cửa sổ N/V khớp annotation sau quality-gated detector có preprocessing và
đầu ra CNN khớp TensorFlow2.21 CPU builtin từng byte/code sau bản sửa per-channel
FC. Đây là **component parity**, không phải accuracy end-to-end: các nhịp bỏ sót,
false peaks và nhãn khác đã bị loại khỏi nhóm so sánh đó. Validation đã dùng
nhiều lần; chưa có đánh giá độc lập cuối cùng.

Môi trường `.venv_reference` riêng chứa TensorFlow2.21, chỉ dùng cho test; GUI
không cần TensorFlow. Muốn tái tạo đầy đủ cần compiler g++, TFLM managed sources,
MIT-BIH cục bộ và môi trường reference:

```powershell
py -3.13 -m venv .venv_reference
.\.venv_reference\Scripts\python.exe -m pip install -r requirements-validation.txt
# Trong firmware integrated: python tests/run_full_host.py
# Và compile tests/detector_replay.cpp, tests/preprocess_host.cpp theo docs audit
.\.venv\Scripts\python.exe validate_offline.py
```

Không thay một môi trường đã có bằng lệnh venv nếu đang sử dụng nó.

Simulator integration, timing250Hz cùng telemetry, LED/buzzer thực, packet loss
qua CP210x, RAM/stack/latency trên board và mọi kiểm thử hardware mới đều
**BLOCKED/PENDING**: phiên làm việc này không flash/reset/mở COM. Xem
[`bench_validation.md`](../../firmware/esp32_ecg_tinyml_integrated/docs/bench_validation.md).
