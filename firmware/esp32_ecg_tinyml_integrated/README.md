# ESP32 ECG TinyML integrated — nguyên mẫu thử nghiệm

## Telemetry reliability revision — 2026-11-06

[Báo cáo tiếng Việt, kết quả test/build và hướng dẫn synthetic/raw capture/flash](docs/telemetry_reliability_review.md).
ECG1 body v2, UART driver TX nguyên frame, source synthetic rõ ràng; GUI 2.0 tách
bốn tốc độ và bộ đếm lỗi. ADC thật và synthetic build PASS bằng IDF5.4.4.
Chưa flash/mở COM; CRC thực tế và 250Hz end-to-end: **PENDING HARDWARE VALIDATION**.
AI-live vẫn LOCKED; các báo cáo cũ bên dưới là lịch sử, không thay kết quả mới tại
`debug/telemetry_fix_report.json`.

## Current system revision - Windows Monitor and telemetry

USB Serial ECG1 batched telemetry is now the default. Use
[Windows ECG Monitor](../../tools/ecg_monitor/README.md) and read the
[current audit](docs/system_audit.md), [protocol](docs/telemetry_protocol.md),
[bench procedure](docs/bench_validation.md) and [test/build report](debug/system_completion.json).

WAITING/INVALID/COLLECTING have distinct nonblocking LED patterns; NORMAL is
reserved for valid live inference. Model faults latch. Raw quality thresholds
are unchanged; recovery requires two quality-passing blocks. ADC250Hz and
lead-off27/26 remain; no board sampling claim for this new binary yet.

CNN golden12/12 (33 repeats each) and9425 extended C++/TF2.21 code comparisons
PASS on host after Conv plus per-channel FC rounding compatibility patches.
R detector sensitivity78.55% FAILS release criteria: AI-live remains locked,
BPM/classification unknown. Full-system live validation is NOT_COMPLETE.
No flash/reset/COM open. Earlier sections below describe previous iterations
and binaries; their output-state tables/build sizes are historical.

## Current AD8232 lead-off wiring review - 2026-11-06

Physical LO+ = GPIO27, LO- = GPIO26, OUT = GPIO34. Input/no internal pulls,
active-HIGH lead-off and INVALID_LEADS checks retained. New per-buffer
AD8232_LEADS reports both last raw levels and per-pin HIGH counts from the
same immutable snapshot. Stable250Hz does not imply connected electrodes;
swapping plus/minus cannot change lo_any (OR). Physical cause of the prior
lo_any=256 remains to be measured on board, even though tests/build pass.

See [evidence and simulator-only bench procedure](debug/lead_off_review.md)
and [current firmware build report](debug/lead_off_review.json).
The older numerical-fix section/reports below refer to that earlier binary;
CNN/golden/threshold/FSM remain unchanged. No flash/reset or AI-live enabled.

## Current numerical fix - 2026-11-06

Root cause is proven: first CONV double rounding produces three +1 LSB errors;
Conv-only single rounding fixes all 12 golden samples and all 16 sample-5
operator tensors on the actual TFLM **host** interpreter. The new ESP-IDF5.4.4
binary builds successfully, but patched board execution is **pending**.

See [diagnosis, changed files/tests and COM3 commands](debug/numerical_fix_notes.md)
and [current evidence/build report](debug/numerical_fix_report.json).
Model/golden/threshold0.52 are unchanged; ADC-live remains disabled. No flash or
reset was performed. Earlier sections below record previous debug iterations;
claims of unresolved numerical cause there are superseded by this section.

## Trace protocol2 — sửa kiểm tra toàn vẹn log

Build cuối ESP-IDF5.4.4 đã PASS, binary299600byte (`0x49250`), còn71% app
partition1MiB trống. Chưa flash hoặc đo bản protocol2 trên ESP32.

