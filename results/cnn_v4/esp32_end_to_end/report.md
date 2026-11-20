# Chuẩn bị thực nghiệm ECG V4 trên ESP32 — 19/11/2026

## Trạng thái và phạm vi

| Hạng mục cuối lượt chuẩn bị | Kết quả |
|---|---|
| Firmware ADC V4, IDF5.4.4, Ninja một job | BUILD PASS, chưa nạp |
| CPU | 160MHz, có guard CMake |
| Binary ADC | 324.864bytes; SHA-256 `81b90643f47c4c138648c514e2ed0107f814b5f0a6389cffca34763da953438b` |
| DRAM/IRAM tĩnh từ linker | 51.468 / 54.062bytes; không phải RAM runtime |
| Host C++ | 7 nhóm PASS; preprocessing22/22 exact |
| Evaluator Python | 6/6 synthetic regression tests PASS; không phải board test |
| Benchmark INT8 | Object Xtensa compile PASS; chưa full-link/chạy benchmark riêng |
| Replay asset/build | BLOCKED: Python3.11 thiếu; source/protocol plan đã chuẩn bị |
| FP32 export/build | BLOCKED: Python3.11 thiếu; chưa tạo model FP32 |
| Detector / ECG đầu cuối / analog | NOT READY / NOT RUN |
| Bảo toàn | 9.711 file firmware cũ được đối chiếu hash không đổi; source detector không đổi; checkpoint V4 và kernel golden khớp hash |

RAM arena đã dùng, heap/stack và latency **của bản tích hợp mới** chưa đo. Cấp phát arena cấu hình65.536bytes không phải arena thực dùng. Log build cuối: `build_adc_final.log`; manifest mới: `firmware_manifest.json`; trạng thái máy đọc: `preparation_status.json`.

Đã tạo `firmware/esp32_ecg_v4_experiment/` từ mã nguồn tích hợp V1. Không sửa bản V1, không thay checkpoint, không train, không dùng Final Test, không mở COM3, không build/flash/reset board cũ, không commit/push hoặc stage thêm file. Firmware mới chưa có phép đo phần cứng đầu cuối. Kết quả build cuối cùng được ghi trong `preparation_status.json` và log build; không suy ra build PASS từ việc đã có source.

**Replay và FP32 hiện BLOCKED bởi môi trường**, không được gọi toàn bộ chuẩn bị là PASS. Cả `.venv` và `.venv_diag` báo thiếu `C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe`. Python 3.13/3.14 có sẵn chưa có numpy/scipy/wfdb/tensorflow. Metadata môi trường cũ ghi TensorFlow 2.21.0. Không cài hay đổi TensorFlow để né lỗi. Cần khôi phục đúng runtime 3.11 để chạy công cụ chuẩn bị; chưa có asset stream/FP32 thật để build hai đường này. Không tạo placeholder ECG hoặc model giả.

## File mới và nhận diện model

Project mới gồm bản sao các file `main/*.cpp`, `main/*.h`, CMake/Kconfig cần thiết; các file phụ thuộc model đã được thay:

