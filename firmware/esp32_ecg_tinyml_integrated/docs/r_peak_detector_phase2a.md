# R-peak detector / pending CNN windows — Giai đoạn 2A

Đã sửa quản lý cửa sổ; **kiểm thử chức năng FIFO PASS, detector Validation vẫn FAIL,
AI-live LOCKED**. Chưa chuyển sang2B, chưa flash/mở COM3. Ngưỡng QRS/refactory/lọc,
CNN INT8, threshold CNN0,52, preprocessing, golden, telemetryv2/UART, synthetic,
GPIO, quality và FSM giữ nguyên. Chỉ hai source firmware thay đổi: `signal.h/.cpp`.

## 1. Baseline trước sửa và lỗi cũ

Đọc báo cáo/JSON Giai đoạn1, lưu source+SHA tại `debug/r_peak_phase2a_before/`,
biên dịch lại detector cũ và trace từ source đóng băng **trước khi sửa**.
Khớp từng dictionary candidate/gated score trên7 record; log/data ở
`debug/r_peak_phase2a/baseline_reproduced.json`, `*_before_events.csv`, `*_before_trace.bin`.
Baseline:16838 reference, TP13226, FP90, FN3612; sensitivity78,5485%, PPV99,3241%.
Không reset/clean/revert project; workspace không có Git repository, dùng snapshot
và `debug/r_peak_phase2a/source_diff.patch` để rà phạm vi.

Lỗi cũ: một `pending_` đợi508ms sau center để đủ cửa sổ; refractory chỉ300ms.
Đỉnh tiếp theo hợp lệ ở300..504ms gặp pending cũ và gọi `reset()`, hủy cả cửa sổ
và khởi tạo lại500 mẫu.795 ambiguity resets,2238 FN trong reset warm-up. Điều này
là lỗi quản lý cửa sổ chồng lấn, không phải bằng chứng cần đổi CNN/threshold.

## 2. Thiết kế mới và các hàm thay đổi

- `BeatWindowBuffer::append`: ring raw512 float + timestamp512 int64, một writer
  là AI worker; kiểm tra sample index liên tiếp. Không ISR/ADC/UART/mutex/heap.
- `enqueue`: FIFO **4 center** tĩnh; mỗi entry lưu sample index64bit và timestamp
  đọc từ ring tại center, không dùng thời gian alarm dự kiến. Kiểm tra lịch sử,
  duplicate/out-of-order và capacity; overlap không phải lỗi.
- `pop_ready`: chỉ trả head khi có mẫu `center+127`; kiểm tra ring chưa ghi đè,
  center timestamp, thứ tự và toàn bộ255 interval2000..6000µs trước khi copy.
  Sau đó copy đúng `[center-128,center+128)` vào256 float; center ởindex128.
  `BeatWindowInfo` giữ center/start/end/timestamp; mỗi center emit một lần FIFO.
- `BeatDetector::push`: giữ nguyên EMA0,01, magnitude, ngưỡngmax(30,2,5×envelope),
  warm-up500, refractory75 và no-peak rule. Chỉ thay enqueue/pop cho pending cũ.
  `last_window()` lấy metadata, `stats()` lấy counters theo vòng đời instance.
  Trước conflict đầu tiên của từng record, magnitude/baseline/envelope/threshold/
  age/last-center khớp bit với trace cũ; không có tuning thuật toán QRS ẩn.
- `reset_state`/`reset`: clear FIFO và invalidate ring bounds O(1), reset trạng
  thái QRS; giữ bộ đếm và absolute index để không tái dùng center cũ. Index là
  thứ tự mẫu thực sự được push vào instance, **không phải chỉ số của mẫu ADC bị
  gate loại trước đó**. Timestamp64bit mới là anchor thời gian toàn phiên.
  Ring không cần zero6KiB mỗi reset; dữ liệu cũ không thể đọc qua bounds mới.

Mặc định full FIFO: **drop newest**, tăng `dropped_full`, trả issue
`PENDING_QUEUE_FULL`; không overwrite center cũ và không reset bên trong queue.
Worker hiện có coi issue là invalid và không Invoke beat đó; quality/generation
reset tiếp theo hủy pending an toàn và có `dropped_reset`. Vì vậy không bỏ lỗi để
tiếp tục phân loại. Duplicate/order/history/timing cũng có issue/counter riêng.
`last_drop_reason()` giữ lý do gần nhất; không thêm field vào telemetryv2.

Ở refractory75 và thời gian chờ127 mẫu, tối đa2 center thường cùng pending;
capacity4 là hữu hạn có dư. Unit test cưỡng bức4 center sát nhau để chạy nhánh
full — **không hạ refractory** để tạo overflow trong Validation.
Không kéo dài thời gian chờ của cửa sổ cũ hoặc chặn nhận center mới vì overlap.

