# ESP32 V4 INCART PVC replay — 20/11/2026

**Flash PASS; Golden22/22 EXACT; phiên replay/evaluator PASS.** Đây là xác minh kỹ thuật trực tiếp trên ESP32, không phải kết luận accuracy đạt nghiệm thu hoặc kiểm thử ADC analog. Recall PVC thực đo trên đoạn này là45%; không thay đổi đoạn/threshold/detector để tăng số liệu.

## Firmware, protocol và thiết bị

Nạp snapshot REPLAY `INCART_PVC_V1` đã khóa, không rebuild hoặc dùng cache nhầm mode. Application347.440bytes, SHA256 `2a85f7922caddf802ac3e1927c0c0739a7ac7b180cef68533d242111b2009418`; ELF boot prefix `df119523d...` khớp snapshot ELF. esptool4.13.0 exit0, cả3 vùng ghi đều báo Hash of data verified. `--after no_reset` giữ bootloader; sau đó capture tạo file trước một EN reset đo. Không tự retry/flash tiếp.

Thiết bị ESP32-D0WD-V3 revision3.1, MAC `b0:3f:d3:51:8b:ec`, crystal40MHz. Boot xác nhận CPU160.000.000Hz, ESP-IDF5.4.4, reference_active1/esp_nn_effective0, TFLM1.4.2. UART yêu cầu115200, driver báo115201. Thông tin đầy đủ ở `device_info.json`, `flash.log`, `flash_status.json`, `preflight.json`.

V4 INT8 hash `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`, threshold0,88/code≥98. Firmware boot in0,879999995 là biểu diễn float32, không thay threshold. Preprocessing/detector/kernel/model giữ nguyên.

Protocol `c87f8de8e6e6623b7c8e9ed46055e06a2ca7e1a16ab7100133084af2ad769fec`; stream `3c22e5aed668a003f774272d4896b07fbc1ba57f603de227897b595920c43086`; annotation `779bd42aa43ec542228545edf4b93fa0fae93f88f62f87e4e7e3a11d0fb7d333`. INCART Validation I08/II,466,00–527,44s,43N/20V/0OTHER. Nhãn chỉ chấm sau inference. Không dùng annotation I08 cũ hoặc Final Test.

## Thu UART và evaluator

`uart_raw.log`:666.518bytes, SHA256 `53d97bb1d96460d93e82db6cfcea9999e824af6d18b46d2748fa70cf9ca82ecb`. Capture trực tiếp pyserial, không Start-Transcript. Toàn phiên133,101s trong timeout240s; một boot ID `687938e9`, đủ golden0..21, BEGIN → PEAK/BEAT → `V4_PIPELINE_SUMMARY` → END, không reset bất thường. Model/stream hash và toàn bộ22 output golden được đối chiếu với fixture đã khóa.

Evaluator chạy đúng protocol mới, exit0, tạo `evaluation.json`:

```powershell
.\.venv\Scripts\python.exe python/evaluate_v4_board_replay.py results/cnn_v4/esp32_end_to_end/board_runs/INCART_PVC_V1_20261120_145655/uart_raw.log --record INCART_PVC_V1 --protocol results/cnn_v4/esp32_end_to_end/pvc_replay_v1/protocol.json --output results/cnn_v4/esp32_end_to_end/board_runs/INCART_PVC_V1_20261120_145655/evaluation.json
```

**Cảnh báo ranh giới capture, giữ nguyên raw:** file dừng giữa một status tuần hoàn cuối seq738, còn511bytes chưa kết thúc newline/JSON, ở offset666007, sau END offset660557. Phân tích đầu tiên theo `splitlines()` báo1 CRC lỗi vì coi fragment là frame; kiểm tra ranh giới xác nhận **738 frame có newline đều CRC đúng**,0 frame hoàn chỉnh lỗi. Không có bằng chứng lỗi truyền giữa phiên. Fragment status sau END không dùng trong metrics; không cắt/chữa/ghi đè raw để PASS. Xem cả `uart_crc_diagnostics.json` và `uart_boundary_analysis.json`. Capture/evaluator PASS không có nghĩa mọi byte cuối file tạo thành một frame hoàn chỉnh.

## So sánh host và ESP32

| Chỉ số | Host ungated | ESP32 gate thật |
|---|---:|---:|
| TP |9|9|
| FP tổng |1|1|
| FN |11|11|
| TN |41|40|
| PVC Precision |90%|90%|
| PVC Recall |45%|45%|
| PVC F1 |60%|60%|
| Peak TP /FP /FN |59 /19 /4|59 /19 /4|
| R-peak |78|78|
| Window hoàn tất |78|78|
| Invoke /classified |78|77|
| Rejected |0|1|
| N abstention |2|3|
| Queue /block drops |không mô phỏng RTOS|0 /0|
| Mẫu bị mất |0, đọc file deterministic|0, telemetry/GPTimer|