Log gốc `log.esp32_ecg_tinyml_integrated.20261106042753.txt` và bản
`debug/serial_trace.log` có cùng SHA256. Trong277 dòng DATA tìm thấy35 chunk
thiếu HEX (28 độ dài lẻ,7 độ dài chẵn) và2 dòng hỏng key: dòng124 `ffset=960`,
dòng339 `p=9`. Vì vậy hỏng cả literal metadata, không chỉ chuỗi HEX.
Chi tiết/bằng chứng: `debug/trace_transport_audit.json`. Không phục hồi ký tự
bị thiếu và không dùng trace cũ để xác định operator sai.

Vòng snprintf cũ có char[129],64byte, mỗi byte uint8_t tạo2 ký tự +NUL;
không tìm thấy tràn biên hay shared HEX buffer trong nguồn. Nhưng thiếu kiểm
tra return/độ dài/ghi/flush, thiếu chunk checksum. Log nhận được không xác
định được mất ký tự ở formatting/stdio/VFS/UART/USB hay host terminal. Driver
IDF UART VFS có khóa ghi và chờ FIFO; không mặc định quy lỗi cho UART.

Bản mới:

- `trace_codec.h`: encoder nibble, chunk16byte → đúng32ký tự, chunk cuối
  nbyte →2*n ký tự, NUL rõ ràng, kiểm tra capacity và strlen trước khi ghi.
- DATA có `offset`, `nbytes`, `hex_chars`, `chunk_fnv`. TENSOR giữ checksum
  toàn tensor. END có tổng byte/chunk, checksum toàn stream, lỗi sinh/ghi.
- Mọi dòng trace gồm BEGIN/TENSOR/DATA/END/RESULT có `line_fnv`, bảo vệ cả key
  và giá trị; FNV1a32 tính từ chữ E của ECG_TRACE đến trước khoảng trắng
  ` line_fnv=`, không gồm suffix hoặc CR/LF. Đây là checksum chẩn đoán,
  không phải xác thực mật mã và không đảm bảo không collision.
- Một khóa recursive chung cho mọi task xuất console trong project, cộng
  khóa stdio; format một record có giới hạn, kiểm tra fwrite/fflush. ESP_LOG
  của ứng dụng cũng dùng khóa này. Panic/ROM/ngoại vi writer ngoài ứng dụng
  không được bảo đảm bởi khóa; checksum sẽ từ chối capture không nguyên vẹn.
- Trong dump, logger vẫn nhận/kiểm tra summary nhưng tạm không in ADC_BUFFER.
  ISR, ADC read, buffer256 và task sampling không bị pause hoặc đợi console.
  Khi in lại, `ADC_TRACE_PAUSE` báo số summary ẩn và lỗi integrity nếu có.
  Đây không phải mất mẫu ADC; vẫn phải kiểm tra missed_est/late trên board.
- Comparator bắt buộc protocol2, BEGIN/END/RESULT đúng thứ tự, checksum dòng/
  chunk/tensor/stream, đủ byte, không offset trùng/gap và RESULT khớp tensor
  cuối. Chỉ sau đó mới tính numerical divergence. Lỗi ghi `TRACE_REJECTED`,
  không vá dữ liệu hoặc tái sử dụng PASS của lần trước.

### Kiểm thử trên ESP32

1. Bản sửa đã build ESP-IDF5.4.4, chưa tự flash. Bạn chủ động nạp firmware
   sau khi xác nhận đúng cổng COM. ADC-live vẫn tắt, threshold0.52 không đổi.
2. Lưu log đầy đủ **một boot mới** vào `debug/serial_trace_v2.log`. Phải thấy
   `ECG_TRACE_BEGIN protocol=2 ... chunk_bytes=16`, DATA có nbytes/checksum,
   END COMPLETE/generation_errors=0/write_errors=0, RESULT invoke_ok=1/trace_ok=1.
   Các log ADC_BUFFER tạm vắng trong dump là có chủ đích, không tắt GPTimer.
3. Giữ nguyên `debug/python_operator_reference.json` đã tạo. Từ workspace gốc:

