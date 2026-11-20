# Hoàn thiện replay và FP32 V4 — 19/11/2026

Đây là báo cáo tiếp tục; giữ nguyên các báo cáo cũ. Các trạng thái Python BLOCKED trong `report.md`/`preparation_status.json` trước đó là lịch sử, được thay thế bởi bằng chứng kiểm tra lần này.

## Môi trường: PASS, không sửa dependency

Đã dùng trực tiếp `.venv/Scripts/python.exe`: Python3.11.9, NumPy2.4.6, SciPy1.17.1, TensorFlow2.21.0, WFDB4.3.1. Import, load Keras, resample, WFDB và TFLite Invoke thực tế đều chạy được. Sandbox mặc định không truy cập được base interpreter, nhưng cùng lệnh trong user context được cấp quyền chạy thành công. Đây không phải Python chưa cài; không xóa/tạo lại venv hoặc cài package. TensorFlow oneDNN tắt trước import trong script thực nghiệm.

## Replay đã tạo và khóa

`replay_protocol.json`, `MITBIH_100_annotations.json`, `INCART_I08_annotations.json` lưu record/lead/range, hash ECG nguồn/stream/annotation và matching. Hai stream nằm tại `firmware/esp32_ecg_v4_experiment/main/assets/`, mỗi stream15.360 mẫu uint16/61,44s; source250Hz sau resample_poly360→250 hoặc257→250, mapping kế thừa `rint(2048+200*mV)` rồi clip ADC. MIT100 Train/MLII, I08 Validation/II, không dùng Final Test, không đổi protocol sau khi thấy score.

Nhãn chỉ được mở ở Python sau khi detector và TFLM inference đã kết thúc. Native runner nhận stream/counts, không nhận annotation. Firmware chỉ embed stream/model/golden; không embed annotation sidecar. Golden có nhãn chỉ phục vụ bài kiểm tra tham chiếu khi boot, không điều khiển detector/live inference.

Chuỗi host dùng chính `signal.cpp`, window256, `preprocessing.h` mới và reference TFLM INT8/adapter đã kiểm chứng; tái dùng object TFLM cũ, không chạy lại25.010 mẫu parity. Chỉ chạy trên hai stream mới. Runner/command source: `tests/replay_host.cpp`, `tests/tflm_replay_host.cpp`, `python/check_v4_replay_host.py`.

| Host stream | N tham chiếu | V tham chiếu | Peak | Peak TP/FP/FN | Window hoàn tất | Inference | Window clipping bị loại | TN | Missing N |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| MIT100 | 75 | 0 | 73 | 73/0/3 | 72 | 66 | 6 | 65 | 10 |
| INCART I08 | 63 | 0 | 62 | 61/1/2 | 62 | 62 | 0 | 61 | 2 |

MIT có thêm1 OTHER beat tham chiếu/được phân loại; không gộp vào N. Một peak MIT cuối đoạn chưa có đủ128 mẫu từ mốc trở đi, không tạo window. Chi tiết chính xác là **6 window clipping +1 window chưa đủ đuôi**, thay cho mô tả sơ bộ7 window clipping. Các nhịp mất không được tính TN. Không thay detector50/75 hoặc threshold0,88 sau kết quả này.

**Không có PVC trong hai đoạn smoke đã khóa**, vì vậy không có cơ sở tính/diễn giải Recall/F1 PVC (các số0 trong JSON do quy ước mẫu số0 không phải hiệu năng PVC bằng0%). Không chọn lại đoạn dựa trên score để làm đẹp. Muốn kiểm chứng PVC đầu cuối cần bổ sung protocol Development có PVC trước một lượt chạy mới; golden22 mẫu đã có PVC chỉ xác minh classifier, không thay cho stream có PVC.

Log từng peak/window/rejection: `host_replay_20261119/*.events.csv`; từng beat có code, score, prediction, reference được ghép sau inference, offset và **Invoke host µs** tại `*.beats.csv`/`*.timings.csv`. Chi tiết: `host_replay_20261119/evaluation.json`. Không có sample bị mất trong việc đọc file host; đây không phải số đo mất mẫu trên ESP32.

Host chain này **ungated, logical timestamps**, không giả lập FreeRTOS, lead-off, generation/recovery, UART jitter hoặc quality gate analog. Firmware replay giữ các gate thật và GPTimer; vì thế không gọi số host là kết quả firmware end-to-end. Khi gate/device drop làm mất nhịp, evaluator tính missing PVC vào FN, missing N là abstention; OTHER và unmatched theo đúng ±38 mẫu one-to-one, unmatched không mặc định là noise.

## FP32: export và host PASS, ESP32 runtime PENDING

- Checkpoint nguồn V4 giữ SHA256 `36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1`,849 tham số.
- FP32 TFLite mới: `main/model/ecg_cnn_v4_fp32.tflite`,9.584bytes; SHA256 `699dd84a6490d1cb50ea67c840225a7023b0dbfccd24350d58f8c53463217522`. Không train, optimization/conversion quantization tắt.
- Input/output float32, shapes `[1,256,1]`/`[1,1]`. Host Invoke thực tế PASS. Keras–FP32 TFLite trên22 golden: max absolute error2,980232238769531e−7,0 quyết định đổi tại0,88.
- FP32–INT8 trên các window stream hợp lệ: max score difference MIT0,0014220551; INCART0,0216625854;0 quyết định đổi. Không suy ra điều này cho PVC vì đoạn không có V.
- `fp32_export.json` liệt kê thêm DELEGATE do default desktop interpreter partitioning; danh sách không-delegate trong `host_replay_20261119/evaluation.json` xác nhận16 operator/7 loại builtin, không có custom/Flex mới. DELEGATE không phải một operator lạ nhúng vào model cho ESP32.

