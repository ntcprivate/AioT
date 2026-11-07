# Research Shadow Mode

Ngày 07/11/2026 (Asia/Saigon). **AI-live chính thức vẫn LOCKED.**

## Kết luận đúng phạm vi

**Đã hoàn thiện đường xử lý và GUI nghiên cứu; chưa chứng minh N/PVC từ ADC hợp lệ trên board hiện tại.** Host replay qua C++ thật + CNN native tạo NORMAL/PVC và khớp TensorFlow. ESP32 chạy golden đúng, nhưng AD8232 hiện LEADS_OFF/chạm rail nên Shadow giữ UNKNOWN/INVALID, không gọi CNN trên ADC. Đây là PENDING nguồn mô phỏng analog hợp lệ, không ép PASS bằng bỏ gate.

## Thiết kế và file

- `main/Kconfig.projbuild`: `ECG_RESEARCH_SHADOW` mặc định OFF; chỉ bản riêng bật. Loại trừ official-live, TEST_ONLY và Synthetic. `debug/research_shadow/sdkconfig.research` / `build_research_shadow` độc lập.
- `main/research_shadow.h`: detector2B và FIFO2A nguyên trạng; thêm queue4 cửa sổ sao chép bất biến trong RAM tĩnh, một model worker sở hữu. Không tạo task theo beat. Metadata R sample/timestamp được đổi về chỉ số ADC thực sau startup/reset.
- `main/pipeline.cpp/.h`: quality/recovery gate hiện tại → detector/window → kiểm tra tuổi → preprocessing nguyên trạng → loại quantization clipping → kiểm tra generation sát Invoke → CNN → kiểm tra lại generation. Queue block2 không chờ ADC; overflow có counters/reason và fail closed. Không gọi publish/FSM cảnh báo chính thức từ Shadow.
- `main/telemetry.cpp`: thêm object `research` vào status ECG1 v2/CRC32 hiện tại; official classification=UNKNOWN, model=LOCKED, p_pvc=null không đổi. Nhãn nghiên cứu `mode=RESEARCH_SHADOW`, `source=ADC_CNN`, `experimental=true`. Buffer JSON/frame lớn hơn nằm tĩnh, riêng task TX. Shadow TX ưu tiên5, AI4; các cấu hình thường giữ TX2. Không đổi queue6/baud115200/GPTimer250Hz.
- `tools/ecg_monitor/ecg_monitor/research.py`, `protocol.py`, `session.py`, `app.py`: vùng **RESEARCH AI — EXPERIMENTAL** riêng, xác suất/timestamp/age/latency/counters/reason; main AI vẫn LOCKED. Result TTL1500ms; Stop/Disconnect/reboot/đổi source xóa trạng thái. Sau Reconnect phải chờ result mới hơn epoch kết nối. Raw flags lead-off/clip/gap chặn ngay tại GUI; invalid cũ không thể được result cửa sổ chồng lên ghi đè.
- `tests/research_shadow_test.cpp`, `tests/research_shadow_replay.cpp` và `tools/ecg_monitor/tests/test_research_shadow.py`: regression C++/parser/GUI. Các tool `verify_shadow_replay.py`, `run_research_shadow_bench.py`, `gui_research_board_smoke.py`, `report_research_shadow.py` tái lập bằng chứng.

Giữ nguyên model/weights, preprocessing, threshold0,52, detector/FIFO, main lấy mẫu/GPIO và `system_state.h`. SHA bảo toàn trong JSON. Không train/tuning trên Validation/Test. Các biểu đồ/chỉ số ADC/TX/RX/CRC còn trong monitor; kéo panel phải để xem thêm. CSV classification vẫn là kênh chính thức UNKNOWN; raw capture giữ đầy đủ research object.

## HOST / REPLAY

- 82 unittest PASS, gồm GUI/telemetry/FC14, detector/FIFO và14 test Shadow. C++ mới kiểm tra copy bất biến, nhiều cửa sổ/ring wrap/index sau reset, queue đầy, stale, leads/clip/gap/noise, no R; đối chiếu byte cửa sổ với detector nguyên trạng. GUI kiểm tra xác suất từ golden thật, Stop/Disconnect/Reconnect và kết quả cũ.
- Frozen Train record208, 60giây/15.000 mẫu: 99 cửa sổ, native/TF 99/99 EXACT; dự đoán N=66, PVC=33; queue high=3, drops=0. Rounding annotation `(sample*25+18)//36`, matching greedy ±12 mẫu như cũ; không chọn lại tham số.
- Matched N/V confusion rows N,V: `[[61,0],[1,27]]`; 1 PVC→NORMAL là lỗi CNN trong smoke replay. Trước CNN bỏ5 N/V (3N,2V); 12 reference khác nhãn N/V không đổi thành Normal. Đây là dữ liệu Train đã dùng, không phải đánh giá accuracy độc lập.
- FC14: regression host đối chiếu đủ16 operator/8 input hiện tại; bằng chứng board8/8 và parity9.425/9.425,33.586/33.586 trước đó tái sử dụng với source/model SHA bảo toàn, không gọi đó là chạy lại toàn corpus.

## Build và firmware đã flash

| Cấu hình | Build | Bytes | Shadow | Official-live |
|---|---|---:|---|---|
| build_research_shadow | PASS | 331552 | True | LOCKED |
| build | PASS | 317808 | False | LOCKED |
| build_synthetic_telemetry_test | PASS | 316368 | False | LOCKED |
| build_ai_test_only_adc | PASS | 348576 | False | LOCKED |
| build_ai_test_only_synthetic | PASS | 346816 | False | LOCKED |

