# Chuẩn bị ADC V4 — source/build đã có, analog chưa được đo

Không flash/reset/mở COM3 hoặc đổi firmware/GUI ở lượt này. Theo benchmark cuối, firmware trên board là BENCH_INT8; muốn thu ADC phải chọn đúng mode ADC sau phê duyệt. Không dùng replay hoặc benchmark như bằng chứng đường analog.

## Cấu hình đối chiếu source hiện hành

| Mục | Giá trị /source |
|---|---|
| Model |V4 INT88.688bytes, SHA256 `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`|
| Threshold |0,88, code≥98; metadata/model/publish V4 nhất quán|
| Sampling |GPTimer1MHz,alarm4000µs; ISR chỉ notify; ADC task core1 priority10|
| ADC |GPIO34,ADC1_CHANNEL_6,oneshot12bit,attenuation12dB; đọc ADC trong task|
| LO+ /LO− |GPIO27 /GPIO26, input, không pull-up/down; bất kỳ HIGH→lead-off|
| Window |256mẫu `[R−128,R+128)`,ring512,pendingFIFO4; index/timestamp và integrity checks|
| Detector |EMA baseline0,025,envelope0,01; max(30counts,2,5×envelope);500mẫu warm-up;confirmation50/refractory75; không V4-A|
| Preprocessing |raw counts window,mean/std population double→float32,std≤1e−8 reject,round-to-even; input scale0,06217966973781586,zp−8|
| Output |scale1/256,zp−128;score=(code+128)/256;V4 threshold giữ nguyên|

Nguồn: `main/main.cpp`, `lead_off.h`, `signal.cpp/.h`, `preprocessing.h`, `model.cpp`, `pipeline.cpp`, `research_shadow.h`, `telemetry.cpp`, model metadata và CMake của `firmware/esp32_ecg_v4_experiment/`. Baseline filter chỉ phục vụ detection; window morphology vẫn raw. ADC timestamp lấy ngay trước call đọc, kèm read duration, không phải giờ alarm dự kiến. Counter late/missed và sample interval được tính theo timer/đọc thật; không suy luận tốc độ từ UART arrival.

## Gate và điều kiện có NORMAL/PVC

Model_init+golden phải thành công. Không lead-off/ADC error/missed slot, snapshot/hash/queue/generation nhất quán. Block/window không rail≤16 hoặc≥4079, ptp≥20counts, mean-difference không vượt25%ptp; timestamp2–6ms. Quality recovery có≥512 mẫu tốt và2 block tốt. Có R-peak, đủ window256, normalize hữu hạn và **không input quantization clipping**. Worker kiểm tra model/system/output fault, generation và sample freshness<20ms trước/sau Invoke; window age≤1,5s. Prediction hết hiệu lực sau1,5s; invalid/stale/gap phải UNKNOWN, không dùng nhãn cũ. Power50 ratio/baseline delta chỉ là metric chẩn đoán trong source, không tự coi đã có gate reject đầy đủ theo chúng.

Khi hợp lệ, NORMAL nếu code<98, PVC nếu≥98; không phải mọi tín hiệu analog đều là ECG hợp lệ chỉ vì qua các heuristic. Nhãn simulator không đi vào detector/CNN. LED/buzzer bench demo mặc định tắt, không dùng như cảnh báo y tế.

## Thiết bị tối thiểu

- ESP32 DevKit V1/WROOM-32 đúng board đã đo,USB cable và PC.
- AD8232 module, tài liệu/schematic revision thực tế, dây/adapter có đánh dấu đúng chân; không suy màu dây là RA/LA/RL.
- **Ưu tiên ECG patient simulator** có Normal/PVC, lead selection, mức mV/RR xác định và marker/log tham chiếu. Cần manual thông số output/common-mode/lead-off tương thích AFE.
- DMM để đo3V3/offset/LO; oscilloscope và probe phù hợp để xem OUT/gain/clipping. Nếu thiết bị nối đất bảo vệ thì kiểm điểm đặt ground/probe trước nối; không clip ground vào differential/RLD tùy tiện.
- Nguồn3,3V ổn định và đủ dòng cho ESP32/module; adapter/điện trở bảo vệ theo thiết kế được xác minh, không thêm RC/lọc rồi coi preprocessing không đổi.

Chưa có bằng chứng model/revision/filter schematic của module thực tế hoặc voltage/gain đã đo. Đó là mục người dùng cần cung cấp/kiểm tra tay, không phải lỗi Python.

## Sơ đồ bench, không nối người

```text
ECG simulator (đầu ra mV, có annotation/marker riêng)
  RA -------------------- AD8232 −IN (thường chân/cáp RA)
  LL [muốn lead II] ------ AD8232 +IN (module thường gắn nhãn LA)
  RL/reference ---------- AD8232 RLD/RL theo manual simulator/module
                          (không mặc định RL là GND)

ESP32 3V3 --------------- AD8232 3V3
ESP32 GND --------------- AD8232 GND
AD8232 OUT -------------- ESP32 GPIO34 /ADC1_CH6
AD8232 LO+ -------------- ESP32 GPIO27
AD8232 LO− -------------- ESP32 GPIO26
ESP32 USB --------------- PC/UART115200
Reference marker/log ---- bộ chấm, không điều khiển detector hoặc classifier
```