- `main/model/ecg_cnn_int8.tflite`: V4 8.688 bytes, SHA-256 `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`.
- `main/test_data/ecg_test_metadata.h` và `ecg_test_samples_int8.bin`: 22 golden V4, reference giữ nguyên từ bộ đã PASS. Checkpoint nguồn SHA-256 `36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1`.
- `main/single_round_conv.*`, `single_round_fc.*`, `single_round_math.h`: sao chép từ firmware golden V4. Stock TFLITE_SINGLE_ROUNDING=0, adapter Conv/FC single-round, reference kernels; ESP-NN không được bật. CMake kiểm tra effective flags.
- `main/research_shadow.h`, `pipeline.cpp`, `telemetry.cpp`: threshold V4 0,88, metadata input scale 0.06217966973781586/zero −8, output scale 1/256/zero −128; code ≥98 là PVC. Telemetry nhận diện V4, giữ ECG1 v2/CRC và quality/generation/queue/stale checks. Nguồn replay được đánh dấu LABELED_REPLAY, không giả là phần cứng analog.
- `main/preprocessing.h`: z-score population bằng double rồi float32, std ≤1e−8 bị loại; tách normalize/quantize để đo riêng; ties-to-even và saturation. Pipeline vẫn từ chối cửa sổ có quantization clipping như trước.
- `main/replay_main.cpp`: GPTimer 250 Hz, dữ liệu liên tục từ flash, không chứa annotation, không đọc ADC; bắt đầu sau golden/model ready, phát một lần rồi kết thúc, không loop. Pending timer notification >1 làm abort thay vì chạy bù giả. Timestamp phản ánh thời gian chạy thực tế. Chất lượng/timing vẫn đi qua pipeline.
- `main/benchmark.cpp`: hai build FP32/INT8 riêng, cùng 22 cửa sổ raw, CPU160MHz, warm-up3 và measured30 lần/fixture, cùng pause/log policy; không đưa warm-up vào thống kê warm latency.
- `tests/test_v4.cpp`, `tests/test_replay_evaluator.py`, `tests/host_stubs/sdkconfig.h`: kiểm tra mới có liên quan.
- Các công cụ ngoài firmware: `python/prepare_v4_experiment.py`, `prepare_v4_replay_assets.py`, `evaluate_v4_board_replay.py`; helper `build.ps1` chỉ configure/build/size, không có lệnh flash.

`original_firmware_hashes.json` và manifest mới dùng để xác minh tính bảo toàn. Các build dùng component TFLM/ESP-NN đã có trong project cũ qua override_path; không sao chép cache/managed_components hoặc chỉnh source thư viện.

## Bằng chứng preprocessing và giới hạn

Host C++ kiểm tra byte INT8 của 22 raw golden V4: exact, kể cả khi tách normalize/quantize. Kiểm tra thêm flat/NaN/Inf, ties-to-even, clipping, threshold97/98, stale/safety, FIFO overlap/wrap, queue full/reset và quality gate. Đây là kiểm thử preprocessing/buffer, không chạy lại benchmark/model parity cũ.

MIT-BIH/INCART offline resample về250Hz, cửa sổ `[R−128,R+128)`; ADC đã250Hz không được resample lần nữa. Affine gain dương/offset có thể được loại bằng z-score, nhưng ADC quantization, đảo cực, clipping và lọc AD8232 làm thay đổi morphology. Detector-centered không tương đương annotation-centered. Quality gate count-based phụ thuộc mapping tín hiệu; block metrics power50/baseline vẫn chỉ chẩn đoán nếu code không dùng làm gate.

Golden ESP32 đã có trong thư mục cũ:22/22 EXACT, arena_used6.124bytes, Invoke trung bình83,010ms. Chỉ tái sử dụng làm bằng chứng kernel/golden; **không coi là phép đo bản tích hợp mới**. RAM/latency thực tế của project mới vẫn PENDING.

## Detector: NOT READY cho tuyên bố hiệu năng đầu cuối

Đọc `results/cnn_v4/qrs_verification_v4a/report.md`: V4-A FAIL vì lợi ích không ổn định nhiều patient, không đủ cơ sở promotion. Evaluation: MIT FP1510→1506, INCART1938→1865, recall PVC không đổi; phần lớn lợi ích INCART tập trung patient8. Nhiều MIT FP là QRS Normal thật bị CNN phân loại PVC. Unmatched cũng có thể là timing/scope/OTHER/T/P hoặc chưa xác định, không tự gọi là nhiễu. Không nhúng gate V4-A.

Giữ nguyên baseline hiện hành để làm đối chứng có provenance: baseline EMA0,025; envelope EMA0,01; threshold max(30,2,5×envelope), warm-up500 mẫu, refractory75 mẫu, confirmation50 mẫu, thay candidate chỉ khi mạnh hơn1,5 lần. FIFO4, ring512. Bản sao `signal.cpp` không đổi thuật toán. Confirmation50 không được coi đã đạt yêu cầu; không thay thành58 hoặc tối ưu theo locked Test.

