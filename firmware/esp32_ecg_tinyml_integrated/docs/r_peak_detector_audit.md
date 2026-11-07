# Kiểm toán R-peak detector — giai đoạn 1, 2026-11-06

Đã tái lập đúng baseline: **16838 nhịp tham chiếu, TP=13226,
FP=90, FN=3612; sensitivity=78.5485%, PPV=99.3241%**.
Điểm yếu chính có bằng chứng là xung đột một cửa sổ đang chờ với QRS đến sớm,
dẫn đến reset và mất thêm 2 giây khởi tạo. Chưa thay detector, CNN, preprocessing,
threshold0,52, quality gate, FSM hay sdkconfig. AI-live vẫn LOCKED; không mở COM/flash.

## 1. Source và quan hệ pipeline

Đường dẫn `main/` và `tests/` tính từ firmware này; `tools/` tính từ workspace.
Các vị trí dưới đây lấy từ source thực tế, không suy đoán tên file.

| File:dòng | Hàm/lớp | Vai trò |
|---|---|---|
| `main/signal.h:7` | `BeatDetector` | Streaming state: 512-sample raw/time ring, one pending center, EMA states |
| `main/signal.cpp:38` | `BeatDetector::push` | Baseline residual, threshold, refractory, pending window, reset |
| `main/signal.cpp:37` | `BeatDetector::reset` | Resets all state, including warm-up age and baseline |
| `main/signal.cpp:22` | `signal_block_reason` | Rail, timestamp, minimum PTP and mean-difference gates |
| `main/signal.cpp:6` | `signal_metrics` | Diagnostic DFT50/variation/baseline metrics; not detector filtering |
| `main/pipeline.cpp:171` | `worker` | Model/golden, quality/recovery, block continuity, guarded detector invocation |
| `main/pipeline.cpp:267` | `pipeline_observe` | Immediate lead-off/ADC/timing safety |
| `main/pipeline.cpp:281` | `pipeline_offer` | Immutable queued block with generation/hash |
| `main/model.cpp:98` | `model_invoke_beat` | Calls unchanged quantization and CNN |
| `main/preprocessing.h:12` | `ecg_preprocessing::quantize` | Per-beat z-score then int8 quantization; downstream of detector |
| `main/system_state.h:4` | `kLivePipelineValidated` | False; independent classification gate remains closed |
| `main/Kconfig.projbuild:58` | `ECG_ADC_RAIL_MARGIN .. ECG_QRS_MIN_COUNTS` | 16 / 20 / 25 / 30, matching tests/sdkconfig.h |
| `tests/detector_replay.cpp:8` | `main` | Historical native candidate + quality-gated host mirror |
| `tests/signal_test.cpp:10` | `main` | Synthetic polarity, ring indexing and quality controls |
| `tools/ecg_monitor/validate_offline.py:22` | `score / main` | Validation selection, resampling, historical greedy ±12 score |
| `tools/ecg_monitor/ecg_monitor/offline.py:25` | `display_filter` | Causal notch50 + bandpass preview only; not detector/CNN input |
| `python/04_extract_beats.py:25` | `main` | Record100,25/36 resample, round-half-up annotations, raw256 slice then z-score; not called by live detector |
| `python/05_build_dataset.py:37` | `extract_record` | MLII, same integer annotation mapping, raw256 slice then z-score; not called by detector replay |

ADC/GPTimer → `pipeline_observe` (lead-off/ADC/rail/gap) và `pipeline_offer`
(copy block256 + hash/generation) → worker kiểm tra continuity/quality/recovery →
**cổng live đang đóng** → nếu sau này được phép, `BeatDetector::push` → cửa sổ
raw256 → `model_invoke_beat` → z-score/quantize → CNN → cổng publish/FSM.
Hiện worker không gọi detector cho ADC-live vì cả cấu hình live OFF và
`kLivePipelineValidated=false`. Kết quả dưới đây đến từ host replay thực sự gọi
class C++, không phải từ phân loại ADC đang chạy.

**RR/BPM:** chưa có bộ ước lượng RR thích nghi hoặc RR searchback trong detector.
`last_center_` chỉ phục vụ refractory và timeout. Firmware phát `rr_ms=null`,
`bpm=null`; GUI hiển thị `-- / --`. RR trong báo cáo này là chênh lệch annotation
offline, không phải một tính năng BPM đã kiểm chứng.

## 2. Detector hiện tại