Sơ đồ cực điện ECG chỉ áp dụng **sau khi xác nhận pin mapping thực tế**. LeadII là LL−RA; nếu nối kiểu LA−RA thì đó là leadI, không được ghi là cùng leadII/MLII của dataset. Chọn một cấu hình rõ ràng, không nối LA và LL đồng thời vào cùng đầu. Nếu simulator chỉ hỗ trợ cấu hình khác, ghi đúng lead và giới hạn morphology; không tự đảo cực để tăng score. Các nhãn RA/LA/RL trên module là đầu nối, cần đối chiếu schematic với +IN/−IN/RLD trước dùng.

## Nguồn và điện áp — kiểm khi chưa nối GPIO

AD8232 chip có supply2,0–3,5V; bench dùng3,3V, không cấp5V vào module không rõ regulator. LOD active-HIGH theo mode; AC mode có thể chỉ LOD+ báo mất lead, nhưng OR hai chân vẫn giữ fail-safe. RLD là output driven-reference, không nối tắt tùy tiện xuống GND. Xác minh SDN/enable của module theo schematic; firmware không điều khiển SDN. [Datasheet AD8232](https://www.analog.com/media/en/technical-documentation/data-sheets/ad8232.pdf), mục pin/supply/lead-off.

OUT vào GPIO34 cần nằm trong mức điện hợp lệ của ESP32; không âm, không5V, không vượt rail3V3. **12dB không chứng minh ADC đo tuyến tính0..3,3V.** Chọn offset và biên độ bằng DMM/scope để có headroom, không sát raw0/4095; dừng nếu rail/clipping/không rõ điện áp. Không dùng raw4095×3,3V như phép đo điện áp đã calibration. Driver oneshot đang đọc raw, source chưa gọi adc_cali để xuất mV; range chính xác phụ thuộc ADC/chip/attenuation. Xem [ESP-IDF5.4.4 ADC oneshot](https://docs.espressif.com/projects/esp-idf/en/v5.4.4/esp32/api-reference/peripherals/adc_oneshot.html) và [ADC calibration](https://docs.espressif.com/projects/esp-idf/en/v5.4.4/esp32/api-reference/peripherals/adc_calibration.html).

ECG simulator mức điện cực phải qua AD8232; không đưa trực tiếp tín hiệu mV nhỏ vào GPIO34 rồi coi tương đương AFE. Nếu dùng DAC/AWG để cấp trực tiếp GPIO thì đó là bài test ADC khác, phải có DC offset, mức an toàn và protocol riêng, không giả thành phép AD8232 hoàn chỉnh. Xác minh simulator thật sự tạo đường điện phù hợp để lead-off hoạt động; không kéo LO xuống LOW để qua gate.

USB/PC và module hiện có chưa được chứng nhận cách ly người. Không có điện cực hoặc đường dẫn nối cơ thể trong mọi bước bench này. Không yêu cầu người dùng tự chứng minh safety bằng cách thử trên người.

## Trình tự tay trước khi xin nạp ADC

1.Tắt nguồn, xác nhận chân/module/simulator và chuyển đạo. Không người kết nối.
2.Chưa nối OUT vàoGPIO34: cấp nguồn đúng, đo3V3/GND, kiểm OUT offset/biên độ/cực tính/rail trên scope. Ghi serial/model thiết bị, gain/filter settings, ảnh/sơ đồ và file scope nếu có.
3.Ngắt nguồn trước đấu OUT/LO vào ESP32. Kiểm continuity và không short. Cắm đúngUSB, chọn cổng bằng hardware ID khi được phép (không mở COM trong kiểm kê).
4.Khóa chương trình Normal/PVC, nhãn/marker/timebase, amplitude/RR và thời gian đo trước chạy. Không chọn lại sau nhìn score.
5.Sau phê duyệt riêng mới chọn binary ADC đúng hash/config (không flash cache BENCH_INT8). Nạp/thu boot+golden+raw/CRC+prediction+drop/reason/memory/latency bằng logger liên tục phù hợp; lưu vào thư mục mới.
6.Thử lead-off/recovery và mất/flat/clipping an toàn; sau đó mới lượt N/V có nhãn đồng bộ. Khi không có annotation/trigger đáng tin, chỉ báo chức năng, không tính accuracy. Giữ mọi missed V vàoFN, N mất là abstention.

## BLOCKED/readiness cần biết

- Source/historical build ADC: **PASS**; analog hardware/accuracy: **NOT RUN**. Không build lại ở lượt này.
- GUI hiện có threshold validator0,52, không tương thích đầy đủ V4: `tools/ecg_monitor/ecg_monitor/ai.py:26`. Phải dùng raw output/code và evaluator V4, hoặc sửa GUI ở phạm vi được duyệt sau này. Không lấy UNKNOWN do GUI làm CNN FN khi chưa phân biệt.
- Capture replay chờ `V4_REPLAY_END`; ADC không có marker đó. Cần protocol capture duration/start-stop/annotation riêng trước đo.
- Chưa có simulator/manual, mapping lead/gain/filter/voltage thực đo hoặc reference sync trong artifact đã kiểm. Không gọi hệ thống ADC “ready for accuracy validation” cho tới khi hoàn thành chúng. Chi tiết thứ tự/tiêu chí trong `remaining_experiments.md`.