```powershell
python firmware\esp32_ecg_tinyml_integrated\tests\compare_operator_trace.py --log firmware\esp32_ecg_tinyml_integrated\debug\serial_trace_v2.log
```

Log cũ protocol1 thiếu checksum mới bị từ chối, phải thu lại; không tự chuyển
đổi hoặc chèn lại ký tự. Nếu protocol2 còn hỏng, gửi log thô và báo cáo reject
để phân biệt lỗi sinh (generation_errors), lỗi ghi (write_errors) và mất ký
tự sau khi kiểm tra trong firmware. Chưa có log board mới nên chưa tuyên bố
đã hết mất ký tự hay xác định operator đầu tiên lệch.

Test tái chạy từ folder project:

```powershell
python -m unittest discover -s tests -p test_trace_protocol.py -v
g++ -std=c++17 -Wall -Wextra -Werror -I main tests/trace_codec_test.cpp -o tests/trace_codec_test.exe
.\tests\trace_codec_test.exe
```

14 test Python và host test encoder đã PASS, gồm valid, mất1ký tự HEX,
mất1ký tự key, mất nguyên byte, thiếu marker/chunk, checksum sai và RESULT sai.
Test chỉ dùng numerical fixture trong thư mục tạm, không phải log ESP32 giả.

## Debug tiếp sample 5 — bằng chứng mới và trace operator

Bản debug operator đã build/link thành công: binary298096byte (`0x48c70`),
qua kiểm tra app partition1MiB. Chưa flash hoặc chạy trace mới trên board.
Xem `operator_debug_report.json` (thay cho kết luận nguyên nhân lần trước).

**Đính chính:** log có sẵn `results/esp32_serial.log` của Step8 cũng ghi
sample2=-61 (reference−66), sample5=0 (reference7), và ECG_DONE FAILED.
`esp32_inference_comparison.json` xác nhận10/12 exact,11/12 lớp khớp.
Vì vậy không thể xem Step8 là baseline đã PASS mọi golden; sai khác sample5
đã có trước tích hợp. Thay lựa chọn ESP-NN là khớp cấu hình, chưa phải bằng
chứng đã sửa được sai khác numerical với Python. Chưa thay reference/dung sai.

Trong bản debug, `reference_active`/`esp_nn_effective` được lấy từ **compiler
options thực tế của target TFLM**, không chỉ suy ra từ sdkconfig hoặc probe.
CMake dừng nếu yêu cầu reference nhưng target vẫn có define ESP_NN. Đối chiếu
compile_commands khi build và log ECG_KERNELS sau khi bạn nạp lại.

Một điểm cần phân biệt: kernel `esp_nn/reduce.cc` có fast-path MEAN riêng không
bị bao toàn bộ bởi `#if ESP_NN`; tắt define ESP_NN không có nghĩa mọi operator
đều trở thành cùng implementation với Python TFLite. Đây là **ứng viên cần
trace**, chưa phải kết luận MEAN gây lỗi. Sai khác nhỏ ở conv/mean/FC cũng có
thể tích lũy thành7LSB ở sigmoid. Golden input là INT8 có sẵn, không đi qua
z-score/quantize ADC, nên không thể dùng nhiễu/rail/leads ADC để giải thích
golden hoặc kết luận N/PVC cho dữ liệu ADC đó.

### Lấy trace thực tế (không tự flash)

`CONFIG_ECG_OPERATOR_TRACE=y`, `CONFIG_ECG_TRACE_SAMPLE=5` mặc định trong
menuconfig. Profiler của TFLM chụp byte output ngay cuối mỗi operator, trước
khi arena reuse. Không sửa thư viện hoặc bật preserve_all_tensors ở firmware;
không allocate/UART trong callback. Thêm buffer diagnostic cố định24KiB ngoài
arena. Dump sau Invoke trên task AI; sampling vẫn ưu tiên cao hơn. Chế độ này
không dùng để báo latency/performance production hoặc khẳng định 0 mất mẫu.
Tắt option trace để bỏ buffer và overhead sau khi xác định lỗi.

