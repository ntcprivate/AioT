# Audit và kết quả hệ thống - 2026-11-06

Đã triển khai phần monitor/telemetry và kiểm chứng offline; **chưa hoàn thành
phát hiện PVC live đã được xác minh**. Không coi build hoặc golden PASS là đủ
để mở khóa. Báo cáo máy đọc: `debug/system_completion.json`.

## Bảng kiểm toán

| Thành phần | Bằng chứng/trạng thái | Thay đổi/tiêu chí còn lại |
|---|---|---|
| ADC/GPTimer | ISR chỉ notify; ADC12bit/GPIO34, actual timestamps,256 mẫu; user báo250Hz ở revision trước | Giữ thuật toán/tần số/Sample layout; thêm producer telemetry bounded. Timing cùng TX trên board mới PENDING |
| Buffer/queue | Sampling sở hữu buffer; summary checksum, immutable value-copy, independent recompute | Giữ kiểm tra; telemetry không cho logger đọc buffer đang ghi; queue drop phải hiện counter |
| Lead-off | LO+27, LO-26, INPUT/no internal pulls, active HIGH | Giữ gate từng mẫu; đổi mapping không đổi OR; AC/DC module chưa đo trong phiên này |
| Quality | Rail margin16, min PTP20, max mean-diff/PTP25% | Không nới threshold. Thêm clipping/PTP/diff, DFT50Hz/variance, baseline delta; metrics không chứng nhận ECG |
| Nhiễu50Hz | Chu kỳ5 mẫu tại250Hz tương ứng50Hz; sine test kích hoạt HIGH_FREQUENCY_NOISE | Chưa có capture hardware đầy đủ để làm PSD; first10 không đủ. Tool CSV/PSD đã có |
| Filter | Training không notch/bandpass mới trước model; chỉ resample_poly25/36 khi tạo dataset | Offline notch/bandpass thử trên synthetic và12459 cửa sổ nhãn; không áp dụng CNN vì đổi morphology/alignment |
| R detector | EMA baseline/envelope alpha0.01, magnitude local max, threshold max(30,2.5*envelope), warmup500, refractory75 samples | FAIL sensitivity78.55%; chưa có RR search-back/T-wave rejection đủ tin cậy. Không tuyên bố đã hoàn thiện detector |
| Beat window | [center-128,center+128),256 mẫu, center tại128; đợi đến center+127 | Host index/polarity/timestamp-boundary tests PASS; runtime detector center vẫn chưa đạt |
| Preprocessing | Float64 population mean/std, float32 normalized, ties-to-even INT8 | Factored nguyên thuật toán vào preprocessing.h;9425x256 byte parity PASS. Không đổi dữ liệu/model |
| CNN |12 golden exact,33 lần lặp/mẫu ổn định trên host; sample5 toàn16 tensors exact | Giữ golden reference strict; thêm per-channel FC rounding adapter sau chứng minh số học |
| Extended chain |9425 matched N/V windows: C++ preprocessing và TFLM codes = TF2.21 CPU builtin | Component parity PASS; không phải full end-to-end accuracy, không bao gồm missed/false peaks; Test không sử dụng |
| FSM | Trước đây WAITING và NORMAL đều LED ON; model fault có thể bị signal recovery che | Tách pattern, latch fault,2 quality-block recovery, giữ generation check; board transition timing PENDING |
| Telemetry | Protocol1, CRC32, actual timestamp32 samples/batch, sequence/boot IDs | Host parser/load tests PASS; khoảng50% UART capacity; board CPU/heap/stack/loss PENDING |
| GUI Windows | PySide6/PyQtGraph, DEMO/HARDWARE/AI TEST locked, CSV/analysis | Qt offscreen rendering/performance và safety tests PASS; chưa mở COM trong phiên này |

## Truy vết các hiện tượng

`WAITING/R_DETECTOR_UNVALIDATED_LIVE_DISABLED` là chủ đích của nhánh Kconfig
khóa live, không phải lỗi ADC. Bản mới còn có kLivePipelineValidated=false và
classification_allowed để một thay đổi config đơn lẻ không đủ mở khóa.

`HIGH_FREQUENCY_NOISE` tính `100*mean(abs(diff))/PTP >25`. Không phải bộ nhận
dạng50Hz; một sine50Hz tại250Hz có biến thiên lớn nên có thể bị loại. Test
native xác nhận điều đó. Chỉ PSD từ full samples mới định lượng phổ thật; chưa
đủ bằng chứng quy lỗi điện lưới cho capture hiện trường cũ.

`WAITING/COLLECTING` cũ có thể xuất hiện sau512 mẫu không chạm rail dù quality
block trước đó thất bại, rồi bị block quality loại lại. Bản mới cần cả512 mẫu
tốt và hai block chất lượng liên tiếp trước phục hồi. Mất điện cực, clipping,
ADC lỗi, gap vẫn invalid ngay; không đợi debounce. Lỗi model/GPIO/init/queue
corruption có SYSTEM_FAULT sticky, không bị healthy ADC xóa.

LED nhấp nháy rồi sáng liên tục trước đây do hardware self-test2 giây +6 blink,
sau đó WAITING được định nghĩa LED ON giống NORMAL. Đã tách pattern và xuất
SELF_TEST độc lập. Không có kết quả live thì không có NORMAL. Không suy luận
sức khỏe từ LED hoặc ADC hoạt động.

Trong lúc golden chạy, worker cũ chưa nhận queue nên có thể báo PROCESS_QUEUE_FULL
lúc khởi động. Bản mới không enqueue AI blocks trước model_ready; ADC telemetry
và instant safety vẫn chạy. Quality result của buffer cũ chỉ cập nhật khi
generation còn khớp, tránh ghi đè một lead-off mới xảy ra trong lúc xử lý.