- Mỗi mẫu lưu vào ring512 kèm timestamp; EMA baseline hệ số0,01; magnitude là
  `abs(raw-baseline)`. EMA envelope của magnitude cũng hệ số0,01.
- Chọn local maximum của magnitude trước đó, khi magnitude vượt
  `max(30 ADC counts, 2.5*envelope hiện tại)`, sau warm-up500 mẫu≈2s.
  Floor30 tương đương khoảng0,15mV trong mapping bench200counts/mV; không phải
  ngưỡng đã hiệu chuẩn theo AD8232 thật. Không có riêng thống kê QRS/noise.
- Refractory75 mẫu=300ms. Không có QRS-band energy, T/P discrimination hoặc
  RR-aware searchback. Lấy trị tuyệt đối hỗ trợ hai cực tính, chưa bảo đảm xác
  định cùng fiducial R cho mọi QRS rộng/đa pha.
- Chỉ có **một `pending_`**. Đợi đến `current >= center+127` để trả slice
  `[center-128,center+128)`: đúng256 mẫu, center ở index128. Như vậy cần508ms từ
  center đến mẫu cuối, dù phần từ center có128 mẫu tính cả center.
- Đỉnh tiếp theo được chấp nhận về refractory ở khoảng75..126 mẫu
  (**300..504ms**) sẽ gặp pending cũ; nhánh ambiguity chạy trước nhánh hoàn tất
  cửa sổ, gọi `reset()` và không trả cả hai beat. Không phải mọi RR ngắn đều
  như vậy: <300ms bị refractory; từ508ms có thể đã hoàn tất cửa sổ trước.
- `reset()` xóa ring, baseline, envelope, center và count; lại mất500 mẫu warm-up.
  `NO_RELIABLE_R_PEAK` cũng reset: sau age>1000 và không có center trong>500 mẫu.
  Không có searchback thay cho reset.
- Timestamp cửa sổ phải có interval2000..6000µs. Replay dùng timestamp lý tưởng
  `index*4000`; chưa đánh giá scheduler ESP32 hay sai số clock trên board.

## 3. Tái lập baseline và tiêu chí cũ

Chỉ dùng record thuộc **Validation** từ `validation_indices` trong
`data/processed/mitbih_split_indices.npz`, tra `record_ids` của dataset cũ:
**115,118,121,210,214,233,234**. Không đánh giá Test, không loại record khó.
Mỗi record đọc đúng MLII theo `sig_name`; trong bảy record này MLII đều index0,
đơn vịmV, fs360. Không tổng quát hóa MLII luôn là kênh0.

Giữ nguyên `resample_poly(signal,25,36)`; ADC bench
`clip(rint(2048+200*signal250),0,4095)` int16; annotation
`floor(sample360*25/36+0.5)`. Dữ liệu input ADC từng record khớp SHA với replay cũ.
BEATS giữ nguyên từ `validate_offline.py`: `/?ABEFJLNQRSVaefjnr`.
Không chỉ lấy N/V khi đánh giá QRS. Nhịp khởi tạo/biên vẫn tính vào FN.

Matching giữ nguyên: duyệt reference theo thứ tự, chọn nearest trong hai hàng
xóm searchsorted chưa dùng, sai số **≤12 mẫu=48ms**, mỗi detection chỉ dùng một
lần; giữ cả quy tắc tie cũ. Không sửa tolerance, không dịch detector theo annotation.
Khớp từng dictionary score candidate và gated với `offline_validation.json` cũ;
harness có trace cho **stdout giống hệt** harness production mới biên dịch.

Tiêu chí cũ: **từng record** sensitivity≥99%, PPV≥99%, p95 sai số tuyệt đối≤40ms;
flat và pure50Hz phải có0 false peaks. Tổng tốt không thay được từng record.

| Record | Reference | TP | FP | FN | Sensitivity | PPV | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 115 | 1953 | 1935 | 11 | 18 | 99.0783% | 99.4347% | 4 |
| 118 | 2278 | 2209 | 17 | 69 | 96.9710% | 99.2363% | 20 |
| 121 | 1863 | 1741 | 50 | 122 | 93.4514% | 97.2083% | 4 |
| 210 | 2650 | 2061 | 5 | 589 | 77.7736% | 99.7580% | 4 |
| 214 | 2262 | 1619 | 2 | 643 | 71.5738% | 99.8766% | 4 |
| 233 | 3079 | 963 | 0 | 2116 | 31.2764% | 100.0000% | 36 |
| 234 | 2753 | 2698 | 5 | 55 | 98.0022% | 99.8150% | 4 |