Sau khi **bạn** chọn nạp bản debug, lưu log đầy đủ một boot, gồm ECG_KERNELS,
ECG_ASSETS, ECG_TRACE_BEGIN/TENSOR/DATA/END/RESULT và ECG_GOLDEN_DONE, vào
`debug/serial_trace.log`. Không gộp nhiều boot; thiếu chunk/checksum là lỗi
capture, không được kết luận kernel sai. UART đang có ADC_BUFFER vẫn được
phân biệt bằng prefix; công cụ bỏ qua các dòng không phải trace.

### Tạo tensor reference bằng Python máy tính

Từ workspace gốc, Terminal có TensorFlow2.21 đang hoạt động:

```powershell
.\.venv\Scripts\python.exe firmware\esp32_ecg_tinyml_integrated\tests\compare_operator_trace.py --generate --sample 5
```

Chỉ dùng binary golden Validation256byte của sample5. Không đọc dữ liệu ADC
hoặc Test, không cập nhật reference cũ. Script kiểm tra Python cuối cùng vẫn
ra7; nếu khác7 thì dừng để kiểm tra version trước khi tạo tensor reference.
TFLite CPU không delegates, preserve tensors để đọc intermediate; ghi
`debug/python_operator_reference.json`. Trong Codex `.venv` còn trỏ tới
Python311 không tồn tại nên chưa tạo được file reference này.

Sau khi có file reference và log thật, so sánh bằng Python stdlib:

```powershell
python firmware\esp32_ecg_tinyml_integrated\tests\compare_operator_trace.py --log firmware\esp32_ecg_tinyml_integrated\debug\serial_trace.log
```

Tạo `debug/operator_comparison.json`: xác minh SHA model/data, input checksum,
operator order/version/tensor/quantization, đủ mọi byte và checksum, rồi xác
định operator **đầu tiên** có output lệch. Báo số phần tử lệch, LSB lớn nhất,
16 sai khác đầu. Không suy luận operator nếu log thiếu/corrupt. Tensor đầu
tiên lệch chỉ xác định boundary; tiếp theo phải xem input/quantization/kernel
để kết luận cơ chế lỗi. Chưa có trace mới nên nguyên nhân arithmetic cụ thể
của7LSB vẫn **UNRESOLVED**, không tuyên bố đã sửa inference.

ADC250Hz, self-test LED/buzzer và bốn trạng thái không đổi. ADC-live vẫn tắt;
golden lỗi vẫn SIGNAL_INVALID. Leads-off và raw chạm rail phải tiếp tục bị loại.

Project mới, ESP-IDF **v5.4.4**, target **esp32**, ESP32-WROOM-32 không PSRAM.
Hai project nguồn và model/dataset được giữ nguyên. Không flash tự động.

## Sửa sai khác golden / self-test phần cứng

Bản sửa đã **build/link thành công** bằng ESP-IDF5.4.4/toolchain có sẵn qua
`cmake --build build --parallel 4`. Binary 295664 byte (0x482f0), vừa app
partition1MiB, còn72% trống. Chưa flash hoặc chạy lại golden trên board.
Xem `golden_debug_report.json` cho bằng chứng so sánh và trạng thái build.
Lần configure đầu trong sandbox không đọc được git describe của IDF nên chuỗi
`IDF_VER` là HEAD-HASH-NOTFOUND; source/version macros vẫn là5.4.4 (được
main.cpp kiểm tra). Đây là giới hạn metadata build, không phải thay đổi
arithmetic kernel. Build lại từ ESP-IDF Terminal của bạn để lấy chuỗi version
từ môi trường sở hữu repository bình thường.

Đối chiếu hai project cho thấy model, golden binary, metadata, dependency lock
và 669 file component giống nhau. Tuy nhiên build Step8 có cache
`ESP_NN_OFF_PROBE=1`: các kernel biên dịch không có `-DESP_NN`, dù sdkconfig
bật ESP-NN. Build tích hợp trước sửa lại có `-DESP_NN`. Chỉ nhìn sdkconfig là
không đủ xác định đường kernel thực tế. Không đổi model hoặc reference.