## Test/build

Host C++7 nhóm PASS, preprocessing golden22/22 exact; evaluator Python6/6 PASS. Model INT8 vẫn SHA256 `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`,8.688bytes, output code≥98, input/output contract giữ nguyên.

Tất cả build dưới đây PASS IDF5.4.4, CPU160MHz, Ninja-j1, reference kernels; không tự bật ESP-NN:

| Mode | Application .bin bytes | DRAM tĩnh | IRAM tĩnh |
|---|---:|---:|---:|
| REPLAY MIT100 | 347.440 | 43.228 | 54.066 |
| REPLAY INCART I08 | 347.440 | 43.228 | 54.066 |
| BENCH INT8 | 270.576 | 15.532 | 49.634 |
| BENCH FP32 | 273.936 | 14.996 | 49.634 |

Binary snapshots, bootloader/partition và SHA256 nằm tại `builds/` + `completion_status_20261119.json`. Đây là kích thước build, **không phải RAM/arena/latency runtime**. Không chạy lại build ADC cũ đã PASS.

Để tiết kiệm compile, các mode được build tuần tự bằng cache trong `build_adc_MITBIH_100`. Cache hiện là **BENCH_FP32**, tên directory không đại diện mode hiện tại. Không flash cache này như replay. Các bản `.bin` từng mode đã lưu riêng; bản ADC cũ cũng được giữ.

Benchmark hai build dùng cùng22 raw golden,3 warm-up+30 measured/fixture, CPU160MHz và cùng chính sách pause/UART. Log tách normalization, quantization/copy, Invoke, total; kết quả classifier, arena_used, heap_min, stack. FP32 stock float kernels, INT8 adapter proven. Toàn bộ **board allocation/Invoke/latency vẫn PENDING**, build/link không chứng minh chạy được. Benchmark total là window→output, không phải latency ADC/detector. R→result end-to-end đo riêng bằng replay INT8 `V4_BEAT e2e_us`; chưa có FP32 detector-replay end-to-end đối chứng, không gọi benchmark static là phép đo đó.

## Sẵn sàng và còn thiếu

Sẵn sàng xin phép chạy **engineering replay smoke/golden và benchmark** trên board. Chưa có bằng chứng accuracy PVC đầu cuối, chưa có board timing/heap/arena của các build mới, chưa xác minh analog, và detector vẫn NOT READY cho tuyên bố hiệu năng. Cần protocol stream có PVC để nghiệm thu PVC; không tuning theo locked Test. GUI cũ không nhận LABELED_REPLAY/REPLAY_CNN: dùng Serial log thô, không sửa GUI trong lượt này.

Đối chiếu9.711 hash firmware V1 cũ không đổi. Không sửa V1/checkpoint/model INT8/threshold/detector hoặc các báo cáo cũ. Không flash, reset, mở COM3, commit hoặc push.

## Lệnh chỉ chạy sau khi được phép đo board

PowerShell tại gốc repo, dùng terminal ESP-IDF5.4.4. Trước flash cần bench/simulator không nối người. **Các lệnh dưới đây chưa được thực hiện**:

```powershell
# Tạo đúng mode trong build directory riêng; không dùng cache BENCH_FP32 làm replay.
& .\results\cnn_v4\esp32_end_to_end\build.ps1 -Mode REPLAY -Record MITBIH_100
Start-Transcript -Path results/cnn_v4/esp32_end_to_end/REAL_MIT100_RUN.txt
idf.py -C firmware/esp32_ecg_v4_experiment -B firmware/esp32_ecg_v4_experiment/build_replay_MITBIH_100 -p COM3 flash monitor
# Thoát monitor bằng Ctrl+], rồi:
Stop-Transcript
.\.venv\Scripts\python.exe python/evaluate_v4_board_replay.py results/cnn_v4/esp32_end_to_end/REAL_MIT100_RUN.txt --record MITBIH_100 --output results/cnn_v4/esp32_end_to_end/REAL_MIT100_metrics.json
```

Giữ đủ boot/model/golden22/22, BEGIN/END, peak/beat và summary. Evaluator hỗ trợ cả UTF8 và PowerShell UTF16 transcript, từ chối log thiếu/queue-drop hoặc code/score hỏng. INCART đổi mode record và tên build/log tương ứng. Mỗi lượt dùng filename mới, không ghi đè.

Benchmark: build `-Mode BENCH_INT8` rồi `idf.py ... -B .../build_bench_int8_MITBIH_100 -p COM3 flash monitor`; FP32 tương tự `BENCH_FP32`/`build_bench_fp32_MITBIH_100`. Lưu log riêng, bỏ run−3..−1 khỏi thống kê warm; so mean/median/p95/min/max/SD cùng fixture/run, score và disagreement tại0,88; báo cold riêng. Flash/monitor có thể reset nên chỉ chạy sau phê duyệt. Nếu allocation/Invoke/golden lỗi, dừng, giữ log, không sửa reference/threshold để PASS.
