# Kiểm kê thực nghiệm V4 — 20/11/2026

Chỉ đọc artifact/source, kiểm tra đường dẫn và SHA-256; không inference/train/build/COM/flash/reset. Không sửa bài báo hoặc các kết quả cũ. `evidence_manifest.json` chứa hash từng file; `metrics_summary.csv` tách mỗi điều kiện/dataset thành một dòng, Precision/Recall/F1 theo tỷ lệ0..1, thời gian ghi rõ µs. Không có “accuracy chung” của offline/replay/benchmark.

## Quy ước trạng thái

PASS nghĩa là phép kiểm số học/thu phiên/build đáp ứng kiểm tra đã lưu; không tự mang nghĩa đạt hiệu năng PVC. COMPLETED là có số liệu/bằng chứng, chưa có tiêu chí accuracy nghiệm thu. NOT RUN/MISSING không được điền số0 thay cho số đo chưa làm. FAIL promotion chỉ áp dụng nhánh thử nghiệm đã bị loại theo báo cáo gốc.

## 1. Model và provenance

| Artifact | Nơi lưu | SHA-256 | Trạng thái |
|---|---|---|---|
| Checkpoint849 tham số | `models/v4/ecg_cnn_v4_best.keras` | `36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1` | Có, đúng checkpoint |
| INT8,8.688bytes | `models/v4/ecg_cnn_v4_int8.tflite` | `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e` | Host/board chạy được |
| FP32 TFLite,9.584bytes | `firmware/esp32_ecg_v4_experiment/main/model/ecg_cnn_v4_fp32.tflite` | `699dd84a6490d1cb50ea67c840225a7023b0dbfccd24350d58f8c53463217522` | Host/board chạy được |

Hai dtype cùng checkpoint/kiến trúc V4; threshold0,88, INT8 code≥98. Input256×1,250Hz,z-score population theo cửa sổ; INT8 input scale0,06217966973781586,zp−8; output scale1/256,zp−128. Không có RR. Provenance: `selection.json`, `preprocessing.json`, `int8_conversion.json`, `esp32_end_to_end/fp32_export.json`; training log `results/cnn_v4/training_run.log`. Kiến trúc: Conv1D8×k5→pool2→Conv1D16×k5→pool2→GAP→Dense8→sigmoid1,849tham số.

## 2. Offline CNN-only — COMPLETED, không gọi tất cả là Final Test độc lập mới

| FP32, annotation-centered, threshold0,88 | N /V | TP /FP /FN /TN | Precision /Recall /F1 |
|---|---|---|---|
| MIT-BIH Test, fixed diagnostic đã lưu |10.374 /905|812 /351 /93 /10.023|69,819% /89,724% /78,530%|
| INCART Test |23.081 /3.332|2.594 /403 /738 /22.678|86,553% /77,851% /81,972%|

INCART gốc: `results/cnn_v4/test_evaluation.json`, `test_evaluation.lock.json`, `report.md` và per-patient trong JSON. MIT-BIH V4 không có ở bảng Final Evaluation V5 ban đầu (ô null); **sau đó đã có** tại `results/cnn_v5/precision_drop_diagnostic/summary.json`, `beat_predictions.csv`, `per_record_metrics.csv`, `report.md`. Artifact này ghi checkpoint V4 đúng hash, threshold cố định và không tuning trong lượt chẩn đoán. Không chạy lại để điền số.

Tính độc lập phải tách hai khái niệm: artifact INCART ghi patient-disjoint và checkpoint/threshold khóa trước lượt Test ban đầu; điều này không chứng minh một phép đánh giá xác nhận hoàn toàn mới của model cuối sau nhiều lần xem Test. Các kết quả Test đã được phân tích và đối chứng để chọn ứng viên V4; đối chứng end-to-end hiện có tự ghi **retrospective, not independent confirmatory evidence**. Vì vậy hồ sơ hiện **chưa có cohort xác nhận mới chưa ảnh hưởng quyết định chọn model cuối**. Kiểm kê này không thay cho audit đầy đủ Git/split leakage; không tự kết luận V4 train trên Test chỉ vì Test đã được xem.

### Validation và PTQ đã có

INCART Validation25.010 beat: FP32 P95,6435%/R92,9541%/F194,2796%; INT8 P96,4770%/R92,0491%/F194,2110%.55 quyết định thay đổi tại0,88, score MAE0,00372551, max abs0,489056. Đây là số đã lưu ở `int8_conversion.json`, không chạy lại.22 golden có quyết định FP32/INT8 khớp không phủ nhận55 thay đổi trên Validation đầy đủ. Calibration INT81.000 mẫu chỉ từ Train; không nhầm calibration này với Test.

## 3. Detector tự động/offline dùng đối chứng V4 — COMPLETED, ungated

