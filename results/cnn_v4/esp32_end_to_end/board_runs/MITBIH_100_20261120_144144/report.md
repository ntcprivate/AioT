# ESP32 V4 MITBIH_100 replay — 20/11/2026

**Thu UART và evaluator PASS.** Không flash lại, không đổi firmware/model/threshold/detector/evaluator. Chỉ COM3/115200, một EN reset có chủ đích, timeout240s. Capture hoàn tất sau133,194s, không timeout/reset thêm. Đây là board replay số, không phải ADC analog hoặc bằng chứng accuracy PVC.

## Hai log trước

- `firmware/esp32_ecg_v4_experiment/log.esp32_ecg_v4_experiment.20261119130501.txt`:16 dòng golden, fixture1..16, tất cả EXACT_MATCH; một boot ID `d9ca79c7`, telemetry từ3,587s đến53,057s. Thiếu cả đầu phiên và phần hoàn tất. Không thấy panic/reset/FAILED trong phần đã ghi. Chưa có bằng chứng model lỗi hoặc treo; log đã dừng khi golden còn chạy. Phiên mới chứng minh firmware có thể hoàn tất với cùng model, không cần flash.
- `log.esp32_ecg_v4_experiment.20261120143453.txt`:14 dòng, fixture0 rồi0..12; boot ID `d58e241a` đổi sang `4c63110c`, uptime trở về dưới1s, có `rst:0x1 (POWERON_RESET)`. Đây là bằng chứng hai lần boot, không phải14/22 fixture độc lập. Sau reset log chỉ đến39,797s. Không thấy golden FAILED hoặc panic. Không đủ bằng chứng để kết luận reset do nguồn, nút EN hay Serial Monitor điều khiển DTR/RTS.

Chi tiết hash/timeline: `../prior_log_diagnosis_20261120.json`. Hai log cũ giữ nguyên.

## Trình tự thực tế trong source

`main/replay_main.cpp`: UART → hash stream → cấu hình GPTimer (chưa start) → pipeline worker/telemetry → replay task đợi `model_ready` tối đa120s. `pipeline.cpp` chỉ đặt ready sau `model_init() && model_golden_test()`.

`model.cpp`:22 fixture, mỗi fixture3 warm-up+30 Invoke đo và `vTaskDelay(1)` sau từng lần; chỉ in một `ECG_GOLDEN` cho mỗi fixture. Như vậy tổng726 Invoke, không phải22 Invoke. `ECG_GOLDEN_DONE samples=22 failed=0 status=PASSED` mới giải phóng replay. Chi phí khởi động vì vậy vượt thời gian hai log cũ đã lưu.

Marker đúng theo thứ tự:

1.22 dòng `ECG_GOLDEN` và `ECG_GOLDEN_DONE`.
2.`V4_REPLAY_BEGIN`.
3.`V4_PEAK`, `V4_BEAT`, telemetry/gate events trong61,44s stream.
4.`V4_PIPELINE_SUMMARY` sau khi stop timer và đợi2s.
5.`V4_REPLAY_END`.

Không có marker tên `V4_REPLAY_SUMMARY` trong firmware. Evaluator dùng `V4_PIPELINE_SUMMARY`. Không sửa evaluator để chấp nhận marker thiếu.

## Phiên mới và tính toàn vẹn

- UART raw: `uart_raw.log`,692.025bytes, SHA256 `1fbe94640a85b39f843e11ce1ab41d1796e423b6a32f3dea0cfe614acb97b6d8`.
- Một ROM boot, một telemetry boot ID `f7214f94`; golden IDs0..21 duy nhất,22/22 code khớp cả reference trên board lẫn fixture đã khóa.
- Model SHA256 `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`; stream hash `79e989ecfc3e964d914137e0fe601f285405d16856da3a614564bcb8d53e64a3`.
- BEGIN/SUMMARY/END và GOLDEN_DONE xuất hiện đúng một lần, đúng thứ tự, cùng boot. END `stream_complete=1 missed=0`.
-739 frame telemetry hợp lệ,0 CRC lỗi; write_errors/format_errors/tx_dropped cuối phiên đều0.
- Script capture mới `python/capture_v4_mit100_uart.py`: mở file mới trước reset; cấu hình DTR/RTS rồi một xung EN; không tự retry/reset/flash. `.venv` thiếu pyserial nên lần gọi đầu dừng ngay tại import, chưa mở COM/reset. Dùng pyserial đã có trong Python ESP-IDF cho phiên thật, không cài package.

## Kết quả thực đo

| Hạng mục | Kết quả |
|---|---:|
| Mẫu phát lại |15.360|
| R-peak detector |73|
| Window đã hoàn tất/log |72|
| Invoke/classified |65|
| Rejected |7|
| Queue drops / block drops |0 / 0|
| Missed samples |0|
| dt mean/min/max, từ telemetry |4.000 /3.879 /4.121µs|
| Invoke mean/min/max,65 lần |84,809 /84,382 /85,270ms|
| R→result mean/min/max,65 kết quả hợp lệ |1.236,052 /812,189 /1.665,779ms|
| Tensor arena used/allocated |6.124 /65.536bytes|
| Internal heap free/min cuối phiên |169.192 /160.420bytes|

7 rejected:6 `INPUT_QUANTIZATION_CLIPPING`;1 `SIGNAL_CHANGED_BEFORE_INFERENCE` ở R15089. Beat cuối này xử lý khi mẫu đã ngừng cập nhật sau EOF: result128.528.778µs, last sample128.422.075µs, chênh106.703µs vượt gate20.000µs. Gate được giữ nguyên, không suy luận trên dữ liệu quá cũ. R15298 chưa có đủ đuôi+127 trước EOF, nên chưa tạo window. Không gộp hai trường hợp này vào lỗi model.

`evaluation.json`: peakTP73/peakFP0/peakFN3; classification TN64, FP0, TP0/FN0; matched OTHER1, missing N abstentions11. Có75 N và0 PVC trong đoạn đã khóa. Vì không có PVC, Precision/Recall/F1 PVC không có ý nghĩa đánh giá ở phiên này (JSON dùng0 khi mẫu số0). Không tuyên bố phát hiện PVC đầu cuối PASS. Bài đo chỉ PASS tính đầy đủ phiên/evaluator và vận hành stream này.

Chi tiết mỗi beat: `beats.csv`; số đo/tổng hợp CRC: `measured_summary.json`; trạng thái capture/reset/time: `capture_status.json`.

## Evaluator đã chạy nguyên trạng

```powershell
.\.venv\Scripts\python.exe python/evaluate_v4_board_replay.py results/cnn_v4/esp32_end_to_end/board_runs/MITBIH_100_20261120_144144/uart_raw.log --record MITBIH_100 --output results/cnn_v4/esp32_end_to_end/board_runs/MITBIH_100_20261120_144144/evaluation.json
```

Exit0, JSON được tạo thành công. Không cần nới marker/matching hoặc sửa model/reference.

## Bước tiếp theo đề xuất, chưa thực hiện

Giữ bộ log mới làm bằng chứng replay MIT100 hoàn chỉnh. Muốn kiểm chứng khả năng PVC phải khóa một protocol Train/Development chứa PVC trước khi chạy lượt mới, không sửa detector/threshold theo Test. Chưa chuyển INCART, FP32 benchmark hoặc ADC; chưa chạy thêm reset. Cần người dùng cho phép phạm vi mới trước các phép đo đó.
