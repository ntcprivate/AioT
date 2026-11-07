# Rà soát telemetry và Windows Monitor — 2026-11-06

Đã tiếp tục trên code hiện có, hoàn tất sửa và build; chưa flash, reset hoặc mở COM3.
**PENDING HARDWARE VALIDATION**: chưa có raw capture từ phiên lỗi mới; chưa xác minh
CRC thực tế hoặc 250 Hz xuyên suốt ESP32 → Windows. AI-live vẫn LOCKED.

## Bảo toàn công việc trước

Kiểm kê lúc tiếp tục xác định **10 file**, thay vì ước lượng 9 trong yêu cầu:

| File | Công việc được giữ và hoàn thiện |
|---|---|
| `main/CMakeLists.txt` | Dependency UART driver |
| `main/Kconfig.projbuild` | Tùy chọn synthetic mặc định OFF, không đi cùng live |
| `main/main.cpp` | Khởi tạo UART, nhánh synthetic, truyền thống kê clock |
| `main/telemetry.cpp` | Frame, UART TX, nguồn dữ liệu, bộ đếm và tốc độ |
| `main/telemetry.h` | Giao diện thống kê/UART |
| `main/telemetry_codec.h` | CRC/frame và mẫu synthetic xác định |
| `tools/ecg_monitor/ecg_monitor/app.py` | GUI, tốc độ, reset biểu đồ |
| `tools/ecg_monitor/ecg_monitor/protocol.py` | Giải mã và bộ đếm lỗi |
| `tools/ecg_monitor/ecg_monitor/serial_worker.py` | Capture trước parser, Serial reader |
| `tools/ecg_monitor/ecg_monitor/session.py` | Session, kiểm tra mẫu và clock |

Bốn đường dẫn cuối tính từ workspace; sáu đường dẫn đầu tính từ firmware này.
Agent trước đã xác minh lỗi tên Sampling rate, lỗi reset range, baud/layout khớp,
và bắt đầu capture/tách counters. Lượt này hoàn thiện trên chính các thay đổi ấy,
bổ sung kiểm thử, TX nguyên frame, synthetic, đo clock riêng và công cụ chẩn đoán.

Workspace không có Git repository: `git status`/`git diff` không dùng được.
Không reset, clean hoặc revert. Bản sao trước sửa nằm ở `debug/telemetry_fix_before/`;
kiểm kê ở `debug/telemetry_resume_files.json`; diff lúc tiếp tục ở
`debug/telemetry_resume_diff.patch`; diff sau hoàn thiện ở
`debug/telemetry_final_diff.patch`. Đây là diff với snapshot, không phải Git diff.
Danh sách file và SHA cuối nằm trong `debug/telemetry_fix_report.json`.

## Nguyên nhân có bằng chứng và phần còn chưa biết

1. GUI cũ tính Sampling rate từ số mẫu nhận được chia thời gian thiết bị. Mất batch
   làm chỉ số giảm khoảng 166 Hz dù metadata ADC là 250 Hz. Đây là tốc độ giao nhận,
   không chứng minh ADC chậm. Test tái hiện và kiểm tra bốn số đo độc lập.
2. Chuyển HARDWARE → DEMO trước đây không bật lại Y auto-range. Test tái hiện giữ
   nguyên range ±1e18. Bản sửa xóa ring, origin, session, filter, đường vẽ, pause,
   trạng thái Raw và reset cả range lẫn auto-range khi đổi nguồn/boot/kết nối.
3. Session trước đây có thể nhận giá trị âm rất lớn nếu gọi trực tiếp bỏ qua decoder.
   Nay toàn batch được kiểm tra trước khi cập nhật; NaN/Inf/ADC ngoài 0..4095 bị từ
   chối (ADC-error sentinel chỉ hợp lệ khi có cờ lỗi và được hiển thị gap).
   Plot kiểm tra tiếp trước khi vẽ, không dùng clamp để che dữ liệu sai.
   Dấu vết NaN ghi vào mảng integer có thể tạo -9223372036854775808; tuy nhiên
   không có capture/phiên bản GUI của ảnh lỗi để khẳng định đó là nguyên nhân ảnh.
4. Hai đầu đều 115200/8N1; layout `<IHB>` khớp. Giá trị 1e18 không thể xuất phát trực
   tiếp từ uint16 trong packet hợp lệ. Bộ đếm cũ `CRC/parse=23` là tổng lỗi, không
   phải bằng chứng có đúng 23 CRC mismatch.