Đánh giá kế tiếp phải khóa protocol trên Train/Development: cùng stream/lead/mapping/detector hash, greedy one-to-one ±38 mẫu theo evaluator hiện có. Báo detector sensitivity/PPV/timing, queue/window losses và PVC classifier riêng từng record/patient. Hai đoạn smoke dưới đây chưa đủ chứng minh độ ổn định của detector; cần cohort Development đã dùng trước đây, không chọn bỏ record khó. Không có tiêu chí accuracy nghiệm thu được chốt mới trong lượt này, nên không được tự tuyên bố accuracy PASS.

## Replay dự kiến và scoring

`replay_plan.json` cố định trước chạy: MIT100 Train/MLII và INCART I08 Validation/II, mỗi đoạn `[0,15360)` ở250Hz (61,44s). Đây là smoke engineering, có thể ít/không có PVC trong một đoạn; không tạo PVC giả. Mapping cố định kế thừa evaluator: `clip(rint(2048+200*physical_mV),0,4095)`; resample full record rồi crop. Annotation mapping `floor(sample*250/fs+0.5)`.

Sau khi runtime được khôi phục, `prepare_v4_replay_assets.py` sẽ tạo stream `.bin`, hash nguồn/data, annotation sidecar ngoài firmware và `replay_protocol.json`; không ghi đè nếu protocol đã tồn tại. Chỉ khi asset/hash/protocol hoàn chỉnh mới được build REPLAY. Nhãn không tham gia phát hiện peak hoặc inference. Protocol chọn cohort này không dựa trên Test và không chọn thông số detector.

Nếu stream/protocol đã tạo thành công nhưng export FP32 bị gián đoạn, có thể chạy lại script với `--export-only` để giữ nguyên asset/protocol đã khóa. FP32 đã có thì script từ chối ghi đè.

Log mới: `V4_PEAK`, `V4_DETECTOR_EVENT`, `V4_BLOCK_REJECT`, `V4_BEAT`, `V4_PIPELINE_SUMMARY`, BEGIN/END replay; giữ telemetry ADC/timing/dropped/quality. Mỗi beat có sample/R timestamp, output code, probability, prediction hoặc −1 khi rejected, reason, prep/Invoke/result/end-to-end time và generation. END là CAPTURE_ONLY_NOT_ACCURACY_PASS. Serial log hoàn chỉnh là đầu vào evaluator, không phải dữ liệu host replay giả làm board.

GUI hiện tại chỉ nhận envelope HARDWARE/SYNTHETIC_TEST và AI source ADC_CNN (`tools/ecg_monitor/ecg_monitor/protocol.py`, `ai.py`). Bản ADC mới giữ các identity đó và `model=READY/DISABLED`, thêm `model_version=V4`. Replay cố ý dùng LABELED_REPLAY/REPLAY_CNN để tránh giả là ADC thật; GUI hiện tại sẽ từ chối nguồn này. Chưa sửa GUI: dùng capture UART thô/IDF monitor và evaluator riêng cho replay. Việc GUI hỗ trợ replay là một hạng mục tương lai, không phải phần đã PASS.

`evaluate_v4_board_replay.py` từ chối log thiếu marker, thiếu golden mới, model/stream sai, peak/beat trùng, mất peak log, queue/block drop hoặc score/code/threshold không khớp. Matching toàn bộ BEATS; OTHER tính TP detector nhưng loại khỏi N/V. PVC không có peak/window/classification đều phải vào FN; Normal bị mất là abstention, không TN. Unmatched predicted PVC tính FP alarm theo protocol nhưng không kết luận peak là noise. Báo riêng boundary/warm-up/gate losses; không thu nhỏ mẫu số vì gate.

## Đối chứng FP32–INT8

`prepare_v4_replay_assets.py` có bước xuất TFLite FP32 từ checkpoint khóa, optimizations rỗng, builtin ops, không calibration/train. **Chưa chạy được**, chưa có file FP32 hay phép đo FP32. Sau export cần so Keras/FP32 TFLite trên cùng golden normalized input, xác nhận operator/I/O và hash; chưa được mặc định PASS.