Tổng detector thuần: 13316 detection, sensitivity78.5485%,
PPV99.3241%. **FAIL**, giữ khóa live. Record233 đóng góp2116/3612 FN≈58,58%.
Quality-gated mirror: TP=13215, FP=90, FN=3623,
sensitivity=78.4832%, PPV=99.3236%.

### Theo loại annotation

| Loại | Reference | C++ TP | C++ FN | C++ sensitivity | XQRS TP | XQRS FN | XQRS sensitivity |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 104 | 91 | 13 | 87.5000% | 104 | 0 | 100.0000% |
| E | 1 | 0 | 1 | 0.0000% | 0 | 1 | 0.0000% |
| F | 22 | 12 | 10 | 54.5455% | 19 | 3 | 86.3636% |
| J | 50 | 22 | 28 | 44.0000% | 50 | 0 | 100.0000% |
| L | 2003 | 1553 | 450 | 77.5337% | 1999 | 4 | 99.8003% |
| N | 11167 | 9165 | 2002 | 82.0722% | 11165 | 2 | 99.9821% |
| Q | 2 | 1 | 1 | 50.0000% | 1 | 1 | 50.0000% |
| R | 2166 | 2112 | 54 | 97.5069% | 2166 | 0 | 100.0000% |
| V | 1301 | 268 | 1033 | 20.5995% | 1233 | 68 | 94.7733% |
| a | 22 | 2 | 20 | 9.0909% | 18 | 4 | 81.8182% |

N có nghĩa là đúng annotation **N**, không tự gộp L/R thành N. Detector QRS chưa
phân loại N/V nên FP không có true beat-type để tính PPV riêng theo N/V; chỉ báo
PPV toàn bộ. Không gán nhãn cho FP bằng annotation gần nhất để tạo metric đẹp.
**PVC chỉ phát hiện268/1301=20,5995%**, bất chấp PPV QRS toàn bộ99,3241%.
Không suy độ nhạy PVC toàn hệ thống từ golden CNN hoặc9425 matched windows:
parity chỉ kiểm tra thành phần trên các cửa sổ đã chọn, không bù nhịp bị bỏ sót.

## 4. Bằng chứng nguyên nhân

### 4.1 Pending/reset là ưu tiên đầu

| Record | Ambiguity resets | No-peak resets | Thời gian warm-up s | FN trong reset warm-up |
|---|---:|---:|---:|---:|
| 115 | 1 | 0 | 4 | 3 |
| 118 | 13 | 0 | 28 | 32 |
| 121 | 14 | 3 | 36 | 38 |
| 210 | 135 | 0 | 272 | 378 |
| 214 | 178 | 0 | 358 | 296 |
| 233 | 445 | 0 | 892 | 1464 |
| 234 | 9 | 0 | 20 | 27 |

Tổng795 ambiguity resets và3 no-peak resets; thời gian age<500 cộng cả khởi động
là1610s trên bảy record. Trong2238 FN khi khởi tạo lại, **2229** theo sau ambiguity
và9 theo sau no-peak reset. Trace ghi trực tiếp state của class production.

Phân nhóm mô tả cho toàn bộ3612 FN (có thứ tự ưu tiên; không phải ablation causal):

| Bằng chứng gần annotation | FN | Tỷ lệ trong FN |
|---|---:|---:|
| INITIAL_WARMUP | 20 | 0.55% |
| REFRACTORY_BLOCK | 81 | 2.24% |
| ACCEPTED_THEN_RESET_BEFORE_WINDOW | 785 | 21.73% |
| RESET_WARMUP | 2238 | 61.96% |
| END_WINDOW_UNAVAILABLE | 5 | 0.14% |
| BELOW_ADAPTIVE_THRESHOLD | 39 | 1.08% |
| PENDING_CONFLICT_RESET | 444 | 12.29% |

785 center đã được nhận nhưng reset trước khi đủ cửa sổ;444 FN tại center gây
xung đột;2238 FN trong warm-up sau reset. Ba nhóm chiếm3467/3612≈95,99%, nhưng
**không có nghĩa sửa pending chắc chắn thu hồi3467 TP**: state/threshold và matching
sẽ thay đổi. Đây là vị trí chặn quan sát được, chưa phải hiệu quả của thuật toán mới.
PVC FN gồm598 warm-up sau reset,402 conflict,22 accepted rồi bị hủy,7 dưới ngưỡng
thích nghi,3 warm-up ban đầu và1 refractory. PVC đến sớm và các nhịp N sau đó đều
bị ảnh hưởng. Không chỉ là vấn đề biên độ hoặc cực tính PVC.

