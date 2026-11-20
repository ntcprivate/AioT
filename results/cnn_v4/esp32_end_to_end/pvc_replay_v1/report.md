# Chuẩn bị replay có PVC — 20/11/2026

**Chuẩn bị/build PASS; phần cứng CHƯA CHẠY.** Không COM3, flash/reset, train, tuning, Final Test, commit hoặc push. Kết quả host chưa đạt Recall PVC cao; giữ nguyên dữ liệu và thuật toán để đo trung thực.

## Chọn đoạn và khóa trước inference

`selection_rule.json` được ghi trước khi quét: chỉ INCART Validation theo split V4; record ID tăng dần, start tăng dần theo grid1s; cố định61,44s/15.360mẫu; tối thiểu20N và20V trong `[start+1000,end−256)` để có4s khởi động và1,024s đuôi. Đây chỉ là điều kiện chọn; **chấm tất cả annotation trong stream**, không loại nhịp đầu/cuối khỏi mẫu số. Chọn cửa sổ hợp lệ đầu tiên, không tối đa hóa F1 hay score. Không có fallback tự ý giảm số PVC hoặc đổi duration. Không đọc waveform trước khi khóa lựa chọn, không mở model trước khi khóa protocol.

Đã chọn **I08 / INCART Validation, lead II**, source257Hz; resample toàn record bằng250/257 rồi crop:

- Start250Hz116.500 (**466,00s**); end exclusive131.860 (**527,44s**).
- Stream15.360mẫu, **43N /20V /0OTHER**, không có rail sample theo margin16.
- Mapping cố định kế thừa: `clip(rint(2048+200*mV),0,4095)`, round-to-even. Annotation `floor(source_sample*250/257+0.5)−116500`.
- Cấu hình tham chiếu giữ matching chronological one-to-one nearest unused, tolerance±38mẫu, tie lower detection index. Matched OTHER là beat TP detector nhưng loại khỏi N/V; unmatched PVC là FP alarm, không tự gọi là noise; mất V ở detector/window/gate đều FN, mất N là abstention chứ không TN.

20PVC đủ làm một pilot kỹ thuật có N/V, nhưng mẫu nhỏ và cùng một đoạn/patient, không đủ chứng minh độ chính xác hay tổng quát hóa độc lập. Validation này đã tham gia phát triển V4; không phải Test độc lập mới.

## Hash đã khóa

| Artifact | SHA-256 |
|---|---|
| `protocol.json` | `c87f8de8e6e6623b7c8e9ed46055e06a2ca7e1a16ab7100133084af2ad769fec` |
| Stream `INCART_PVC_V1.bin` | `3c22e5aed668a003f774272d4896b07fbc1ba57f603de227897b595920c43086` |
| `annotations.json` | `779bd42aa43ec542228545edf4b93fa0fae93f88f62f87e4e7e3a11d0fb7d333` |
| Firmware application snapshot | `2a85f7922caddf802ac3e1927c0c0739a7ac7b180cef68533d242111b2009418` |

Protocol chứa cả hash `.hea/.dat/.atr`, selection rule/choice, nhãn đầy đủ và đường dẫn. `protocol.sha256` dùng để xác minh trước chấm. Không thay protocol sau khi đã xem inference.

## Host: kết quả thực, không điều chỉnh theo kết quả

Native runner dùng đúng detector/window/preprocessing C++ hiện hành, V4 TFLM host và kernel đã kiểm chứng. Chỉ sau hai process detector/inference kết thúc, Python mới mở annotation để chấm. Không RR, nhãn trước hay annotation làm input classifier.

| Chỉ số host | Giá trị |
|---|---:|
| Peak |78|
| Peak TP /FP /FN |59 /19 /4|
| Window /inference |78 /78|
| Window bị loại /pending cuối đoạn |0 /0|
| TP /FP /FN /TN |9 /1 /11 /41|
| PVC Precision /Recall /F1 |90% /45% /60%|
| PVC mất do detector |2|
| PVC có window nhưng dự đoán Normal |9|
| PVC mất do window/normalization/clipping |0|
| Normal abstention |2|
| PVC alarm trên peak unmatched |1|

FP1 là unmatched PVC alarm;19 peak unmatched không đồng nghĩa19 peak noise hoặc19 cảnh báo PVC. Không tự phân loại sinh lý T/P/nhiễu khi chưa có bằng chứng waveform. FN9 trên detector-centered window không đủ tách riêng giới hạn CNN và độ lệch tâm detector; chỉ ghi đúng điểm thất bại trong pipeline.

`host/events.csv` ghi peak/window/issues, `host/beats.csv` ghi local/global peak index, symbol ghép sau inference, timing error, rejection, output code, probability/prediction và Invoke **HOST** microseconds; `host/evaluation.json` có metric và phân rã lỗi. Host file scan không mất mẫu, nhưng không suy ra ESP32 sẽ không mất mẫu. Đánh giá **ungated**, không mô phỏng RTOS/lead-off/quality recovery/generation/tuổi prediction; không trình bày là kết quả board. Queue drops, RAM/arena và latency board đều PENDING.