| Điều kiện FP32 detector-centered | TP /FP /FN /TN | Precision /Recall /F1 | Detector miss N /V |
|---|---|---|---|
| MIT Development |1.163 /643 /138 /10.507|64,396% /89,393% /74,863%|34 /14|
| INCART Development |2.844 /122 /251 /21.503|95,887% /91,890% /93,846%|324 /19|
| MIT Test hồi cứu |767 /285 /138 /9.516|72,909% /84,751% /78,385%|688 /56|
| INCART Test hồi cứu |2.218 /187 /1.116 /22.565|92,225% /66,527% /77,296%|361 /366|

Nguồn: `results/model_comparison/end_to_end_v4_v6_v11/` và `test_end_to_end_v4_v6_v11/`; có `evaluation.json`, `report.md`, per-record metrics, scores/peaks NPZ và patient/group summaries. Đây là đọc kết quả V4 đã lưu trong đối chứng, **không chạy V11**. Matching greedy one-to-one±38, BEATS gồm OTHER; matched OTHER không phải N, missing N là abstention, missing V là FN, unmatched PVC alarm là FP. Test FP MIT285 =178 matched-N errors+107 unmatched alarms; INCART187=166+21. Extra peaks2955/3443 không tự đồng nghĩa nhiễu.

Các phép offline không tái hiện đầy đủ lead-off, saturation/timing/generation/recovery/age gate firmware. Không lấy CNN-only Test và detector-centered Test làm cùng sample denominator: ví dụ INCART CNN-only N23.081/V3.332, end-to-end reference N23.092/V3.334 do phạm vi annotation/window khác. Không tự lấy N/V subset để công bố sensitivity/PPV của mọi loại beat khi thiếu mẫu số OTHER.

Detector source hiện dùng confirmation50/refractory75mẫu, threshold EMA và FIFO4; không tự gán số legacy detector58mẫu hoặc số99,61% trong tài liệu khác cho build này. V4-A gate FAIL promotion (`qrs_verification_v4a/report.md`); V4-B FAIL (`v4b_hard_example_training/report.md`). Giữ hai kết quả âm này và không coi là model triển khai.

## 4. Numerical parity và board golden — PASS số học

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Python INT8↔host TFLM |25.010/25.010 exact,0LSB max|`int8_conversion.json`; `v4_validation_inputs_int8.bin`, `v4_validation_python_codes.bin`, `v4_validation_tflm_host_codes.bin`, host source/executable và conversion log|
| Golden ESP32 riêng |22/22 output và preprocessing exact,arena6.124bytes|`esp32_golden_test/board_runs/verification_20261119_101619.json`; raw `esp32_golden_test/firmware/log.v4_golden_only.20261119101602.txt`; fixtures JSON/NPZ/binaries|
| Golden trong replay |22/22 ở cả MIT100 và PVC|raw UART hai phiên bên dưới|

Đây là số học/runtime compatibility, không phải22/22 nhịp đúng nhãn thật hay accuracy detector. Tài liệu conversion cũ ghi board_tested=false là trạng thái lúc chuyển đổi; verification/board logs sau đó là bằng chứng cập nhật. Không ghi đè trạng thái lịch sử để che tiến trình.

## 5. Board replay — PASS phiên, chưa nghiệm thu accuracy tổng quát

Đường dẫn chung: `results/cnn_v4/esp32_end_to_end/board_runs/`.

| Phiên | Kết quả và giới hạn |
|---|---|
| `MITBIH_100_20261120_144144/` |15.360mẫu61,44s,75N/0V;73peak,65inference,7rejected (6clipping+1EOF freshness),queue/block/sample drops0. PeakTP73/FP0/FN3;TN64,missingN11,OTHER1. Invoke mean84,809ms,R→result1.236,052ms. Không có PVC nên Recall/F1 PVC không định nghĩa; không diễn giải số0 JSON như hiệu năng0%.|
| `INCART_PVC_V1_20261120_145655/` |I08 Validation/II466,00–527,44s,43N/20V;78peak,77inference,1EOF rejection,drops0. TP9/FP1/FN11/TN40,P90%/R45%/F160%;2V detector miss+9V CNN Normal. Invoke84,777ms,R→result1.202,063ms;arena6.124bytes. Chỉ một segment/patient đã dùng trong phát triển.|

Mỗi thư mục có raw `uart_raw.log`, capture/device/flash metadata, `evaluation.json`, từng beat CSV và report; PVC còn có reference accounting/unmatched CSV. MIT log SHA256 `1fbe94640a85b39f843e11ce1ab41d1796e423b6a32f3dea0cfe614acb97b6d8`; PVC `53d97bb1d96460d93e82db6cfcea9999e824af6d18b46d2748fa70cf9ca82ecb`.