Microtest gọi class nguyên bản: impulse tại600 và700 (RR400ms) gây ambiguity ở701;
cả hai không được emit, count về0 ở702; impulse1000 tiếp tục bị warm-up che;
đến1300 mới trả được beat. Đây là bằng chứng quyết định, không phải kết luận từ ảnh.

### 4.2 Refractory và nhầm local peak

81 FN thuộc nhóm refractory. Không nên chỉ rút ngắn refractory rồi kỳ vọng tốt:
record115 tại **46,376s** có RR annotation trước=1048ms, nhưng detector nhận một
đỉnh sai tại **46,196s**, cách R thật180ms; R thật bị chặn. Biểu đồ cho thấy FP
trước QRS; chưa cần gọi chắc đó là P hay T wave. Bộ chọn magnitude thiếu phân biệt
hình dạng/năng lượng QRS. Có5 reference RR≤300ms trong toàn tập, đều FN; nhiều
trường hợp refractory khác xuất phát từ center trước sai hoặc khác fiducial.

### 4.3 Ngưỡng, biên độ, cực tính, RR

39 FN có local maximum dưới ngưỡng thích nghi khi không bị warm-up ưu tiên che.
Không thấy FN được phân nhóm chỉ do floor30; cực đại residual trong±12 mẫu của
mọi reference đều≥30. Điều này **không chứng minh floor phù hợp phần cứng** hoặc
loại trừ tác động ngưỡng trong nhóm reset. Microtest biên độ29 bị chặn ở cả hai
cực tính; floor là yếu tố phụ thuộc gain ADC cần hiệu chuẩn sau này.

Trị tuyệt đối không có lỗi chỉ nhận QRS dương đơn giản: test impulse± đều qua.
Nhưng dữ liệu QRS âm/PVC có sensitivity thấp (chi tiết `morphology` trong JSON).
Đó là tương quan bị nhiễu bởi RR/reset, chưa chứng minh chỉ cần đảo cực sẽ sửa.
1151 reference có RR trước trong(300,508]ms,995 FN; nhưng các center C++ thực tế
mới quyết định conflict, không được đồng nhất RR annotation với khoảng center.
Không có cơ chế RR adaptation/searchback để phục hồi khi morphology/nhịp đổi.

### 4.4 Resampling, kênh và phase

Quy đổi annotation khớp công thức số nguyên `(sample*25+18)//36`; sai số làm tròn
tối đa≈2ms, nhỏ hơn tolerance48ms. Impulse test xác minh vị trí resample trong1
mẫu so với mapping. Không phát hiện lệch fs hoặc chọn sai kênh trong replay.
`04_extract_beats.py` và `05_build_dataset.py` cũng dùng cùng quy tắc half-up;
không tìm thấy khác biệt rounding với detector replay. Z-score ở các script
dataset và `preprocessing.h` áp dụng sau khi có beat256, không tạo đỉnh QRS.
`resample_poly` mặc định dùng FIR low-pass zero-phase, giữ time origin, không
tự thêm group-delay chưa bù. Biên zero-padding vẫn cần xét ở đầu/cuối.
[Tài liệu SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html).

Detector chỉ dùng EMA baseline trên nhánh detection; causal notch50/bandpass0,5–40
trong `display_filter` **không đưa vào detector hoặc CNN**. Không thể quy baseline
FN cho delay của display filter. EMA/magnitude có thể đổi fiducial ở QRS đa pha;
p95 hiện tại là trên TP đã match, không chứng minh không còn alignment errors.
Chưa phê duyệt thay waveform/CNN preprocessing bằng filtered signal.

### 4.5 Biên buffer và quality gate

Streaming ring giữ state qua256/512 mẫu, không reset mỗi buffer. Test center511,
767,1023 qua biên thành công. Có20 FN warm-up ban đầu và5 FN thiếu phần cuối cửa
sổ; đều giữ trong denominator. Chưa có bằng chứng lỗi off-by-one cắt256 mẫu:
slice center-128..center+127 đúng với preprocessing đã kiểm chứng.