Hai build benchmark cùng ESP32, IDF5.4.4, TFLM1.4.2, CPU160MHz, compiler/scheduling và dữ liệu giống nhau. FP32 dùng stock float kernels, INT8 dùng adapter đã xác minh. Đo normalize, quantize+input copy (FP32 chỉ copy), Invoke và tổng; tính mean/median/SD/p95/min/max sau warm-up, báo cold riêng. Báo arena_used, heap tối thiểu, stack và Flash/ELF size từng build. Không dùng phép đo V1 240MHz làm đối chứng V4 160MHz. Benchmark static không đo detector/ADC end-to-end: dùng timestamp replay/ADC cho phần đó, có ít nhất508ms post-R cộng batching/queue/preprocessing/Invoke. Không tối ưu threshold theo score khác biệt.

## Điều kiện trước khi xin phép nạp

1. Hash V4/metadata/golden và source manifest khớp; model/threshold/CPU/kernel đúng; old firmware hash không đổi.
2. Host regression liên quan PASS; build đúng mode với Ninja-j1 thành công; không nhúng annotation hoặc dùng Test.
3. Với REPLAY: assets và protocol đã materialize/freeze; log evaluator sẵn sàng; hiện điều kiện này BLOCKED.
4. Với FP32: export và host I/O/golden equivalence phải được kiểm chứng; hiện BLOCKED.
5. Chỉ xin phép board engineering test sau các điều kiện tương ứng; người dùng xác nhận bench/simulator, không nối người. Golden tích hợp phải exact22/22; nếu không thì dừng. Không sửa reference hoặc nới sai số.
6. Detector/accuracy chưa nghiệm thu không cấm một phép đo engineering có kiểm soát sau phê duyệt, nhưng cấm gọi hệ thống đã xác minh hoặc dùng như cảnh báo y tế. NOT READY không được đổi thành PASS chỉ vì build/golden.

## Lệnh dự kiến, CHƯA nạp

Tại thư mục gốc, sau khi có Python3.11/môi trường cũ phù hợp:

```powershell
.\.venv_diag\Scripts\python.exe python/prepare_v4_replay_assets.py
& .\results\cnn_v4\esp32_end_to_end\build.ps1 -Mode REPLAY -Record MITBIH_100
```

Helper build dùng IDF đã cài. File constraints của bản cài thiếu nên helper dùng `IDF_PYTHON_CHECK_CONSTRAINTS=no`, không cài package; minimum dependencies đã được IDF kiểm tra. Nếu execution policy chặn `.ps1`, dùng terminal ESP-IDF đã cấu hình để chạy lệnh tương đương, không đổi policy toàn máy.

**Chỉ sau khi người dùng cho phép flash**, trong terminal ESP-IDF5.4.4:

```powershell
idf.py -C firmware/esp32_ecg_v4_experiment -B firmware/esp32_ecg_v4_experiment/build_replay_MITBIH_100 -p COM3 flash
idf.py -C firmware/esp32_ecg_v4_experiment -B firmware/esp32_ecg_v4_experiment/build_replay_MITBIH_100 -p COM3 monitor
```

Monitor có thể reset board; không chạy trước phê duyệt. Dùng Ctrl+T rồi Ctrl+L để bật ghi log monitor (hoặc lưu toàn bộ transcript); lấy đủ boot/model/golden/BEGIN/END. Vì replay chỉ chạy một lần, sau khi bật capture mới được reset có chủ đích nếu bỏ lỡ boot. Exit Ctrl+]. Log phải nằm trong thư mục run mới, không ghi đè golden cũ. Chấm:

```powershell
.\.venv_diag\Scripts\python.exe python/evaluate_v4_board_replay.py REAL_LOG.txt --record MITBIH_100 --output results/cnn_v4/esp32_end_to_end/REAL_RUN_metrics.json
```

## Analog ADC sau này

Sau replay/golden tích hợp, build mode ADC riêng. Nguồn ECG mô phỏng có nhãn/thời gian tham chiếu → AD8232 →GPIO34, LO+27/LO−26. Kiểm tra rail/gain/cực tính/lead-off, 250Hz thật, missed samples/queue, quality recovery và prediction expiry. Không dùng ECG INVALID_LEADS để chấm N/PVC. Chỉ báo accuracy analog nếu biết nhãn và đồng bộ nguồn; nếu không chỉ báo vận hành. Giữ nguyên gate/detector/threshold, không tuning trên Test. Mọi RAM/Flash/latency đầu cuối cần log build/board tương ứng, không lấy số standalone golden thay thế.