Project hiện mặc định CMake `ECG_REFERENCE_KERNELS=ON`, đặt probe của component
trước khi cấu hình dependency để khớp lựa chọn kernel của Step8. Component
ESP-NN vẫn là dependency nhưng nhánh tối ưu bị tắt. Chỉ tắt option này cho
một thí nghiệm khác có golden/review riêng, không dùng để tự bật ADC-live.
Log `ECG_KERNELS reference_active=1 esp_nn_effective=0` xác nhận lựa chọn build.
Golden chạy 3 warm-up và 30 lượt/mẫu, recopy/check input mỗi lượt, ghi cold_code,
warm_exact, stable_exact, LSB và class_match. Mọi lượt phải khớp reference; lỗi
vẫn chặn live và SIGNAL_INVALID. Không nới dung sai để ép PASS.

Sai khác do người dùng báo: sample2 -61 thay vì -66 (5 LSB), sample5 0 thay
vì 7 (-7 LSB). Output scale=1/256, zero=-128: sample5 thực tế0.5 so với
reference0.52734375, nên đổi từ PVC sang Normal ở threshold0.52. Sample2
0.26171875 so với0.2421875, cả hai vẫn dưới ngưỡng. Kernel-selection mismatch
là nguyên nhân cấu hình đã xác định; chưa chứng minh operator cụ thể hoặc
golden trên board đã hết sai khác cho tới khi có log bản sửa.

`CONFIG_ECG_HARDWARE_SELF_TEST` (menuconfig, mặc định y) cho phép kiểm tra LED23/
buzzer25 **độc lập AI**, kể cả golden FAILED. Một lần lúc boot: LED2s/còi tắt,
rồi6 chu kỳ cùng ON150ms/OFF350ms, cuối cùng tắt; sau đó trả về trạng thái AI.
Task alert ưu tiên2 chạy state machine theo timestamp, sampling không phải
chờ hoặc delay. Các log có tiền tố `ALERT_TEST` và
`source=HARDWARE_SELF_TEST not_ai=1`. Trong cửa sổ kiểm thử rõ ràng này physical
output là bài test phần cứng, không phải cảnh báo AI. Hết test, SIGNAL_INVALID
lại bắt buộc LED/còi tắt, WAITING/NORMAL sáng/tắt, PVC nhấp nháy/bíp.
Không thể bật đồng thời golden alert demo qua menuconfig khi hardware test bật.

Không flash tự động. Phải xem golden bản mới có EXACT_MATCH cho đủ12 mẫu,
đặc biệt sample2/5, trước khi kết luận lỗi inference đã được xác nhận khắc phục.
Trạng thái live vẫn mặc định disabled và detector R chưa kiểm chứng.

## Trạng thái bàn giao ban đầu (lịch sử, xem báo cáo sửa golden mới)

Đã tạo code tích hợp model INT8 thật, ADC, phân đoạn thử nghiệm, quality gate
và bốn trạng thái. **Chưa build/link hoặc chạy firmware tích hợp trên board.**
Môi trường Codex không activate được IDF vì thiếu
`C:\Espressif\espidf.constraints.v5.4.txt`; không cài lại hoặc bỏ qua kiểm tra.

Kiểm tra đã thực thi:

- Unit test C++ dùng các dãy số kiểm thử (không phải ECG giả để báo độ chính xác):
  rail/flat/noise/gap, cửa sổ center ở index128, hai cực tính detector.
- Compiler Xtensa `-fsyntax-only` cho bốn file cpp, cả live/demo bật và tắt;
  dùng include/config cache của hai project tham chiếu. Không thay cho build.
- SHA256 bản model/golden copy và hash các file nguồn cũ không thay đổi.