Tất cả **12341 block đầy đủ** qua quality gate, không rail clipping trong bảy
input bench. Vì vậy không có bằng chứng quality gate là nguyên nhân chính của
78,55%. Mirror gated mất14 reference vốn candidate match và lấy lại3 (net−11TP),
do admission/history đầu và phần buffer cuối; không phải14 quality rejects.
Mirror bắt đầu feed sau hai block tốt và không feed trailing block thiếu256.
Đây chưa phải mô phỏng đầy đủ worker/generation/FSM/RTOS. Gate thực còn lead-off,
rail, ADC errors/gap/queue integrity và2 block recovery; **không tắt hay nới gate**.
Power50/baseline metrics là diagnostic, không có thêm power50 gate bí mật ở đây.

## 5. Đoạn bỏ sót và biểu đồ

Tìm theo bin10s cố định không chồng lắp; không chọn lại tolerance hay loại nhãn.
Đây là top của các cửa sổ đã xếp hạng theo FN; CSV giữ top10 từng record.

| Record | Thời gian s | Reference | FN | FN N | FN V |
|---|---|---:|---:|---:|---:|
| 234 | 860–870 | 22 | 20 | 0 | 0 |
| 233 | 740–750 | 17 | 17 | 13 | 4 |
| 233 | 120–130 | 17 | 16 | 10 | 6 |
| 233 | 160–170 | 17 | 16 | 8 | 7 |
| 233 | 190–200 | 17 | 16 | 10 | 6 |
| 233 | 330–340 | 16 | 16 | 12 | 4 |
| 233 | 380–390 | 16 | 16 | 12 | 4 |
| 233 | 460–470 | 16 | 16 | 12 | 4 |
| 233 | 860–870 | 18 | 16 | 8 | 7 |
| 233 | 1170–1180 | 17 | 16 | 10 | 6 |
| 233 | 1270–1280 | 16 | 16 | 12 | 4 |
| 210 | 1080–1090 | 16 | 15 | 7 | 8 |

Ví dụ234/860–870s mất20/22 nhịp J dù sóng QRS rõ;233/740–750s mất17/17;
210/1080–1090s mất15/16, gồm8 PVC. Không dùng riêng ví dụ đẹp để chấm score.

Đã tạo19 hình offline. Mỗi hình có ECG MLII gốc360Hz và annotation, input250Hz,
center phát hiện, TP xanh/FN đỏ/FP tím, so sánh XQRS, magnitude/threshold và vùng
warm-up màu cam; đường đỏ đứt là ambiguity reset. TP/FN xác định trên toàn record
trước khi cắt hình, không matching lại theo đoạn. Marker xanh lam là detection
center; TP là annotation được match, hai vị trí có thể lệch≤48ms.

- [115 / worst10s / 1790.000–1800.000s](../debug\r_peak_audit\115_worst10s.png)
- [115 / refractory_block / 43.376–51.376s](../debug\r_peak_audit\115_refractory_block.png)
- [118 / worst10s / 740.000–750.000s](../debug\r_peak_audit\118_worst10s.png)
- [121 / worst10s / 1580.000–1590.000s](../debug\r_peak_audit\121_worst10s.png)
- [210 / worst10s / 1080.000–1090.000s](../debug\r_peak_audit\210_worst10s.png)
- [210 / pending_conflict_reset / 7.668–15.668s](../debug\r_peak_audit\210_pending_conflict_reset.png)
- [210 / below_adaptive_threshold / 496.024–504.024s](../debug\r_peak_audit\210_below_adaptive_threshold.png)
- [210 / refractory_block / 184.700–192.700s](../debug\r_peak_audit\210_refractory_block.png)
- [210 / pvc_reset_warmup / 27.756–35.756s](../debug\r_peak_audit\210_pvc_reset_warmup.png)
- [214 / worst10s / 1710.000–1720.000s](../debug\r_peak_audit\214_worst10s.png)
- [214 / pending_conflict_reset / 5.988–13.988s](../debug\r_peak_audit\214_pending_conflict_reset.png)
- [214 / below_adaptive_threshold / 296.416–304.416s](../debug\r_peak_audit\214_below_adaptive_threshold.png)
- [214 / refractory_block / 1695.128–1703.128s](../debug\r_peak_audit\214_refractory_block.png)
- [214 / pvc_reset_warmup / 145.088–153.088s](../debug\r_peak_audit\214_pvc_reset_warmup.png)
- [233 / worst10s / 740.000–750.000s](../debug\r_peak_audit\233_worst10s.png)
- [233 / pending_conflict_reset / 5.368–13.368s](../debug\r_peak_audit\233_pending_conflict_reset.png)
- [233 / below_adaptive_threshold / 908.576–916.576s](../debug\r_peak_audit\233_below_adaptive_threshold.png)
- [233 / pvc_reset_warmup / 0.076–8.076s](../debug\r_peak_audit\233_pvc_reset_warmup.png)
- [234 / worst10s / 860.000–870.000s](../debug\r_peak_audit\234_worst10s.png)