78 peak index khớp host. Tất cả **77 window cùng được inference có output code exact**, max delta0LSB. Sai khác duy nhất: R15214 (record index131714), N, host code−120; board không gọi CNN vì `SIGNAL_CHANGED_BEFORE_INFERENCE` khi cuối stream đã dừng cập nhật mẫu. Beat result timestamp128472101µs, last sample128422133µs, cách49.968µs vượt freshness gate20.000µs. Đây là abstention do safety/EOF, không phải model bị lượng tử hóa sai. TN giảm1; TP/FP/FN không đổi. Không sửa gate hoặc bỏ nhịp này khỏi hạch toán.

20PVC =9TP +9 có window nhưng CNN dự đoán Normal +2 không match peak. Không PVC nào bị clipping/window/gate loại trong phiên này. FN9 có thể gồm ảnh hưởng localization của detector-centered window; không tự quy kết hoàn toàn weights nếu chưa phân tích morphology. Không thực hiện tuning hoặc phân tích để chọn lại đoạn trong lượt đo.

## Hạch toán đúng43N và unmatched

- **Host:43N =41TN +0 N→PVC +2 detector miss.**
- **ESP32:43N =40TN +0 N→PVC +2 detector miss +1 safety rejection EOF.**
- FP1 của cả hai là **unmatched alarm**, không thuộc43 reference N. Vì vậy TN41+FP1=42 không biểu diễn42 nhịp N được chấm. Missing N không được tính TN; phần FP unmatched làm bảng TP/FP/FN/TN là metric sự kiện mở rộng, không phải ma trận đóng bao phủ toàn bộ63 annotation.
- **20V =9TP+11FN** ở cả hai. Không nhịp PVC bị bỏ được chuyển thành dự đoán đúng.

19 peak không ghép: tất cả ngoài tolerance±38mẫu với annotation gần nhất (khoảng cách tuyệt đối41–149mẫu).18 dự đoán Normal,1 dự đoán PVC. Không có OTHER trong đoạn, nên không thể giải thích chúng là OTHER bị loại. Nhiều candidate xuất hiện khoảng75mẫu sau N, nhưng chỉ timing không chứng minh T/P/nhiễu hay secondary QRS. Không đổi tolerance/annotation để ghép lại.

Alarm unmatched duy nhất ở peak9905 (record126405), code119, nearest annotation V9964, lệch−59mẫu/−236ms. Annotation V9964 không có match khác, nên protocol hiện tại đồng thời tính một unmatched FP và một detector-missed PVC FN trong cùng vùng. Điều này chỉ chứng minh lỗi timing/matching theo tiêu chí đã khóa; chưa chứng minh peak đó là nhiễu hoặc không phải QRS thật. Giữ nguyên cách chấm. Toàn bộ khoảng cách, nhãn gần nhất và code được lưu ở `unmatched_peaks.csv`; từng reference được hạch toán ở `reference_accounting.csv`.

## Số đo board

| Đại lượng | Giá trị |
|---|---:|
| Stream |15.360mẫu,61,44s|
| Acquisition frequency telemetry |249,999755Hz|
| dt mean/min/max |4.000,004 /3.475 /4.524µs|
| Invoke mean/min/max,77 lần |84,777 /84,313 /85,213ms|
| Preprocessing mean/min/max,77 lần |3,874 /3,708 /4,649ms|
| R timestamp→result mean/min/max |1.202,063 /675,054 /1.690,722ms|
| Arena used /allocated |6.124 /65.536bytes|
| Heap free tại END /minimum |169.192 /160.420bytes|
| Heap free telemetry sau replay task exit |173.648bytes|
| Worker stack free/high-water telemetry |8.304bytes|
| Queue /block /sample drops |0 /0 /0|
| UART write /format /TX drop counters |0 /0 /0|

Latency R→result gồm chờ đủ+127mẫu, batch/queue, preprocessing và Invoke; không chỉ Invoke và không bao gồm analog delay. Khác biệt heap trước/sau do replay task được xóa, không trộn hai thời điểm. Runtime memory lấy đúng log phiên này, không thay bằng build hoặc golden cũ.

## Bằng chứng và kết luận

- `uart_raw.log`: UART nguyên bản; `capture_status.json`: boot/reset/markers/timeout.
- `evaluation.json`: kết quả evaluator; `analysis.json`: số đo/đối chiếu và bản phân tích CRC sơ bộ; diễn giải CRC cuối cùng tại `uart_boundary_analysis.json`.
- `beats.csv`, `reference_accounting.csv`, `unmatched_peaks.csv`, `host_board_by_peak.csv`: chứng cứ từng nhịp.
- `preflight.json`, `flash.log`, `flash_status.json`, `device_info.json`: hash, flash và thiết bị.

**Xác minh kỹ thuật thành công**: V4 đúng hash chạy trên ESP32, golden exact, stream đủ/single boot, output77/77 khớp host trên window chung, không drop. **Không nghiệm thu khả năng phát hiện PVC tốt**: trên đoạn phát triển này chỉ phát hiện9/20PVC (Recall45%, F160%). Development đã dùng khi phát triển/chọn V4; đây không phải kiểm thử tổng quát hóa độc lập hay ADC analog. Dừng sau phép đo này; không benchmark FP32, INCART đoạn khác hoặc ADC. Có thể xem xét phân tích các FN/localization ở lượt sau nếu được yêu cầu, không tự tuning/train hay chạy thêm board.