5. Chưa xác định lỗi byte phát sinh ở firmware/UART/cáp/driver/host. Log board cũ
   chỉ có ADC/golden, không phải raw telemetry lỗi mới. Thay cơ chế TX tăng tính
   toàn vẹn nhưng **không phải bằng chứng nguyên nhân CRC thực tế đã được sửa**.

## Giao thức và UART

Framing vẫn là ASCII `ECG1 <CRC32 HEX8> <JSON>\n`, không phải binary COBS.
CRC32 IEEE tương thích zlib, chỉ bao phủ bytes JSON. Firmware thêm LF trước frame
để tách phần debug chưa có newline. JSON body nay **v=2** và bắt buộc `source` là
`HARDWARE` hoặc `SYNTHETIC_TEST`. GUI mới đọc cả v1 cũ để chẩn đoán; GUI cũ từ chối
v2 thay vì nhận nhầm synthetic là tín hiệu thật. Đóng GUI cũ và chạy bản 2.0.
Không sửa/đoán dữ liệu hỏng để qua CRC.

UART0 driver TX ring 4096 byte, RX 256 byte, LF/8N1/no flow control. Mỗi frame đã
kiểm tra độ dài được gửi bằng một `uart_write_bytes`; khóa TX của driver ngăn các
writer VFS khác chen vào giữa frame. Console của ứng dụng dùng chung mutex.
Chờ TX drain tối đa 500 ms ở task telemetry ưu tiên thấp, ngoài mutex console.
Task lấy mẫu core1 ưu tiên10 không chờ UART; telemetry core0 ưu tiên2.
Kiểm tra mã lỗi khởi tạo, partial write, format/truncation và timeout riêng.
`uart_baud_actual` được đọc từ driver; sai số chia clock nhỏ trong 0,5% là hợp lệ.
Không có ACK từ máy Windows: TX hoàn tất không đồng nghĩa host đã nhận được.

### Bốn tốc độ trong GUI

| Chỉ số | Cách đo và giới hạn |
|---|---|
| ADC / generator rate | `intervals*1e6/(last_us-first_us)` từ timestamp thực cùng buffer; 256 mẫu có 255 interval; chỉ hiện khi status còn mới |
| TX completed rate | Mẫu trong frame ghi/drain thành công trên clock thiết bị, cửa sổ TX gần đây; không đo host ACK |
| RX device-time rate | Số mẫu host nhận thành công trên khoảng timestamp thiết bị; giảm khi mất batch |
| RX wall-clock rate | Mẫu nhận trên clock monotonic tại Serial reader, cửa sổ khoảng 5 giây; khác clock render GUI |

Thiếu hoặc hết hạn dữ liệu hiện UNKNOWN. DEMO không tự gán ADC đo được là 250 Hz.
Timestamp lấy ngay trước lời gọi ADC, không phải alarm dự kiến; gồm scheduling
jitter. Nó không phải timestamp chính xác của tụ sample-and-hold bên trong ADC.
`late`, `missed_est`, pending notifications và interval ADC giữ nguyên thuật toán;
missed là ước lượng slot bỏ lỡ, không được cộng với ADC errors hay packet gaps
thành một con số tổng mất mẫu. Clock/rate không chứng minh chất lượng ECG.

### Phạm vi bộ đếm

| Bộ đếm | Phạm vi/ý nghĩa |
|---|---|
| CRC | JSON bytes không khớp CRC nhận được |
| Frame | Prefix/độ dài/CRC field/line boundary không hợp lệ |
| Schema | JSON hoặc kiểu/range/timestamp không hợp lệ |
| Sequence | Packet trùng/lùi hoặc boot cũ bị phát lại |
| Packet gaps / missing samples | Khoảng thiếu seq / khoảng thiếu sample index; có thể cùng một sự kiện, không cộng đôi |
| RX timing | Interval lệch >500 µs so với 4000 µs giữa sample ID liên tiếp |
| Synthetic mismatch | Giá trị không đúng pattern đã công bố |
| Các bộ đếm trên | Reset mỗi kết nối; raw capture giữ bằng chứng trước parser |
| Host queue drops / reconnects | Theo vòng đời Serial worker; lần mở đầu không tính reconnect |
| ADC errors / missed_est / late / tx_dropped | Firmware, tích lũy từ boot; tx_dropped là batch queue bị bỏ |
| format_errors / uart_write_errors / uart_tx_timeouts | Firmware, từ boot; lỗi tạo frame / ghi / chờ drain |

