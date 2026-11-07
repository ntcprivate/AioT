# AI LIVE và cleanup dự án

## Kết quả

Đã flash bản main ESP-IDF5.4.4 mới lên COM3 sau xác nhận bench/simulator không
nối người. Main tự chọn `ECG_AI_LIVE`: ADC250Hz → quality gate → detector2B/FIFO
→256 mẫu → preprocessing/CNN INT8 hiện có → telemetry `ai.mode=AI_LIVE` → GUI.
Không còn mode Shadow hoặc khóa nghiệm thu offline trong đường chạy main.

GUI giữ một panel và một snapshot cho header/kết quả: AI LIVE + N/PVC khi hợp
lệ; WAITING + UNKNOWN khi chưa có prediction; INVALID/leads-off/gap/stale/mất
kết nối → UNKNOWN. CSV nay dùng cùng chính sách/source/xác suất với GUI, giữ
nguyên cột và raw samples. Adapter chỉ đọc capture `research` cũ, không phải
luồng inference thứ hai. Chú thích prototype và các kiểm tra an toàn vẫn giữ.

## Đã gỡ và sửa

- Gỡ `kLivePipelineValidated`, `classification_allowed`, option
  `ECG_ENABLE_EXPERIMENTAL_LIVE`, option Shadow và nhánh inference cũ trùng lặp.
- Gỡ publish/PVC-hold cũ nối prediction với FSM LED/buzzer. CNN main không gọi
  cảnh báo; GPIO/ADC, self-test phần cứng và công cụ diagnostic vẫn giữ.
- Gỡ wrapper `model_invoke_beat` không còn caller; actual quantized Invoke,
  preprocessing, weights, threshold0.52, golden và detector/FIFO không đổi.
- Telemetry vẫn ECG1v2/CRC32; model báo READY thay trạng thái khóa, một object
  `ai` chứa prediction. TEST_ONLY/Synthetic không chạy ADC inference.
- Gỡ điều kiện ai_validated/r_validated/approval trong CSV. Đổi tên trạng thái
  offline thành DETECTOR_CRITERIA_FAIL để chỉ phản ánh phép đánh giá; không
  đổi tiêu chí hoặc tham số chấm điểm.
- GUI/parser/session chuyển sang `ecg_monitor/ai.py`; giữ nguyên logic đồng bộ
  header đã hoàn thành. Cập nhật test, helper bench/GUI và README hiện hành.

Xóa hai source đã thay thế hoàn toàn: `ecg_monitor/research.py` và
`run_research_shadow_bench.py`. Thay bằng `ecg_monitor/ai.py`,
`run_ai_live_bench.py`; `bench_flash.py` dùng backup MD5 từng vùng. TEST_ONLY
backup đúng firmware hiện tại vào session riêng trước khi thử, không phục hồi
một firmware lịch sử mặc định. Bản source/ảnh build trước sửa vẫn lưu trong
`debug/ai_live/before/` và `before_artifacts/`.

Đã rà soát138 file source thuộc dự án, gỡ import không dùng đã xác nhận bằng
AST/tham chiếu, giữ hai golden metadata header trùng hash vì hai project cần
chúng. Chỉ dọn bytecode cache đã kiểm tra không tracked/không chứa dữ liệu;
xác nhận xóa cụ thể trong `cleanup_deleted.json`. Không xóa build snapshot,
host exe/compile metadata còn được test tham chiếu hoặc file chưa chắc dư.

## Kiểm thử và build/flash

| Phạm vi | Kết quả |
|---|---|
| Python GUI/parser/CSV/mode/FC14 liên quan | 78 PASS, 0 FAIL |
| C++ queue/window và recovery/quality/CRC/GPIO pattern | 2 PASS |
| Host golden12 +8 FC14 input duy nhất | 20/20 EXACT so reference TF đã lưu |
| Build main / TEST_ONLY / Synthetic | 3 PASS |
| ESP32 main golden | 12/12 EXACT, cold/warm/30 lần đo ổn định |
| Capture main90 giây | ADC250Hz; CRC=0; missing=0; TX drops=0 |
| ADC error / missed slots / late | 0 /0 /9; không tuyên bố không có jitter |
| Heap internal free / minimum | 152996 /144160 bytes |
| AI task minimum stack free | 9392 bytes |
| GUI đọc COM thật | PASS;3552 mẫu; CRC=0; missing=0 |

Board hiện giữ main AI_LIVE; model=READY, không phát trạng thái khóa. SHA app:
`c3abd72cc35e70d36f6a8e00230a2fb3c62b39fbcd8e40713c4674c999cae8fe`.
Backup byte-exact mọi sector bị chạm được đọc/xác minh MD5 trước flash; esptool
xác minh hash sau ghi. Thông tin đầy đủ trong `debug/ai_live/results.json`.

**Đầu vào bench hiện LEADS_OFF**, nên classified=0, ADC inference_calls=0 và
GUI hiển thị UNKNOWN/LEADS_OFF đúng yêu cầu. Đây là quality gate, không phải
khóa F1. Chưa quan sát N/PVC qua analog hợp lệ trên board trong lượt này;
không tạo tín hiệu/prediction thay thế để ép PASS. Cần nguồn mô phỏng phù hợp
vượt gate để kiểm thử analog end-to-end tiếp. Golden parity không phải accuracy.

Không train, retune, đổi weights/dataset/splits, chạy lại benchmark hoặc toàn
bộ đánh giá offline. Kết quả F1/record121 và giới hạn nghiên cứu trước không
thay đổi. Không push/commit hoặc sửa Git history/GitHub backup.

## Giữ lại và cách chạy

Giữ training/conversion/evaluation, ModelV1/weights/INT8, dataset/splits,
golden/TEST_ONLY/Synthetic, CSV/raw capture, báo cáo và ảnh firmware trước.
`research_shadow.h` vẫn là file của **một Engine duy nhất**, giữ tên vì các
harness replay đang tham chiếu; không còn mode/gate Shadow. Các generator báo
cáo lịch sử và snapshot cũ vẫn giữ để tái lập bằng chứng; chữ trạng thái cũ
trong chúng không điều khiển runtime. Các cache môi trường/thư viện và artifact
đang cần cho build/test không bị xóa.

Đóng GUI cũ rồi mở `tools/ecg_monitor/Start_ECG_Monitor.bat` → HARDWARE MONITOR
→ COM3 → Connect → Start Monitoring. Không cần bật mode nghiên cứu riêng.
Với firmware hiện đã flash, đầu vào hợp lệ sẽ được CNN xử lý trực tiếp;
đầu vào bench hiện tại vẫn phải UNKNOWN do LEADS_OFF.

Research prototype — Not for medical diagnosis.

Cache cleanup confirmed: 5 directories, 48 bytecode files, 766414 bytes removed.
