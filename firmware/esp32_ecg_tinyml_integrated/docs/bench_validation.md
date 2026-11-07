# Kiểm thử tiếp theo trên bàn thử, không nối cơ thể

Phiên Codex này chỉ chạy host tests và build. Không mở COM, không flash/reset.
Các bước bên dưới do người dùng thực hiện có chủ đích. Detector R đang FAIL;
giữ AI-live LOCKED dù các bước điện/timing dưới đây PASS.

## 1. Nạp firmware monitor

Trong ESP-IDF5.4.4 PowerShell terminal:

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
idf.py build
idf.py -p COM3 flash
```

Đóng monitor Serial khác. Nhấp đúp `tools/ecg_monitor/Start_ECG_Monitor.bat`,
chọn HARDWARE MONITOR, chọn COM3 và Connect → Start Monitoring. Telemetry mặc
định115200. Nếu mở monitor bằng idf.py để debug trước, phải đóng nó trước GUI.
Ứng dụng không tự gửi reset hay unlock. Reconnect mặc định OFF.

## 2. Wiring và power

OUT→GPIO34, LO+→GPIO27, LO-→GPIO26, nguồn3.3V/GND; LED23 và active buzzer25
giữ nguyên. Kiểm tra điện áp/continuity tại cả module và ESP32, không chỉ tên
in trên dây. Xác nhận SDN/module enable và chế độ AC/DC bằng schematic/strap
thực tế. File Wokwi `D:\diagram (1).json` chỉ là potentiometer simulation,
không thay thế schematic AD8232.

DC: mất +IN làm LOD+ HIGH, mất -IN làm LOD- HIGH; cần reference/RLD return phù
hợp. AC: mất một trong hai input làm LOD+ HIGH, LOD- luôn LOW. GPIO internal
pulls tắt; tuyệt đối không kéo LO LOW để lách INVALID_LEADS.

## 3. ECG simulator

Dùng nguồn ECG simulator thích hợp có các electrode outputs và reference/RL
theo manual của simulator/module. Không nối cơ thể. Bắt đầu nominal1mV,60bpm
nếu thiết bị hỗ trợ. Đợi settle, kiểm tra LO cả hai LOW khi circuit đạt điều
kiện kết nối. Khi tháo từng simulator input, SIGNAL_INVALID phải có hiệu lực
ngay theo sampling/batch latency, không kêu còi PVC và không xuất NORMAL.

Thử cả hai leads rời, tín hiệu flat, waveform clipping và ECG có nhiễu mô
phỏng. Thử tín hiệu sạch60/90/120bpm và N/V từ simulator nhưng **không** dùng
chúng để mở AI-live tự động. BPM trên GUI vẫn -- vì detector chưa được xác minh.

Nếu chỉ cấp function generator vào GPIO34: tháo OUT của AD8232 trước để tránh
nối hai outputs; dùng common GND và waveform giới hạn0..3.3V (ví dụ offset1.65V,
peak0.2V). Đây chỉ là ADC test, không tạo đường dẫn điện tại electrode inputs,
không làm lead-off trở nên hợp lệ. Không cấp biên độ mức ADC trực tiếp vào
electrode input gain cao của AD8232.

## 4. Chứng minh timing và transport

Ghi phiên đầy đủ ít nhất10 phút cùng golden startup, telemetry, output task
và GUI recording. Kiểm tra:

- Golden trên **binary mới**:12 EXACT_MATCH, warm_exact/stable_exact=1,
  ECG_GOLDEN_DONE failed=0/PASSED; kernel log có fc_per_channel_single=1.
- Timestamp distribution thực: nominal4000us, không duplicate/reverse;
  expected samples/time250Hz. missed_est/adc_errors/snapshot_errors/tx_dropped,
  CRC/parse errors và packet/sample gaps phải được báo cáo, không tự bỏ qua.
- So sánh khi GUI pause display, khi recording, khi bật filtered preview và
  khi ngắt/reconnect USB có chủ đích. CPU/heap/stack high-water và latency cần
  đo riêng trên board; không suy ra từ benchmark host.
- Dùng logic analyzer/nguồn chuẩn nếu cần khẳng định độ chính xác clock và
  độ trễ ADC. Timestamp hiện tại là software ADC-call bound, không hardware
  sample-and-hold instant hay lịch alarm.
- Xác nhận self-test2s+6beep chỉ một lần, WAITING slow blink, INVALID fast
  blink, buzzer OFF ngoài self-test hoặc PVC hợp lệ. Hiện tại live locked nên
  không mong đợi một cảnh báo PVC/NORMAL từ ADC.

Nếu queue đầy hoặc mất gói: lưu counters và CSV, kiểm tra serial contention,
nguồn/USB/driver, CPU/stack, kích thước queue và tải log; không sửa số liệu để
cho PASS. CRC bảo vệ nguyên vẹn dữ liệu, không chứng minh không có packet loss.

## 5. Phân tích nguồn nhiễu

Save CSV đủ mẫu/timestamp, Stop Recording, bấm Analyze CSV. Giữ source/boot và
đoạn liên tục; không ghép qua reconnect/gap để làm PSD như thể liên tục.
So sánh raw PSD,48-52Hz power, clipping, baseline drift và high-frequency
fraction trước/sau filter thử nghiệm. DFT50 trên firmware chỉ là diagnostic.
Kiểm tra nguồn, common mode, bias/RLD, layout, dây và shielding theo schematic
thay vì mặc định notch chữa mọi lỗi. Không dùng dữ liệu INVALID_LEADS để đánh
giá độ chính xác N/PVC; lọc đẹp hơn không đồng nghĩa hợp lệ.

## Điều kiện còn thiếu trước AI-live

Detector streaming phải đạt tiêu chí đã ghi, segmentation/preprocessing/CNN
parity phải PASS, noise controls và simulator replay phải PASS, rồi mới có
independent final evaluation phù hợp. Hiện detector đang FAIL nên không có
hướng dẫn bật experimental-live để bỏ qua bước này. Việc chuyển sang thử trên
cơ thể nằm ngoài phiên này và cần đánh giá an toàn điện riêng.
