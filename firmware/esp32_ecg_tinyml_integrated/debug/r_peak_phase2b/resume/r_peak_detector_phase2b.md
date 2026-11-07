# Giai đoạn2B — R-peak và AI end-to-end

**Chưa đạt nghiệm thu; AI-live LOCKED.** Detector cải thiện nhưng record121 chưa
đạt PPV. Golden/corpus cũ PASS; parity mở rộng phát hiện16 output code khác.
Không mở COM3/flash/train; không thay model/weights/golden/CNN threshold0,52,
preprocessing,telemetryv2,GUI,GPIO,signal-quality/FSM hoặc khóa live.

## Thay đổi và cách chọn

Chỉ source firmware `main/signal.h/.cpp`: giữ nguyên toàn bộ code `BeatWindowBuffer`
2A (so sánh byte đoạn hàm), FIFO4/ring512/raw256/index128 không đổi.
Baseline detection EMA0,01→0,025 để bám baseline drift nhanh hơn; envelope0,01,
floor30, multiplier2,5, refractory75 và warm-up500 giữ nguyên.
Thêm xác nhận hữu hạn50sample=200ms: giữ local maximum đầu, chỉ thay khi đỉnh sau
mạnh hơn1,5lần trong khoảng đó. Tránh P/đỉnh giả yếu khóa refractory trước QRS,
đồng thời không trượt sang lobe muộn chỉ cao hơn một ít. Enqueue sau xác nhận;
cửa sổ vẫn trả ởcenter+127, không thêm200ms lên độ trễ508ms vốn có.
No-peak vẫn phát issue an toàn một lần, nhưng không reset nội bộ/khởi động lại
500sample chỉ do thiếu đỉnh; **worker invalid/recovery vẫn giữ nguyên và có thể
reset từ ngoài**. ADC ngoài range hoặc timestamp gap bị reject ngay.

Tham số chọn trên6 **Train** record105,106,114,119,208,219 (không dùng Test).
Đã loại thử nghiệm curvature vì FP/FN rất xấu trên Train; giữ nguyên fiducial
magnitude. So sánh3 cấu hình confirmation, rồi3 tỷ lệ replacement trên Train;
chọn macro-F1, tie theo sensitivity. Các plan/results ở `debug/r_peak_phase2b/`.
Đã nhìn Validation trong quá trình phát triển (bản giữ mạnh nhất làm xấu214,
cho thấy rủi ro dời sang lobe muộn), nhưng **không chọn tham số bằng score
Validation**. Validation dùng lại nên kết quả vẫn khám phá, không đánh giá độc lập.
Không dùng XQRS hay lọc waveform đưa vào CNN. Không sửa tham số tiếp để cứu121.

## Detector: cùng7 record/annotation/matching ±12sample=48ms

Baseline2A được biên dịch lại từ snapshot và khớp từng score trước so sánh.
Cùng MLII, resample25/36, round-half-up, ADC bench2048+200counts/mV, BEATS cũ,
giữ startup/end FN và toàn bộ record. Không đổi tolerance/criteria/split.

| Record | TP/FP/FN 2A | TP/FP/FN 2B | Sensitivity2B | PPV2B | Tiêu chí cũ |
|---|---:|---:|---:|---:|---|
| 115 | 1939/12/14 | 1949/1/4 | 99.7952% | 99.9487% | PASS |
| 118 | 2256/23/22 | 2267/12/11 | 99.5171% | 99.4735% | PASS |
| 121 | 1781/65/82 | 1845/20/18 | 99.0338% | 98.9276% | FAIL |
| 210 | 2623/16/27 | 2635/5/15 | 99.4340% | 99.8106% | PASS |
| 214 | 2251/9/11 | 2253/4/9 | 99.6021% | 99.8228% | PASS |
| 233 | 3064/4/15 | 3068/2/11 | 99.6427% | 99.9349% | PASS |
| 234 | 2740/7/13 | 2749/1/4 | 99.8547% | 99.9636% | PASS |

Tổng16838 reference: TP16654→16766, FP136→45, FN184→72;
sensitivity98.9072%→99.5724%; PPV99.1900%→99.7323%.
N: 98.8179%→99.6687%;
V: 98.0784%→98.3859%.
Record118 và210 đã đạt;121 còn20FP/18FN, PPV98,9276%<99% nên **FAIL**.
FN theo annotation:37N,21V,8R,4L,1a,1F. Không có ambiguity reset, queue full,
duplicate/out-of-order; pending cuối2 cửa sổ chưa đủ tương lai, không padding.
Flat và pure50Hz30s đều0 peaks/0 safe windows; thiếu QRS vẫn báo issue, không
được diễn giải thành NORMAL. Gate rail/flat/noise/timing/lead-off không bị nới.

## End-to-end offline: R → raw256 → C++ preprocessing → native INT8 → threshold0,52

Harness xuất **window thực từ class C++**, assert từng raw sample/timestamp/thứ
tự; không cắt lại theo annotation để làm đẹp CNN. Native kernels và chuẩn hóa
thật được chạy, int8 input so với Python byte-for-byte. Cả2A/2B dùng cùng harness.
Primary report dưới đây dùng **safe host mirror**: block-quality/recovery2block,
reset khi issue, abstain khi quantization clipping rồi reset/recover. Đây là
offline chain, không phải chứng nhận worker/generation/FSM/RTOS hay thiết bị.
Clipping được preflight trong harness để không chạy CNN cho window sẽ bị loại;
firmware thật hiện Invoke trước rồi loại score — chính sách output tương đương,
nhưng không giả là cùng số lần Invoke hay cùng latency.