**Mặc định phân loại ADC trực tiếp bị khóa**: chưa có detector R đã kiểm chứng
trong repository. Bật `ECG_ENABLE_EXPERIMENTAL_LIVE` chỉ để thử nghiệm bằng
nguồn điện tử phù hợp, không phải xác nhận khả năng phát hiện PVC trên người.
Golden tests tự chạy trước khi cho phép bất cứ live inference nào. Nếu model
hoặc golden không khớp, trạng thái SIGNAL_INVALID và live bị chặn.

## Đã xác định từ pipeline huấn luyện thực tế

`python/05_build_dataset.py`:

- MLII được chọn theo tên kênh; N=0, V=1. Đầu ra sigmoid là điểm lớp PVC.
- Resample `resample_poly(25,36)` từ 360 về 250 Hz, có anti-alias của resampler.
  Không có band-pass/notch ECG riêng, phát hiện R hay đảo cực trong code training.
- Mốc là vị trí annotation MIT-BIH, **không phải kết quả detector runtime**.
- Mốc mới: `(sample*25+18)//36`. Slice `[center-128, center+128)` có center
  index128, 128 mẫu trước và 128 mẫu từ mốc (mốc+127 là mẫu cuối).
- Population z-score float64, mẫu số `max(std,1e-8)`, rồi float32. Firmware
  làm tương tự; window hằng được reject thay vì đưa mẫu không tin cậy vào AI.
- Quantize float32 normalized bằng round ties-to-even giống np.rint, clip INT8.
  Dequantize output với scale/zero thực tế, so sánh score float với **0.52**.
- IO/model checksum đối chiếu metadata từ Bước 8, không tự đổi model/threshold.
  Score sigmoid không được coi là xác suất đã calibrated.

ADC raw và MLII mV khác đơn vị; z-score bất biến với biến đổi tuyến tính dương
nhưng **không** khắc phục thay đổi chuyển đạo, đảo cực, analog filter, nhiễu,
sampling clock, clipping hay lệch mốc. Không đổi raw ADC thành PVC bằng ngưỡng ADC.

## Kiến trúc và tài nguyên

- `main.cpp`: bản sao phần ADC đã có, giữ GPTimer 1MHz/4000tick, ADC1 channel6,
  12 bit/12dB, timestamp, LO, buffer256, summary/checksum và format ADC_BUFFER.
  Thêm hook kiểm tra an toàn từng mẫu và copy block bất biến vào queue2 không chờ.
- Sampling priority10/core1; không Invoke, UART hay vTaskDelay trong hot loop.
  Startup gate/ISR vẫn dùng task notification. Queue full không chặn ADC, nhưng
  vô hiệu hóa luồng xử lý và reset detector. `id_gap` trong ADC_BUFFER là gap
  summary; gap processing có reason riêng, không nhập nhằng hai loại.
- `pipeline.cpp`: worker priority4/core0, arena TFLM internal mặc định64KiB,
  stack12KiB; alert priority2/core0, stack4KiB; logger sampling priority3.
  Các con số này là **cấu hình**, không phải số RAM/stack sử dụng đã đo.
- `model.cpp`: nhúng binary flash, 7 operator như project B. Kiểm tra checksum,
  schema, shape, dtype, IO quantization, golden trước live. Chỉ một worker dùng
  interpreter. Đo thời gian riêng cho Invoke.
- `signal.cpp`: kiểm tra chất lượng và ring512 giữ các mẫu quanh mốc, không
  lấy tùy ý một block làm nhịp. R-window có thể đi qua biên block.
- Critical section chỉ bảo vệ metadata trạng thái; không ADC/UART/AI trong đó.
  Generation thay đổi khi invalid/recovery: kết quả inference từ generation
  cũ bị loại, không bật cảnh báo cũ sau khi leads vừa đứt.
- Task alert kiểm tra trạng thái mỗi20ms; leads/error được sampling ghi nhận
  mỗi mẫu. Không giữ NORMAL/PVC qua invalid. Độ trễ thực tế còn phụ thuộc scheduler.