Board hiện giữ **build_research_shadow**. App SHA256 `6c5e1be63830f3797e6f656ba6197db5e32f168ece3b9c9cbfb50a9bee2758d0`, ELF SHA256 `93f5442a0f76592a2614339cc5cdc3abdd82bb7177446667ce6a99728ffe234b`. ESP-IDF5.4.4, ESP32-D0WD-V3 rev3.1, 240MHz; COM3 CP210x; MAC b0:3f:d3:51:8b:ec. Model SHA `38705f5399ada9b87f466725608a053ae2305295a8a3cae7bda01f4928f4a394`.

Đã dùng xác nhận bench không có người kết nối trong phiên. Trước flash lần đầu, verify MD5 khớp firmware đã khôi phục ở nhiệm vụ trước; mỗi lần sau verify đúng image thử vừa lưu. Backup byte-exact vùng0–0x70000 vẫn tại `debug/esp32_ai_test_only/pre_test_touched_flash.bin`, đủ vùng ghi; ngoài vùng không bị chạm. ADC/Synthetic và các cấu hình cũ vẫn còn, Shadow OFF mặc định.

## ESP32 thật / UART / GUI

| Quan sát bản cuối | Kết quả |
|---|---:|
| Capture bench | 90 giây |
| CNN golden | 12/12 EXACT, cold/warm +30 measured stable |
| Last-pass latency được log của12 golden | min 80.640, mean 83.054, max 84.325 ms |
| ADC Hz (buffer cuối / toàn capture) | 250.0 / 250.000020 |
| Mẫu UART hợp lệ | 22304 |
| CRC / missing samples / TX drops | 0 / 0 / 0 |
| ADC errors / missed slots / late | 0 / 0 / 8 |
| UART write / timeout / format errors | 0 / 0 / 0 |
| Process-block / inference queue drops | 0 / 0 |
| Heap internal free / minimum since boot | 152960 / 144216 bytes |
| AI task minimum stack free | 9328 bytes |
| ADC Shadow CNN calls / classified | 0 / 0 |
| Qt GUI đọc COM thật | PASS, 3552 mẫu, CRC=0, missing=0 |

Các số latency trên là12 last-pass được log, không phải600-pass aggregate; latency ADC Shadow chưa đo vì bị gate. Trong capture có tải CNN golden thật, nhưng chưa có tải detector+inference với analog ECG hợp lệ. Không tuyên bố không có jitter: late và phân bố dt đầy đủ trong JSON. Heap minimum tính từ boot; stack là AI worker, không phải mọi task.

Đầu vào thật: 22304/22304 mẫu lead-off; 10838 mẫu chạm0/4095. GUI thật hiển thị RESEARCH_SHADOW ACTIVE, UNKNOWN/INVALID, LEADS_OFF, p=--, official LOCKED. Không ép gọi CNN hay hiển thị N/PVC trên những mẫu này. Buzzer flag luôn OFF; FSM và hàm pattern/GPIO không đổi. Chưa đo điện bên ngoài để khẳng định trạng thái LED/buzzer vật lý dưới prediction hợp lệ.

Golden12 vẫn có3 lỗi so nhãn thật (golden1 N→PVC, golden2 V→N, golden4 N→PVC), output khớp TensorFlow nên parity PASS. Không đổi reference để che lỗi. Kết quả Golden không đi vào panel prediction nghiên cứu ADC hoặc cảnh báo.

Lỗi được phát hiện trong lần thử đầu: 16 TX drops/512 mẫu thiếu, tập trung khi CNN golden tải cao; ADC missed=0. Tăng TX priority riêng Shadow lên5 (cao hơn AI4), không tăng queue/baud hay giảm lấy mẫu. Lượt120giây sau sửa và bản cuối90giây đều CRC/missing/drop=0. Giữ nguyên capture FAIL và image ở `debug/research_shadow/attempt1/`, lượt sau ở `attempt2/`; không sửa log.

## PASS / PENDING

- PASS: code/build, host safety/parser/GUI, replay actual C++/TF, current board golden, UART/ADC dưới golden load, invalid-input ngăn Shadow inference, official live LOCKED.
- PENDING: demo **AD8232 analog hợp lệ → R/window → CNN ESP32 → NORMAL/PVC trong GUI**; đo queue/latency dưới beat thật từ simulator, lead-off trong lúc Invoke, stress dài và đo điện LED/buzzer. Hiện không có nguồn analog vượt quality gate; không tạo dữ liệu thay thế để kết luận PASS.
- Detector record121 vẫn FAIL PPV theo báo cáo2B. Giới hạn accuracy/CNN và end-to-end cũ không thay đổi; chưa đủ cơ sở nghiệm thu chẩn đoán hay mở AI-live.

## Mở ECG Monitor

Mở `tools/ecg_monitor/Start_ECG_Monitor.bat` → chọn **HARDWARE MONITOR — USB Serial** → COM3 → **Connect** → **Start Monitoring**. Khu vực RESEARCH AI nằm đầu panel phải; không chọn VALIDATED AI TEST (vẫn LOCKED). Với trạng thái phần cứng hiện tại, UNKNOWN / INVALID / LEADS_OFF là đúng. Chỉ khi nguồn ECG mô phỏng phù hợp AD8232 vượt các gate và có beat mới, panel mới hiển thị NORMAL/PVC do CNN; không cần mở khóa official AI-live.

Artifact: `debug/research_shadow_results.json`; capture `debug/research_shadow/hardware.bin`, `gui_board_results.json`, ảnh `gui_actual_board.png`; replay `train208.*`, `replay_results.json`; build/test logs trong cùng thư mục. Dừng tại báo cáo, không train hoặc mở rộng nghiệm thu.