## 3. RAM, CPU và ownership

Đo layout bằng cross-compiler Xtensa/ELF (không suy từ sizeof Windows):
**6184 → 6448 byte/BeatDetector, tăng264 byte**.
Riêng BeatWindowBuffer6336byte, trong đó raw/time ring6144byte và4 entry64byte;
phần còn lại là index/counters/bounds/alignment. Firmware giữ một detector static
trong worker; không thêm task, timer, heap allocation hoặc buffer ở ADC producer.
Không dùng atomic cho counters vì chỉ worker sở hữu; không đọc trực tiếp chúng
từ task khác nếu chưa thêm cơ chế snapshot phù hợp.

Mỗi mẫu/enqueue O(1), pop thành công tối đa255 interval checks +256 copy, resetO(1).
Host g++-O2,5 lượt×1.000.000 mẫu: median ns/mẫu RR400ms
7.712→10.964, RR800ms
9.481→8.443. RR400ms trước sửa không hoàn tất
cửa sổ nào do conflict; sau sửa hoàn tất9993, nên không diễn giải delta thành
chi phí queue thuần. RR800ms có workload cửa sổ tương đương. Dữ liệu từng lượt
ở `cpu_host.json`; jitter host có thể ảnh hưởng benchmark.
**Chưa đo WCET/CPU/heap/stack ESP32**, không dùng ns trên host để tuyên bố đạt
timing board. ADC/GPTimer task không gọi detector này và không chờ nó; pipeline
worker/CNN đồng bộ cũ giữ nguyên. Nếu inference/worker chậm hơn khả năng block
queue, safety `PROCESS_QUEUE_FULL` vẫn có thể xảy ra; chưa xác nhận trên board.

## 4. Cùng dữ liệu và cách chấm trước/sau

Giữ đúng7 record Validation115,118,121,210,214,233,234; MLII; fs360→25025/36;
round-half-up annotation; ADC bench2048+200counts/mV; BEATS cũ gồm cả nhãn ngoài
N/V. SHA các raw .hea/.dat/.atr và ADC replay được kiểm tra trước chạy. Dùng đúng
`validate_offline.score`, reference-ordered greedy nearest ±12sample=48ms,
không dịch peak, không crop warm-up/biên, không loại record hoặc đánh giá Test.

| Record | TP/FP/FN trước | TP/FP/FN sau | Sensitivity trước→sau | PPV trước→sau | Tiêu chí sau |
|---|---:|---:|---:|---:|---|
| 115 | 1935/11/18 | 1939/12/14 | 99.0783% → 99.2832% | 99.4347% → 99.3849% | PASS |
| 118 | 2209/17/69 | 2256/23/22 | 96.9710% → 99.0342% | 99.2363% → 98.9908% | FAIL |
| 121 | 1741/50/122 | 1781/65/82 | 93.4514% → 95.5985% | 97.2083% → 96.4789% | FAIL |
| 210 | 2061/5/589 | 2623/16/27 | 77.7736% → 98.9811% | 99.7580% → 99.3937% | FAIL |
| 214 | 1619/2/643 | 2251/9/11 | 71.5738% → 99.5137% | 99.8766% → 99.6018% | PASS |
| 233 | 963/0/2116 | 3064/4/15 | 31.2764% → 99.5128% | 100.0000% → 99.8696% | PASS |
| 234 | 2698/5/55 | 2740/7/13 | 98.0022% → 99.5278% | 99.8150% → 99.7452% | PASS |

Tổng: **TP13226→16654, FP90→136, FN3612→184**;
sensitivity78.5485%→98.9072%,
PPV99.3241%→99.1900%. Khôi phục3430 reference vốn FN nhưng mất2
reference vốn TP; net+3428TP, không giả định mọi nhịp trước match đều giữ được.

| Nhãn annotation | Reference | TP/FN trước | TP/FN sau | Sensitivity trước→sau |
|---|---:|---:|---:|---:|
| N |11167|9165/2002|11035/132|82,0722%→98.8179%|
| V |1301|268/1033|1276/25|20,5995%→98.0784%|

Không gộp L/R thành N. QRS detector không phân loại FP thành N/V, nên PPV theo
nhãn thật không được bịa ra; JSON có TP/FN/sensitivity mọi loại annotation.