Queue copy và tài nguyên CPU/RAM vẫn có overhead: **không bảo đảm 0 mất mẫu chỉ
từ kiến trúc**. Cần log actual_hz/late/missed_est/heap/stack trên board tích hợp.

## Bốn trạng thái (không dùng trạng thái thứ năm)

| State | LED23 | Buzzer25 | Ý nghĩa |
|---|---|---|---|
| WAITING | sáng | tắt | đang thu/chưa có nhịp được phép kết luận |
| NORMAL | sáng | tắt | model vừa phân loại N trên nhịp thử nghiệm |
| PVC | nhấp nháy150ms ON/350ms OFF | theo LED | giữ tối thiểu2s, không chặn sampling |
| SIGNAL_INVALID | tắt | tắt | leads-off/lỗi/timing/quality; không publish AI |

Sau PVC hold hết hạn chuyển WAITING nếu chưa có kết quả mới. NORMAL quá2s
không có kết quả mới cũng chuyển WAITING. Invalid luôn hủy hold. NORMAL đến
trong thời gian hold không bị in nhầm thành PVC mới với score Normal.
Log `ECG_AI` chỉ là kết quả thật từ model; các chuỗi minh họa trong yêu cầu
không được dùng làm dữ liệu. Không tự kích hoạt còi lúc boot theo self-test cũ.

## Quality gate — cần hiệu chỉnh/kiểm chứng

Các ngưỡng là **heuristic kỹ thuật**, không xuất phát từ validation lâm sàng:

- LO+ hoặc LO− =1: LEADS_OFF, phát hiện trên từng mẫu.
- Raw <=16 hoặc >=4079: ADC_SATURATION, margin ~0,4% full scale (configurable).
- ADC lỗi, skipped slot, khoảng read <2ms hoặc >6ms: SAMPLE_GAP/discontinuity.
- Sau invalid cần ít nhất512 mẫu sạch (~2,048s) để thu lại; detector reset.
- PTP block <20 counts (~0,5% full scale): FLAT_OR_TOO_SMALL (configurable).
- Mean abs consecutive difference >25% PTP: HIGH_FREQUENCY_NOISE (configurable).
  Đây là tỷ số thô bắt nhiễu biến thiên nhanh, **không** chứng minh SNR/ECG sạch.
- Checksum/buffer/queue gap hoặc quá tải: invalidate/reset; không nội suy.
- Inference lỗi, window hằng, input INT8 bị clip: invalid, không tự thay scale.
- Sampling không cập nhật >20ms: SAMPLING_STALLED; kết quả beat quá1,5s bị loại.

Không thể phát hiện mọi dạng artifact, chuyển động, nhiễu chậm hoặc lead sai
chỉ bằng các kiểm tra này. `lo_any=0` không chứng minh ECG hợp lệ.

## Detector thử nghiệm, mặc định OFF

Chỉ nhánh phát hiện mốc dùng baseline EMA (alpha0.01), magnitude tuyệt đối,
envelope EMA alpha0.01; chọn local maximum vượt max(30 counts,2.5*envelope),
warmup500 mẫu, refractory75 mẫu (300ms). Morphology đưa vào CNN **không bị lọc
EMA, không đảo cực**, lấy raw rồi z-score. Candidate chờ đến center+127 trước
khi cắt nhịp; window bắt đầu center−128. Pending peak quá gần làm invalid.
Không thấy peak tin cậy sau warmup/timeout cũng invalid.

Đây chưa phải bộ QRS detector được benchmark. Có thể nhầm T-wave/noise, bỏ
nhịp nhỏ hoặc nhịp nhanh; refractory và pending window làm hạn chế nhịp gần.
Phát hiện magnitude hỗ trợ định vị hai dấu **không** chứng minh CNN hỗ trợ
đảo cực. Không gọi toàn bộ pipeline tương đương annotation MIT-BIH.