16838 reference mọi loại; mục tiêu binary có11167N+1301V=12468. Có
**16777 window formed**,2 window clipping bị loại; **16775 window
thực đưa qua CNN trong safe mirror**. **Không dùng tổng window làm
denominator accuracy**: matched N/V=12378, matched loại khác
=4352, unmatched predictions=45.
Loại khác (L/R/A/F/...) được liệt kê trong JSON, **không tự gán thành N**.
Miss trước CNN: **66N +24V**,
bao gồm detection/gate/clipping/recovery; không ẩn các nhịp đó.

Confusion matrix **chỉ matched N/V đủ điều kiện** (row=true, column=predicted):

| | Pred N | Pred V |
|---|---:|---:|
| True N | 10673 | 428 |
| True V | 136 | 1141 |

False classification matched N/V=564:
428 N→PVC và136 PVC→N. Accuracy có điều kiện=95.4435%.
Unmatched QRS tạo thêm24 dự đoánN và
21 cảnh báoPVC. Những giá trị này tách khỏi
false classification của nhịp có annotation đúng loại.

| Lớp | Precision matched | Recall matched | F1 matched | Precision có unmatched FP | Recall toàn reference N/V | F1 gồm miss/unmatched |
|---|---:|---:|---:|---:|---:|---:|
| N | 98.7418% | 96.1445% | 97.4258% | 98.5230% | 95.5763% | 97.0273% |
| V | 72.7215% | 89.3500% | 80.1827% | 71.7610% | 87.7018% | 78.9346% |

Metric nghiêm hơn cộng miss trước CNN vào FN, unmatched predictions vào FP;
matched các loại ngoài N/V vẫn **ngoài phạm vi binary**, không phải precision
lâm sàng trên mọi nhịp. 2A→2B strict PVC recall
87.3943%→87.7018%,
F178.6035%→78.9346%.
Detector tốt hơn chưa giải quyết nhầm lớp của CNN; **parity không phải accuracy**.
Chưa có tiêu chí nghiệm thu classification định trước nên không tự tạo ngưỡng
PASS mới; số precision/recall hiện tại không đủ để đề xuất bật live.

Latency: center→window-ready508ms; annotationN/V→ready median
508ms, p95
512ms trên replay250Hz. Native host
batch trung bình0.1145ms/window
**bao gồm process/I/O**, không phải Invoke/WCET ESP32 và không cộng hai clock
để giả latency board. Scheduler/inference/queue delay trên ESP32: PENDING.

## Regression, tài nguyên và giới hạn mới

- Golden host **12/12 EXACT**,33 lần/mẫu; corpus cố định **9425/9425 parity**,
  0 preprocessing byte/0 output code khác. Source model/kernel/preprocessing giữ SHA.
- Mở rộng so TensorFlow trên **33586 window mới** (candidate+safe, có cửa sổ trùng
  giữa hai đường): **16 code khác,8 record/center duy nhất, tối đa4LSB**,0 quyết
  định khác tại0,52. Có cảN/V vàL/R, không chỉ nhãn ngoài binary.
  **FAIL exact parity**, không nới tolerance. Preprocessing input đã khớp;
  khác biệt nằm sau input quantized trong native CNN/reference, chưa xác định
  operator đầu tiên. Không sửa kernel/golden/weights trong nhiệm vụ detector.
  Chi tiết ở `new_window_parity.json`; classification matrix trên dùng native.
- **55 Python +14 operator-trace tests PASS**, C++ signal/safety/lead-off/UART
  codec/confirmation/no-peak/invalid ADC/timing/FIFO/wrap/full/reset PASS.
  Test2A cũ giữ nguyên và chạy frozen; bản current copy vẫn kiểm FIFO4/full/order,
  chỉ đổi expectation occupancy1..2 do enqueue muộn và thời điểm reset fixture
  sau xác nhận. Đây không phải nới tiêu chí score detector.
- Cả2 build **ESP-IDF5.4.4 PASS**: hardware317328byte,
  synthetic315888byte; log trong debug2B. Không flash.
- Xtensa sizeof detector6448→6496byte (**+48byte**); FIFO6336byte không đổi.
  Host median ns/sample RR400ms
  10.367→11.129;
  không allocation/task mới, không chặn ADC. CPU/heap/stack/WCET board PENDING.

## Kết luận và file

Detector: **FAIL121**; exact parity mở rộng: **FAIL**; golden/corpus cũ/regression/
build: **PASS**; hardware: **PENDING**. Chỉ phù hợp thử bench/simulator với live
vẫn khóa khi có yêu cầu riêng; **chưa đủ bằng chứng để tiến tới AI-live hoặc đề
xuất mở khóa**. Cần xử lý FP121, debug operator cho8 input mismatch, xác lập tiêu
chí classification và kiểm thử phần cứng/signal-quality độc lập.

Source chính: `main/signal.h/.cpp`; harness/test mới `tests/detector_phase2b_*.cpp`,
`tests/beat_window_phase2b_test.cpp`; scripts phát triển/đánh giá/báo cáo dưới
`tools/ecg_monitor/*phase2b*.py`. 66 file bảo vệ khớp SHA;
snapshot2A ở `debug/r_peak_phase2b_before`, diff/log/input/predictions ở
`debug/r_peak_phase2b`. Báo cáo2A/GUI/telemetry cũ không bị ghi đè.
Máy đọc: `debug/r_peak_phase2b_results.json`. Không tạo biểu đồ mới.