| Record | Conflict resets trước→sau | FN reset warm-up trước→sau | Windows hoàn tất trước→sau | Drop full sau | Duplicate/out-order sau |
|---|---:|---:|---:|---:|---:|
| 115 | 1 → 0 | 3 → 0 | 1946 → 1951 | 0 | 0/0 |
| 118 | 13 → 0 | 32 → 0 | 2226 → 2279 | 0 | 0/0 |
| 121 | 14 → 0 | 38 → 9 | 1791 → 1846 | 0 | 0/0 |
| 210 | 135 → 0 | 378 → 3 | 2066 → 2639 | 0 | 0/0 |
| 214 | 178 → 0 | 296 → 0 | 1621 → 2260 | 0 | 0/0 |
| 233 | 445 → 0 | 1464 → 0 | 963 → 3068 | 0 | 0/0 |
| 234 | 9 → 0 | 27 → 0 | 2703 → 2747 | 0 | 0/0 |

Windows13316→16790;6 center cuối record còn pending vì thiếu future samples,
không flush bằng padding giả. Không có full/drop-reset/duplicate/out-of-order/
overwritten window trong replay candidate. FIFO high-water2 trên mọi record.
Mỗi window candidate và gated đều assert đúng256 raw sample, center timestamp,
index128 và thứ tự; không chỉ kiểm tra shape.
Conflict reset795→0; FN trong reset warm-up2238→12; warm-up tổng1610s→22s.
No-peak reset3→4 (121:3,210:1), giữ nguyên rule; không gọi đó là conflict mới.

### FP được đo riêng, chưa đạt tiêu chí

FP tăng**46**, tương đương51,11% so với90 cũ; phần trăm detection là0,6759%→0,8100%.
Với cùng tổng thời gian replay12638,892s, khoảng25,64→38,74 FP/giờ.
Record121 tăng50→65 FP,11817→23,2105→16; không ẩn hoặc bỏ các record đó.
Không điều chỉnh threshold/refractory/lọc; thêm thời gian active sau khi bỏ reset
làm xuất hiện cả TP và FP mà baseline đã không emit. Tuy vậy đây không phải bằng
chứng FP được chấp nhận: **FAIL** tiêu chí cũ, không mở live hoặc tuyên bố sẵn sàng.
Từng record phải sensitivity≥99%,PPV≥99%,p95 timing≤40ms; controls phải0 FP.
118 failPPV98,9908%;121 fail sensitivity95,5985% vàPPV96,4789%;210 fail sensitivity
98,9811%. Không làm tròn118 thành99% để cho PASS.

## 5. FN còn lại và Giai đoạn2B

Phân nhóm184 FN bằng trace state tại annotation (mô tả vị trí chặn, không phải
ablation causal độc lập):

| Bằng chứng | FN |
|---|---:|
| INITIAL_WARMUP | 20 |
| REFRACTORY_BLOCK | 91 |
| END_WINDOW_UNAVAILABLE | 5 |
| BELOW_ADAPTIVE_THRESHOLD | 56 |
| RESET_WARMUP | 12 |

91 refractory: còn local peak trước sai làm chặn QRS thật; không đơn giản là RR
sinh lý quá ngắn.56 dưới adaptive threshold;20 warm-up đầu và5 thiếu futurewindow
ở biên vẫn giữ trong denominator.12 reset warm-up còn lại theo no-peak rule.
121 còn82FN/65FP, là ưu tiên2B. PVC còn25FN; không suy sensitivity của CNN hoặc
hệ thống thực từ độ nhạy detector này. `false_negatives_before/after.csv` giữ
thời điểm, nhãn, nearest peak, ngưỡng, age và reset gần nhất để truy vết.
Bit16 trace mới chỉ là benign overlap; tool bỏ bit này khi dùng bộ phân nhóm
Giai đoạn1 để tránh gọi overlap hợp lệ là conflict reset.

Biểu đồ cùng sóng và matching, TP xanh/FN đỏ/FP tím:

- [233: PVC và cửa sổ chồng lấn được giữ](../debug/r_peak_phase2a/233_before_after.png)
- [121: đoạn khó còn FP/FN](../debug/r_peak_phase2a/121_before_after.png)
- [115: đỉnh giả trước R vẫn chưa được sửa](../debug/r_peak_phase2a/115_before_after.png)

Đề xuất2B để xem xét: phân biệt QRS/noise/P/T tốt hơn ở nhánh detection, adaptive
threshold và RR-aware searchback; review refractory/localization/no-peak reset.
Nếu thử bandpass thì chỉ ở nhánh detection và phải đo/bù delay, giữ raw256 cho
CNN. Chưa thực hiện bất kỳ thay đổi nào trong danh sách này; không thay XQRS.

## 6. Test, golden, parity và build

- **53 Python tests PASS**;42 monitor/GUI/protocol cũ,9 kiểm toán lịch sử dùng
  binary detector cũ đóng băng,2 wrapper gọi C++ mới. Không dùng test hành vi lỗi
  cũ để kết luận class mới đã sửa. Log `tools/ecg_monitor/reports/r_peak_phase2a_tests.log`.