Để tháo khóa live có cơ sở: replay tín hiệu benchmark qua detector, đo sai số
mốc với annotation, precision/recall R, thử artifact/đảo cực/nhịp gần, so sánh
window và normalize/quantize với Python, sau đó kiểm thử nguồn điện tử vào ADC.
Chưa làm các phép đo này trong phiên Codex. Không nối người để thay kiểm thử.

## Build từ ESP-IDF Terminal v5.4.4

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
idf.py --version
idf.py set-target esp32
idf.py build
idf.py size
idf.py size-components
```

Component Manager dùng manifest và lock đã sao chép: esp-tflite-micro1.4.2,
esp-nn1.3.0. Không sửa hai managed_components nguồn. Dependency của project
mới chưa được resolve/build trong phiên này. Giữ lock nếu IDF cập nhật khi build.

`idf.py menuconfig` → **Integrated ECG experimental prototype**:

- Live experimental mặc định OFF; khi quality không báo lỗi, log
  `WAITING reason=R_DETECTOR_UNVALIDATED_LIVE_DISABLED`.
- Golden alert demo mặc định OFF. Chỉ bật khi muốn Test1 LED/buzzer bằng dữ
  liệu tĩnh: log `ECG_TEST source=STATIC_GOLDEN_DATA ... not_live=1`, demo N/PVC
  2s mỗi trạng thái sau khi golden pass. Trong demo, output là kiểm thử phần
  cứng có chủ đích, không biểu diễn tình trạng leads/ADC; sau demo trở lại
  quality gate. Không bật demo khi đánh giá cảnh báo live.
- Arena/rail/PTP/noise/peak threshold có thể điều chỉnh, phải ghi config thí nghiệm.

## Thứ tự kiểm thử bắt buộc (chưa thực thi trên board tích hợp)

1. **Golden trước ADC-live**: mọi `ECG_GOLDEN` phải EXACT_MATCH, gồm cả score,
   code và predicted giống Python/projectB. Golden có cả FP/FN từ model gốc:
   không ép predicted bằng true label. Demo alert chỉ khi đủ reference N/PVC
   và mọi output khớp. Mọi sai khác kernel đều khóa live, cần rà soát, không ép PASS.
2. **Quality**: không nối điện cực vào người; kiểm tra LO hở, rail/flat/noise,
   mất mẫu, collecting. Phải thấy SIGNAL_INVALID hoặc WAITING phù hợp, không
   có kết quả live mới. Reset lỗi và quan sát quá trình recovery; không dùng
   các ca này để kết luận clinical validity.
3. **Bench replay experimental**: chỉ sau Test1 và kiểm chứng detector; tắt
   demo, bật experimental bằng menuconfig cho nguồn tín hiệu thử phù hợp.
   Xem `ADC_BUFFER`, `ECG_STATUS`, `ECG_AI`, `ECG_BEAT` và đo heap/stack/arena.
   Kiểm tra invalid giữa lúc Invoke không thể bị kết quả cũ ghi đè; xác nhận
   hiện tượng buzzer2s không làm tăng missed_est/late so với baseline.

Chưa flash; chỉ flash cổng COM thật sau khi bạn xác nhận. Không có kết quả
phần cứng/log/latency/RAM hoặc clinical accuracy giả trong project này.

## Unit/static checks tái chạy

```powershell
g++ -std=c++17 -Wall -Wextra -Werror -I tests -I main tests/signal_test.cpp main/signal.cpp -o tests/signal_test.exe
.\tests\signal_test.exe
python tests/check_xtensa_syntax.py
```

Unit tests dùng numerical fixtures, không thay golden ECG thật hoặc hardware.
Syntax script cần cache compile_commands của hai project nguồn; chỉ đọc chúng.
Xem `tests/xtensa_syntax_results.json`, `integration_report.json` để biết giới hạn.

Prototype nghiên cứu, chưa chứng nhận chẩn đoán/cảnh báo y tế. Chưa thử bệnh
nhân mới, không đảm bảo phát hiện PVC ngoài nguồn kiểm thử đã xác minh.