## FSM và output

| State / điều kiện | LED | Buzzer | Chuyển trạng thái |
|---|---|---|---|
| SELF_TEST,5 giây đầu nếu bật |2 giây ON, sau đó6 lần150ms ON/350ms OFF | Chỉ6 beep trong pha blink | Physical override được nhận diện, không xóa AI/signal fault |
| WAITING,AI locked/no result |1Hz,50% | OFF | Thu thập/quality quyết định trạng thái kế |
| COLLECTING |80ms pulse mỗi giây | OFF | Chờ hai good blocks hoặc nhịp đã được xác minh |
| SIGNAL_INVALID |~3Hz | OFF | Phục hồi chỉ sau điều kiện2 blocks/512 samples; danger reset ngay |
| NORMAL | ON | OFF | Chỉ publish valid/fresh/live/generation đúng; quá2s trở WAITING |
| PVC |150ms ON mỗi500ms | Theo LED | Chỉ publish hợp lệ; latch2s, danger/fault hủy ngay |
| SYSTEM_FAULT |2 pulse100ms cách nhau250ms, mỗi2s | OFF | Sticky; cần sửa nguyên nhân/reboot có chủ đích |

Priority logic: SYSTEM_FAULT > instant SIGNAL_INVALID > valid PVC latch >
fresh NORMAL > COLLECTING/WAITING. SELF_TEST là override output độc lập, state
AI bên dưới giữ nguyên, không tạo một kết quả AI giả. Task output20ms/core0,
không delay ADC. C++ system_test kiểm tra patterns, recovery và64 tổ hợp gate.

## R-peak: FAIL có số liệu, không mở live

Record Validation giữ nguyên:115,118,121,210,214,233,234. Native detector nhận
MLII resample360→250; tạo representation ADC=round(2048+200*mV), không phải
hiệu chuẩn AD8232. Match một-một trong12 samples (~48ms), annotations QRS thật
(không lấy marker rhythm làm nhịp). Warm-up và boundary FN vẫn tính.

Tổng candidate: TP13226,FP90,FN3612, sensitivity78.55%, PPV99.32%. Record233 chỉ
~31.28% sensitivity,214 ~71.57%,210 ~77.77%. Cần99% sensitivity/99% PPV **mỗi
record** và95th-percentile timing≤40ms, flat/50Hz controls không false peaks.
Chưa đạt; không tự tune threshold trên Validation để gọi PASS. N/V matched và
missed counts, timing từng record, quality-gated mirror và ECG+synthetic50Hz
được ghi trong `tools/ecg_monitor/reports/offline_validation.json`.

Hướng tiếp theo: triển khai candidate detector streaming có QRS-specific
bandpass/energy + adaptive signal/noise threshold, RR/search-back/T-wave và
refractory phù hợp; bù trễ để center vẫn đúng input128. Phát triển trên Train,
đánh giá Validation theo record/patient grouping đã có, rồi independent final
evaluation. Cần kiểm tra phase/detector shift và simulator/hardware trước mở
gate. Không coi hai record chắc chắn là hai bệnh nhân khác nhau.

## CNN: mở rộng kiểm tra và sửa có bằng chứng

12 golden ban đầu không bao phủ hết mọi trường hợp làm tròn. Với9425 cửa sổ
mới, bản Conv-only trước đó còn9 code mismatch, max3LSB, không đổi nhãn tại0.52
trong nhóm này. First divergence ở op13 FULLY_CONNECTED per-channel, không phải
input/CONV/MEAN: channel4 accumulator2663, multiplier1380248877,shift-5,
exact scaled53.4870597853; double rounding cho54, single53, zero-128 → -74/-75.

`single_round_fc.cpp` giữ nguyên vendor init/prepare/quantization, thay riêng
per-channel Eval bằng vendor loop với helper single-round. Per-tensor FC và
MEAN giữ stock double rounding. Không thay model, reference, threshold, không
offset theo sample. Bằng chứng trước sửa: `reports/offline/fc_arithmetic_diagnosis.json`,
`extended_parity_mismatches.json` trong thư mục monitor. Sau sửa9425/9425 codes
khớp TF2.21 no delegate;12 golden x33 repeats và16 tensors sample5 vẫn exact.

Validation reused nhiều lần nên số đo chỉ mang tính khám phá. 9425 windows đã
loại missed/false/nhãn khác, không dùng confusion matrix của nhóm này để tuyên
bố full-system accuracy. Full pipeline chưa PASS do detector FAIL và thiếu
hardware validation. User báo golden12/12 trên board trước đây; binary mới
trong phiên này **chưa flash**, nên chưa xác nhận board golden mới.

## Tái lập host tests

Từ firmware integrated, với g++ và Python trên PATH:

```powershell
g++ -std=c++17 -Wall -Wextra -Werror -I tests -I main tests/system_test.cpp main/signal.cpp -o tests/system_test.exe
.\tests\system_test.exe
g++ -std=c++17 -O2 -I tests -I main tests/detector_replay.cpp main/signal.cpp -o tests/detector_replay.exe
g++ -std=c++17 -O2 -I main tests/preprocess_host.cpp -o tests/preprocess_host.exe
python tests/run_full_host.py
python -m unittest discover -s tests -p test_trace_protocol.py -v
```

Sau đó chạy validation với môi trường monitor đã cài, xem README của ứng dụng.
Không cần TensorFlow trong firmware hoặc GUI thường ngày. Các test/benchmark
không mở COM, không flash/reset, không thay split/model/dữ liệu gốc.