- **14 operator-trace tests PASS**; C++ current system/signal/lead-off/trace codec/
  telemetry wire/beat window PASS, requantization20000 signed cases PASS.
- C++ mới:2 đỉnh gần,4 cửa sổ chồng, xung rộng đảo cực kiểu PVC liên tiếp (fixture
  số, không nhãn lâm sàng), RR biến thiên, biên256/512, wrap, full/drop-newest,
  duplicate/order, stale ring, gap atomic reject, reset/hủy pending khi invalid.
  Lead-off mapping/OR và quality/FSM regression giữ nguyên; test hủy pending mô
  phỏng lệnh reset từ gate, **không phải chạy full RTOS/lead-off hardware**.
- Streaming300000 mẫu ở timestamp250Hz (20phút ảo),2993 windows theo thứ tự,
 0 overflow/duplicate/order errors. Host simulation không chứng minh board20phút.
- **Golden12/12 EXACT**,33 lần/mẫu ổn định, đã chạy lại ở host với actual native
  kernels. **Parity9425/9425**,0 byte preprocessing và0 output code sai với TF.
  Corpus cố định9425 matched Validation window Giai đoạn1, không thay sang một
  subset thuận lợi của detector mới. Đây là component parity, không end-to-end
  accuracy; toàn bộ windows mới được kiểm tra raw/index riêng bởi C++ harness.
- **ESP-IDF5.4.4 build ADC thật PASS**,317264byte;
  **build synthetic PASS**,315824byte. Hai log trong
  `debug/r_peak_phase2a/build_hardware.log`, `build_synthetic.log`; không flash.
  Cấu hình root syntheticOFF/liveOFF, cấu hình riêng syntheticON/liveOFF.

## 7. Xác minh phạm vi và file

- `firmware\esp32_ecg_tinyml_integrated\main\signal.h`
- `firmware\esp32_ecg_tinyml_integrated\main\signal.cpp`
- `firmware\esp32_ecg_tinyml_integrated\tests\detector_phase2a_replay.cpp`
- `firmware\esp32_ecg_tinyml_integrated\tests\beat_window_test.cpp`
- `firmware\esp32_ecg_tinyml_integrated\tests\detector_cpu_bench.cpp`
- `firmware\esp32_ecg_tinyml_integrated\tests\detector_size_probe.cpp`
- `tools\ecg_monitor\review_r_peak_phase2a.py`
- `tools\ecg_monitor\validate_phase2a_parity.py`
- `tools\ecg_monitor\report_r_peak_phase2a.py`
- `tools\ecg_monitor\tests\test_phase2a_windows.py`

Hai source sản phẩm sửa trực tiếp là `main/signal.h/.cpp`; còn lại là công cụ/test
mới. Báo cáo này và `debug/r_peak_phase2a_results.json` là output yêu cầu.
Các log/CSV/trace/bench/parity/binaries/probe/diff riêng nằm dưới `debug/r_peak_phase2a`.
Snapshot ban đầu và báo cáo Giai đoạn1/telemetry cũ không bị ghi đè.
**66 file bảo vệ khớp SHA**, gồm pipeline/FSM, ADC/GPTimer,lead-off,
LED/buzzer,telemetryv2/UART/synthetic,Kconfig/sdkconfig,model/golden/preprocessing,
split/dataset và project cũ. Ngưỡng CNN0,52, hai khóa AI-live vẫn giữ nguyên.
Không train, xem Test, mở COM3, reset hay flash; không cập nhật threshold chính thức.

## 8. Tái chạy và giới hạn

Trong workspace hiện tại đã có executable/snapshot; tái chạy Validation/corpus:

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ecg_tinyml_integrated'
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I main -I tests main/signal.cpp tests/detector_phase2a_replay.cpp -o debug/r_peak_phase2a/current_audit.exe
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I main -I tests main/signal.cpp tests/beat_window_test.cpp -o debug/r_peak_phase2a/beat_window_test.exe
Set-Location 'D:\Code Part Two\AIoT\tools\ecg_monitor'
.\.venv\Scripts\python.exe review_r_peak_phase2a.py
.\.venv\Scripts\python.exe validate_phase2a_parity.py
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe report_r_peak_phase2a.py
```

Host tests dùng `.venv` riêng của monitor hiện có, TensorFlow reference dùng
`.venv_reference` có sẵn; không cài lại Python/root.venv/dependencies.
Build dùng terminal ESP-IDF5.4.4 theo cấu hình hiện tại, không mở monitor/flash.
Validation đã dùng lại, chưa là đánh giá cuối độc lập. CPU/timing/heap/stack trên
ESP32 và tính liên tục khi worker/CNN cùng chạy: **PENDING HARDWARE VALIDATION**.
Phải giữ safety gate và LOCKED ngay cả khi queue unit tests PASS.