`sample_attempts` bao gồm lượt đọc lỗi; `tx_samples` chỉ tính frame hoàn tất TX;
`tx_bytes` tính frame hoàn tất, không bao gồm mọi boot/debug log.
`rejected_frames_total` chỉ là tổng tương thích, không mang tên CRC.

## Synthetic trên ESP32

`CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST=y` dùng cùng GPTimer, task, timestamp thực,
queue, UART và Windows parser. Thay lời gọi ADC bằng
`512 + ((uint64(index)*17) % 3072)`, pattern `saw17-v1`, LO giả bằng 0.
Không thay đổi kết nối GPIO hay nhánh ADC thật. Mỗi packet gắn SYNTHETIC_TEST,
GUI có nhãn rõ; không báo BPM/N/PVC thật.
Compiler loại cả `pipeline_observe` và `pipeline_offer` khỏi nhánh synthetic.
Kiểm tra symbol của main.cpp.obj: hai tham chiếu hiện ở bản hardware và vắng ở
bản synthetic. AI/golden khởi tạo vẫn giữ nguyên, lỗi hệ thống không bị nhãn test che.
Synthetic chỉ kiểm tra truyền số, không đánh giá AD8232 hoặc ADC analog.

## Kết quả kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| Python toàn bộ monitor/parser/CRC/session/GUI/serial giả | **42 PASS**, 4,869 s; `tools/ecg_monitor/reports/telemetry_fix_tests.log` |
| Bộ test trace operator cũ | **14 PASS**; không nới tiêu chí trace/golden |
| C++ system, signal, lead-off, trace codec, telemetry wire | **PASS** |
| C++ encoder → Python decoder | 500 batch / 16.000 mẫu, CRC/pattern/seq khớp |
| Stream host dài | 10.000 batch / 320.000 mẫu / 1.280 giây ảo, ring giữ ≤5.000 điểm; không phải chạy board 21 phút |
| Nạp giao thức host | 15.008 mẫu/60,032 giây ảo, 0 lỗi/gaps; ~6.660 B/s, **57,81%** dung lượng 11520 B/s ở115200/8N1; chưa tính tất cả log phụ |
| GUI offscreen | Đã xem ảnh `tools/ecg_monitor/reports/gui_telemetry_fix.png`; đổi nguồn/giá trị lỗi có regression test |
| CNN host golden | **12/12 EXACT**, 33 lần/mẫu ổn định; `debug/telemetry_fix_golden.log` |
| Parity Validation | **9.425/9.425**, 0 byte preprocessing sai, 0 output code sai; `tools/ecg_monitor/reports/offline_validation.json`, phần `chain` |
| R detector cũ | **FAIL**, sensitivity78,55%, PPV99,32%; giữ AI-live khóa |
| Build ADC thật, IDF5.4.4 | **PASS**, `build/esp32_ecg_tinyml_integrated.bin`, 316.880 byte |
| Build synthetic, IDF5.4.4 | **PASS**, `build_synthetic_telemetry_test/esp32_ecg_tinyml_integrated.bin`, 315.456 byte |
| Board/USB/ADC thực tế sau sửa | **PENDING HARDWARE VALIDATION** |

Fresh configure synthetic đã kiểm tra dependencies với constraints thật, không
cài lại Python/venv và không bỏ kiểm tra dependency. Build có cảnh báo vendor TFLM
shadow/CMake minimum cũ, không có lỗi compile/link. Log nằm tại
`debug/telemetry_fix_build.log`, `debug/telemetry_synthetic_configure.log`,
`debug/telemetry_synthetic_build.log`, `debug/telemetry_synthetic_build_final.log`.

Model, golden bytes, preprocessing, kernels, signal-quality và pipeline/FSM khớp
SHA trước sửa. Threshold vẫn0,52; GPIO34, LO+27, LO−26, LED23/buzzer25 giữ nguyên.
Không dùng Test, đổi split hoặc huấn luyện. Parity chỉ là component parity trên
các N/V đã match ở Validation dùng lại, không phải độ chính xác hệ thống độc lập.
File `reports/offline/extended_parity_mismatches.json` là bằng chứng chẩn đoán cũ
được giữ lại; kết quả mới phải đọc ở `offline_validation.json`, không suy từ tên file cũ.

## Cách chạy và lấy bằng chứng trên board