Không đổi đoạn để cải thiện Recall45%; không thay threshold0,88/code≥98, detectorconfirmation50/refractory75, preprocessing hay weights.

## Firmware, tests, build và bảo toàn

Trong project V4 thêm record option `INCART_PVC_V1`, stream và `main/pvc_replay_identity.h`; `replay_main.cpp` chỉ thêm nhánh chọn asset/header. CMake root/main và build helper thêm allowlist/define tương ứng. Model, `signal.cpp`, `pipeline.cpp`, `preprocessing.h` và Conv/FC adapter không đổi hash so bản chuẩn bị trước. Nhãn/annotation/protocol không được embed vào firmware; chỉ model,22 golden reference và raw stream được embed. Golden labels chỉ phục vụ boot self-test, không điều khiển detector/inference stream.

Evaluator thêm `--record INCART_PVC_V1 --protocol ...`, xác minh hash protocol/annotation/stream identity và giữ nguyên hàm matching/chấm/kiểm tra phiên. Không bỏ qua marker/rejection/drop. Capture utility thêm record ID để không lưu nhầm vào thư mục MIT100; chưa chạy capture.6/6 evaluator regression tests PASS; Python scripts compile PASS.

Build **PASS** ESP-IDF5.4.4, CPU160MHz, Ninja-j1, reference kernels/ESP-NN off. Binary347.440bytes, DRAM tĩnh43.228bytes, IRAM tĩnh54.066bytes. Đây không phải RAM runtime. Snapshot `build/application.bin`, `.elf`, bootloader/partition/sdkconfig và manifest/hash tại `build_verification.json`. Cache `build_adc_MITBIH_100` hiện được cấu hình record PVC; không suy ra record từ tên thư mục. Binary/log MIT100 đã PASS nằm riêng, raw UART MIT100 hash xác minh không đổi. Firmware V1 không sửa.

Các file mới chính:

- `python/prepare_v4_pvc_replay.py`, `python/check_v4_pvc_host.py`.
- `firmware/esp32_ecg_v4_experiment/main/assets/INCART_PVC_V1.bin`, `main/pvc_replay_identity.h`.
- Thư mục này: selection rule/choice, protocol/hash, annotation, host logs/metrics, build log và binary snapshot/report.
- File đã bổ sung option: CMake root/main, `main/replay_main.cpp`, `build.ps1`, evaluator/capture utility. Không thay model hoặc thuật toán.

## Rủi ro và bước tiếp theo, CHƯA thực hiện

Sẵn sàng xin phép đo kỹ thuật đoạn PVC này, **không coi accuracy PASS**. Host cho Recall45%, nhiều unmatched peaks và9 PVC bị phân loại Normal; board có thể thấp hơn do quality/gap/age gate. Kết thúc stream có thể tạo stale rejection như MIT100.6,14KiB arena đã đo ở golden/MIT100 không thay cho phép đo pipeline mới. Phải thu đầy đủ một boot/golden22/22/BEGIN/PEAK/BEAT/PIPELINE_SUMMARY/END; nếu reset, timeout, golden lỗi hoặc log thiếu thì FAIL phiên, không sửa evaluator để cứu kết quả.

Chỉ sau khi người dùng phê duyệt, build record trong thư mục riêng rồi nạp. Cần bench không nối người. Ví dụ **CHƯA CHẠY**:

```powershell
& .\results\cnn_v4\esp32_end_to_end\build.ps1 -Mode REPLAY -Record INCART_PVC_V1
idf.py -C firmware/esp32_ecg_v4_experiment -B firmware/esp32_ecg_v4_experiment/build_replay_INCART_PVC_V1 -p COM3 flash
# Không mở thêm Serial Monitor; capture tạo file trước EN reset đúng một lần:
& 'C:\Espressif\tools\python\v5.4.4\venv\Scripts\python.exe' python/capture_v4_mit100_uart.py --record INCART_PVC_V1 --port COM3 --timeout 240 --bench-reset-once
# Thay REAL_RUN bằng thư mục capture thực tế vừa tạo:
.\.venv\Scripts\python.exe python/evaluate_v4_board_replay.py results/cnn_v4/esp32_end_to_end/board_runs/REAL_RUN/uart_raw.log --record INCART_PVC_V1 --protocol results/cnn_v4/esp32_end_to_end/pvc_replay_v1/protocol.json --output results/cnn_v4/esp32_end_to_end/board_runs/REAL_RUN/evaluation.json
```

Sau đo báo TP/TN/FP/FN, P/R/F1, peak misses, inference/rejected, queue/block/sample drops, latency và evaluator PASS/FAIL; tách lỗi detector/window/gate/classifier, giữ mọi FN. Không chạy protocol khác hoặc điều chỉnh model/tham số khi chưa được phép.