## 6. XQRS offline cùng đầu vào và cách chấm

WFDB4.3.1, `xqrs_detect(...,fs=250,learn=True,verbose=False)`, defaults,
đầu vào **(ADC bench−2048)/200 mV**, tức cùng waveform đã quantize mà C++ nhận.
Không crop startup, correction, dịch peak hay dùng annotation để tune. Thư viện
đã có sẵn, không cài mới. XQRS dùng bandpass5–20Hz, wavelet integration, học
ngưỡng/nhịp và searchback theo RR. Đây là baseline **offline** có `filtfilt`
phi nhân quả, chưa phải thuật toán streaming tương đương trên ESP32.
[Tài liệu chính thức WFDB](https://wfdb.readthedocs.io/en/latest/processing.html#qrs-detectors).

| Record | XQRS TP | FP | FN | Sensitivity | PPV | p95 ms | Tiêu chí record |
|---|---:|---:|---:|---:|---:|---:|---|
| 115 | 1953 | 0 | 0 | 100.0000% | 100.0000% | 4 | PASS |
| 118 | 2278 | 0 | 0 | 100.0000% | 100.0000% | 4 | PASS |
| 121 | 1862 | 0 | 1 | 99.9463% | 100.0000% | 4 | PASS |
| 210 | 2595 | 4 | 55 | 97.9245% | 99.8461% | 4 | FAIL |
| 214 | 2251 | 4 | 11 | 99.5137% | 99.8226% | 4 | PASS |
| 233 | 3066 | 1 | 13 | 99.5778% | 99.9674% | 40 | PASS |
| 234 | 2750 | 0 | 3 | 99.8910% | 100.0000% | 4 | PASS |

Tổng XQRS: **TP=16755, FP=9, FN=83, sensitivity=99.5071%,
PPV=99.9463%**. So với C++: TP tăng3529, FP giảm81, FN giảm3529 trên cùng
đánh giá này; chưa phải kết quả Test hoặc board. N đạt99,9821%, PVC94,7733%.

**XQRS vẫn FAIL toàn bộ tiêu chí cũ**: record210 sensitivity97,9245%<99%; ngoài ra
control pure50Hz30s có1 false peak ở sample7495=29,98s (sát biên cuối). Flat có0.
C++ có0 ở cả hai control. Không bỏ biên để cứu score và chưa kết luận chính xác
nguyên nhân peak XQRS đó; filtfilt/edge/learning là giả thuyết cần tách tiếp.
Kết quả này hỗ trợ dùng XQRS làm oracle so sánh offline, không thay detector ngay
và không dùng aggregate99,51% để mở AI-live.

## 7. Hướng sửa giai đoạn 2 để xem xét

1. **Ưu tiên tách detection khỏi hoàn tất cửa sổ**: FIFO center hữu hạn, mỗi center
   chỉ emit khi đủ128 mẫu từ center; giữ ring/state và xử lý RR ngắn bình thường
   mà không reset toàn detector. Overflow phải có fault rõ; không bỏ kiểm tra gap.
2. Nhánh QRS detection riêng có bandpass nhân quả + derivative/energy/integration
   kiểu Pan–Tompkins, hoặc biến thể wavelet/năng lượng gọn; track signal/noise
   levels, refractory và searchback có giới hạn theo RR. Đo/bù delay trên nhánh
   detection rồi localize lại trên raw ring. Không đưa signal lọc vào CNN.
3. Review P/T rejection, QRS rộng/đa pha/đảo cực và threshold phụ thuộc gain. Không
   hạ floor hoặc rút refractory hàng loạt trước khi đo FP và localization.
4. XQRS là comparator offline, không port nguyên `filtfilt`/SciPy lên ESP32.
   Chọn O(1) cập nhật/mẫu, buffer hữu hạn và báo latency/budget; chưa đo chi phí
   ESP32 nên không cam kết tốc độ/heap của thuật toán đề xuất.

File dự kiến: `main/signal.h/.cpp`, `tests/signal_test.cpp`, harness detector replay
và bài test mới về pending/RR/gap. `main/pipeline.cpp` chỉ xem xét nếu giao diện
center/window thay đổi, luôn giữ quality/generation/FSM. Script Validation giữ
nguyên matching/criteria; thêm report mà không sửa denominator.
Không dự kiến sửa model, golden, CNN threshold hay `preprocessing.h`.

## 8. Kiểm thử sau sửa và kiểm thử giai đoạn 1

Sau sửa phải chạy đúng bộ Validation/criteria cũ; báo per-record, per-label, FN/FP
đầy đủ; flat/50Hz/noisy ECG; RR sweep/premature/bigeminy, low amplitude, inversion,
wide QRS, P/T, startup/reset/buffer boundaries; multiple pending windows đúng256
mẫu và center index128; quality/lead-off/ADC/gap/recovery/generation/queue tests.
Chạy lại golden12×33, parity9425, trace/GUI/telemetry regression, build IDF5.4.4;
sau đó simulator/board với quyền riêng, đo latency/CPU/heap/stack và250Hz continuity.
Không tự chia lại data hoặc xem Test để tune. Validation đã dùng lại nhiều lần:
kết quả cải tiến chỉ khám phá, cần đánh giá độc lập thích hợp trước live approval.

Giai đoạn1: **51 Python tests PASS** (42 cũ +9 audit), hai harness C++
biên dịch `-O2 -Wall -Wextra -Werror`; trace và native event output giống nhau trên
cả7 record. Test mới xác nhận lỗi hiện tại, không dùng nó làm expected behavior
cho detector tương lai. Ba fixture ban đầu tưởng không có timeout đã lộ đúng
`NO_RELIABLE_R_PEAK`; đã tách test timeout và sửa thời lượng/khoảng xung của fixture
để cô lập mỗi nhánh. Log lần thử đó giữ tại
`tools/ecg_monitor/reports/r_peak_audit_initial_fixture_failures.log`; không sửa
source detector hay số score để làm PASS. Log cuối: `reports/r_peak_audit_tests.log`.
Không build/flash firmware ở giai đoạn chỉ phân tích. Golden12/12/parity9425 là
kết quả trước đã bảo vệ SHA, **không tuyên bố vừa chạy lại trên board**.

## 9. File tạo, cách tái lập và giới hạn

- Báo cáo này và `debug/r_peak_detector_audit.json` (source map, metrics, evidence,
  plan/test list, SHA inputs/protected files).
- `debug/r_peak_audit/`: snapshot SHA, ADC bench riêng, binary trace32byte/mẫu,
  events CSV, detections/matches NPZ, `false_negatives.csv`, `worst_windows.csv`,19 PNG,
  hai executable host. Không thay file raw/model/split/báo cáo cũ.
- Công cụ mới: `tools/ecg_monitor/audit_r_peaks.py`, `r_peak_audit_report.py`,
  `tests/test_r_peak_audit.py`; harness `tests/detector_audit_replay.cpp`.
- Bản source firmware, sdkconfig, dataset/split, threshold JSON và báo cáo cũ
  đều khớp SHA snapshot trước giai đoạn1; chi tiết `protected_checks` trong JSON.

Tái lập bằng compiler g++ và môi trường monitor hiện có, không cần train/TensorFlow:

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I main -I tests main/signal.cpp tests/detector_replay.cpp -o debug/r_peak_audit/detector_baseline.exe
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I main -I tests main/signal.cpp tests/detector_audit_replay.cpp -o debug/r_peak_audit/detector_audit.exe
Set-Location 'D:\Code Part Two\AIoT\tools\ecg_monitor'
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe audit_r_peaks.py
```

Chưa đủ dữ liệu: hiệu quả chính xác của FIFO/thuật toán mới; nguồn phân bố FP đầy
đủ theo P/T/noise; AD8232 gain/lead-off/common-mode thực; sai số board/RTOS và
CPU/memory budget; tổng quát hóa sang bệnh nhân độc lập. Morphology và RR có thể
liên quan nhưng không đồng nhất quan hệ nhân quả. **Không sử dụng dữ liệu
INVALID_LEADS để kết luận NORMAL/PVC. Không tự mở AI-live.**