1. Đóng GUI cũ và chương trình Serial monitor khác. Chạy
   `tools/ecg_monitor/Start_ECG_Monitor.bat`. DEMO → Start để kiểm tra GUI trước.
2. Sau khi tự flash bản đã chọn, chọn HARDWARE MONITOR, COM3/115200 và chủ động
   Connect. Ứng dụng không tự kết nối khi mở. DTR/RTS=False trước open và không
   gửi lệnh reset; glitch do OS/USB driver vẫn chưa được kiểm chứng trên board.
3. Mỗi Connect tự ghi raw bytes **trước parser** vào
   `tools/ecg_monitor/captures/<UTC_uuid>.bin` và lỗi vào `.rejects.jsonl`.
   Raw capture hoạt động độc lập nút Save session CSV. CSV vẫn ghi rõ nguồn.
   Disconnect để flush/đóng capture; packet dở cuối khi ngắt có thể tạo trailing
   partial, phải báo riêng, không tự gọi là CRC mismatch.
4. Phân tích offline (không mở COM):

```powershell
Set-Location 'D:\Code Part Two\AIoT\tools\ecg_monitor'
.\.venv\Scripts\python.exe diagnose_capture.py 'captures\TEN_FILE.bin' --output 'reports\capture_analysis.json'
```

Gửi file `.bin`, `.rejects.jsonl`, `capture_analysis.json`, CSV nếu có, phiên bản
GUI/firmware, mode và thời gian thử. Analyzer giữ SHA/bytes, lỗi tách loại, gaps,
pattern, counter firmware và rate trên device clock; raw file không chứa đủ
arrival timestamps để phục dựng RX wall-clock rate. Không sửa bytes để tạo PASS.

### Build và flash do người dùng chủ động thực hiện

Trong terminal ESP-IDF5.4.4 đã export, dùng đúng một cấu hình dưới đây.
Các lệnh flash chỉ là hướng dẫn; agent chưa chạy chúng. Đóng GUI trước flash.

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
# ADC thật: sdkconfig gốc có synthetic OFF, AI-live OFF
idf.py build
# Chỉ thực hiện khi bạn quyết định flash bản ADC thật:
idf.py -p COM3 flash
```

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
# Cấu hình riêng đã tạo: synthetic ON, AI-live OFF; không sửa sdkconfig gốc
idf.py -B build_synthetic_telemetry_test -D "SDKCONFIG=$PWD\debug\sdkconfig.synthetic_test" build
# Chỉ thực hiện khi bạn quyết định flash bản synthetic:
idf.py -B build_synthetic_telemetry_test -D "SDKCONFIG=$PWD\debug\sdkconfig.synthetic_test" -p COM3 flash
```

Sau flash, đóng terminal monitor rồi dùng GUI Connect; không giữ COM đồng thời.
Không flash hai bản liên tiếp trong cùng một lượt kiểm thử; ghi lại đúng mode.

### Tiêu chí bench đề xuất, chưa xác nhận đạt trên board

- Không nối cơ thể. Bắt đầu bằng synthetic ít nhất10 phút sau boot/golden; ghi
  cả transient khởi động riêng. Xác minh source/pattern, acquisition gần250Hz
  (ví dụ trung bình249..251Hz), interval trung bình gần4000µs và min/max/jitter.
- Kiểm tra đồng thời TX/RX hai clock, 0 CRC/frame/schema/seq/pattern lỗi, 0 queue
  drops/ADC errors/missed; kiểm tra host drops và UART timeouts, không chỉ nhìn đồ thị.
- Nếu acquisition250 nhưng TX thấp/queue drops tăng: điều tra producer/queue/UART
  trước. Nếu TX đủ nhưng RX thấp: đối chiếu capture/sequence/host queues; TX không
  có ACK nên chưa loại được USB/driver. Nếu acquisition thấp: xem timestamp và
  missed/late trước. Không chọn nguyên nhân chỉ từ một chỉ số.
- Sau đó về firmware ADC thật, dùng nguồn ECG mô phỏng tương thích AD8232, đúng
  mức/common-mode của module, đo rail/lead-off và timing. INVALID_LEADS vẫn loại
  khỏi AI; không dùng mẫu chạm rail hoặc LO cao để kết luận NORMAL/PVC.
- Chưa có số đo board về heap/stack/CPU, USB jitter hay analog chất lượng sau sửa.
  Chỉ đánh dấu 250Hz end-to-end đạt khi raw capture thực chứng minh đủ chuỗi;
  không coi host tests hoặc build PASS là bằng chứng đó.