43N PVC hạch toán đúng:40TN+2detector miss+1safety rejection; FP1 là unmatched alarm, không phải N→PVC.20V=9TP+9classifier FN+2detector miss.19 unmatched peaks đều ngoài±38mẫu, không tự gọi là noise.77 common outputs board/host exact; khác host TN41 vì host ungated không có EOF freshness rejection.

PVC raw có511byte fragment status sau END;738 frame có newline đều CRC đúng. Giữ `uart_crc_diagnostics.json` (phân tích sơ bộ đếm fragment là lỗi) **cùng** `uart_boundary_analysis.json` để giải thích, không xóa fragment. Các log Serial Monitor cũ14/16 golden là capture thiếu/mixed boot, không thay cho phiên hợp lệ; giữ làm lịch sử chẩn đoán, không cần đo lại.

## 6. Benchmark cùng ESP32 — PASS đo mô tả

`BENCH_V4_FP32_INT8_20261120_153844/`: cùng board/CPU160MHz/IDF5.4.4/reference backend ESP-NN off,22 raw windows,3warm-up+30 measured/fixture (660 measured/backend). Mỗi backend có raw UART, verified726 records, build/flash/device/config/hash, all_runs.csv; `metrics.json`, `fixture_comparison.csv`, `paper_table.*` đủ thống kê.

| Chỉ số | FP32 | INT8 |
|---|---:|---:|
| Invoke mean |34,472409ms|83,084818ms|
| Window→raw output mean |36,294545ms|86,771182ms|
| Model bytes |9.584|8.688|
| Application bytes |273.936|270.576|
| Arena used /allocated bytes |18.120 /65.536|6.124 /65.536|
| Minimum free heap bytes |230.912|230.376|

INT8 Invoke gấp2,410183lần FP32 (+141,02%), không nhanh hơn ở backend đã đo.22/22 quyết định khớp,delta score max0,045672357. Arena used giảm66,20% nhưng reservation64KiB như nhau, nên không báo heap tiết kiệm66%. Không tính UART/delay trong timer; total dừng khi Invoke trả về, không phải R→result. Một boot/backend,22cửa sổ lựa chọn số học,không phải660 bệnh nhân/phiên độc lập. Không dùng làm bằng chứng accuracy population hoặc năng lượng.

## 7. Bằng chứng phụ và thiếu sót thực sự

- European ST-T đã có:90record,784.534N/4.467V,P5,295%/R86,568%/F19,980% (`results/cross_dataset_edb/`). Lead policy không đồng nhất MLII/II; đây là bằng chứng giới hạn cross-domain, không bỏ vì F1 thấp và không chạy lại.
- Không thiếu raw/core metadata cho ba nhóm board đã PASS. Hash manifest giữ đường dẫn các JSON/CSV/log và source; per-record/per-patient vẫn ở artifact gốc, không tổng hợp lại bằng inference.
- Còn thiếu: **ADC analog có reference đồng bộ**, kiểm thử safety/fault của chính V4 ADC đã đo, cohort xác nhận độc lập sau lựa chọn model cuối và độ ổn định nhiều segment/patient. Hai mươi PVC: một lỗi làm Recall đổi5điểm phần trăm; nhịp cùng người tương quan, không suy ra CI bệnh nhân độc lập.
- ADC source và build cũ PASS không chứng minh analog chạy đúng. Snapshot `esp32_end_to_end/builds/ADC_previous/esp32_ecg_v4_experiment.bin` hash `81b90643f47c4c138648c514e2ed0107f814b5f0a6389cffca34763da953438b`; không build/nạp lại ở lượt này. Theo phiên cuối đã lưu, board hiện BENCH_INT8, không phải ADC; không hỏi board qua COM lần này.
- GUI `tools/ecg_monitor/ecg_monitor/ai.py:26` hardcodes0,52 khi kiểm nhãn; NORMAL score0,52..0,88 của V4 có thể bị từ chối/UNKNOWN. Replay capture/evaluator chờ END nên chưa phù hợp ADC liên tục. Chỉ ghi nhận, không sửa GUI/capture/firmware.

Xem `remaining_experiments.md` và `adc_preparation.md` cho phần chuẩn bị tiếp theo. Không cần chạy lại golden/parity/replay/benchmark đã hợp lệ; chỉ chạy regression liên quan nếu có thay đổi được phê duyệt sau này.


## ADC passive UART update 2026-11-20 17:37 (Asia/Saigon)

Run `results/cnn_v4/esp32_end_to_end/board_runs/ADC_V4_20261120_173711`: 30080 actual ADC samples, 250.000000 Hz; ECG end-to-end FAIL (ADC_SATURATION, no inference). UART-only recording, no flash/reset. See run report/metrics; not a valid ECG accuracy experiment or patient-safety verification. Earlier entries remain historical.
