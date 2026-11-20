# Đối chứng V4 FP32–INT8 trực tiếp trên ESP32 — 20/11/2026

**Cả FP32 và INT8 chạy thành công, hai phiên kiểm chứng PASS.** Không có lỗi allocation/Invoke, thiếu lượt hay reset bất thường. Không train, đổi model/threshold/preprocessing/detector, chạy lại replay PVC, thử ADC/V11, commit hoặc push. Board hiện còn **BENCH_INT8 V4**, không tự khôi phục replay.

## Điều kiện và tính công bằng

- Cùng ESP32-D0WD-V3 revision3.1, MAC `b0:3f:d3:51:8b:ec`, COM3; boot cả hai xác nhận CPU160.000.000Hz, ESP-IDF5.4.4. TFLM1.4.2, compiler/source và sdkconfig giống nhau; sdkconfig đã đối chiếu byte-identical.
- Cùng checkpoint V4 849tham số, SHA256 `36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1`. Provenance INT8 từ `int8_conversion.json`, FP32 từ `fp32_export.json`; không chuyển model lại.
- FP32 model SHA256 `699dd84a6490d1cb50ea67c840225a7023b0dbfccd24350d58f8c53463217522`; INT8 `a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e`.
- Cùng22 raw ECG windows256mẫu/250Hz đã chuẩn bị; hash `e4b7dc22d17f7048ba0cf329246d51026db4b7144f7b98a7e03496d330869160`. Payload22.528bytes xuất hiện nguyên vẹn đúng một lần trong mỗi application binary (`embedded_fixture_verification.json`). Cùng z-score double→float32 và threshold0,88; INT8 dùng code≥98. Mỗi bản3 warm-up+30 measured/fixture:66 warm-up và660 measured, đúng thứ tự, không duplicate/missing.
- Cả hai ESP-NN **disabled theo compiler flags thực tế**, không suy từ sdkconfig. FP32 dùng stock float reference ops; INT8 dùng reference Conv/FC single-round adapter đã khóa để giữ arithmetic parity. Kết quả chỉ áp dụng hai backend này, không đại diện mọi tối ưu INT8/ESP-NN.
- Cùng app_main stack8192bytes, arena cấp phát64KiB, policy vTaskDelay/log giống nhau. Không có ADC/detector/replay/GUI task trong benchmark.
- Đo `esp_timer_get_time`: t0 trước normalize; t1 sau normalize; t2 sau quantization/copy; t3 ngay khi Invoke trả về. UART printf và delay nằm ngoài timer. Còn có ảnh hưởng RTOS/interrupt thông thường, không phải phép đo cycle-isolated.
- `total_us=t3−t0`: **window→raw output**, gồm normalization+input quantization/copy+Invoke; không gồm memcpy raw trước vòng đo, đọc/dequantize score, quyết định/format UART. Không gọi đây là R-peak→result hoặc ADC latency.

Build hai mode tuần tự bằng Ninja-j1, xác minh mode và hash rồi flash snapshot đúng backend; không flash cache chỉ dựa trên tên thư mục. Cả hai esptool exit0 và xác minh hash vùng ghi. Capture UART thô tạo file trước một EN reset đo; một ROM boot, một BEGIN/END/backend,726 bản ghi mẫu hoàn chỉnh mỗi phiên. Model hash runtime và CPU clock thực tế khớp. FP32 phiên30,272s; INT8 phiên66,561s (wall time capture có UART/delay, không dùng thay Invoke).

## Thời gian thực đo

660 measured/backend, loại66 warm-up; p95 nội suy tuyến tính; SD mẫu(ddof1), đơn vị **ms**:

| Đại lượng | FP32 | INT8 |
|---|---:|---:|
| Invoke mean |34,472409|83,084818|
| Invoke median |34,474500|83,088000|
| Invoke min |34,441000|83,064000|
| Invoke max |34,492000|83,093000|
| Invoke p95 |34,485000|83,093000|
| Invoke SD |0,010572|0,009081|
| Window→raw output mean |36,294545|86,771182|
| Window→raw output median |36,295500|86,775000|
| Window→raw output min |36,210000|86,698000|
| Window→raw output max |36,366000|86,837000|
| Window→raw output p95 |36,360000|86,836000|
| Window→raw output SD |0,037803|0,033730|
| Normalization mean |1,817182|1,854659|
| Quantization/copy mean |0,004955 (copy1024bytes)|1,831705 (quantize+copy256bytes)|

Tổng thống kê của từng giai đoạn có đủ mean/median/min/max/p95/SD trong `metrics.json`/`paper_table.csv`. First Invoke sau boot (ngoài thống kê warm): FP3235,176ms, INT883,758ms. Lượt−3 các fixture sau không được gọi là cold boot, vì interpreter đã được làm nóng bởi fixture trước.

**INT8 không nhanh hơn:** Invoke latency INT8/FP32 = **2,410183**, tăng **141,02%**. Speedup FP32/INT8 =0,414906 (<1). Window→raw output INT8 tăng139,07%. Đây là số đo, không điều chỉnh backend để đảo kết luận. Requantization/reference integer loops so với FPU là các khả năng giải thích, nhưng chưa profile từng operator nên không kết luận nguyên nhân chi phối. Không suy rộng rằng INT8 luôn chậm hơn FP32.

## Tài nguyên

| Đại lượng (bytes) | FP32 | INT8 | Loại |
|---|---:|---:|---|
| TFLite model |9.584|8.688|file|
| Application .bin |273.936|270.576|build, gồm harness/fixture|
| DRAM tĩnh |14.996|15.532|linker|
| IRAM tĩnh |49.634|49.634|linker|
| Arena used |18.120|6.124|runtime TFLM|
| Arena allocated |65.536|65.536|runtime reservation|
| Minimum free internal heap |230.912|230.376|runtime|
| Main stack reserved |8.192|8.192|config|
| Main stack minimum-free/high-water |6.616|6.592|runtime|
| Peak main stack used ước tính |1.576|1.600|reserved−minimum-free|

Model INT8 nhỏ hơn896bytes (**9,35%**); application nhỏ hơn3.360bytes (**1,23%**). Arena **used** giảm11.996bytes (**66,20%**), nhưng cả hai vẫn giữ reservation64KiB; không tuyên bố heap thực được tiết kiệm66%. INT8 còn dùng DRAM tĩnh nhiều hơn536bytes và minimum free heap thấp hơn536bytes. Stack high-water là cả vòng đời app_main, không riêng stack Invoke. Các số heap/arena/stack không cộng cơ học thành “total RAM”, vì arena được lấy từ heap và stack cũng có reservation riêng.

## Đầu ra classifier

-22/22 fixture cùng quyết định,0 khác; cả hai8 NORMAL/14 PVC tại0,88.660/660 cặp measured run cũng cùng quyết định, nhưng chỉ có22 cửa sổ ECG khác nhau.
- INT8 đúng reference ở toàn bộ726 warm-up+measured outputs, END `int8_exact=1`.
- Mean absolute score difference0,009496239; max0,045672357 (~4,567 điểm phần trăm probability). Max ở fixture4: FP320,834734857 vs INT80,789062500, cả hai NORMAL. Score không exact giữa hai dtype, điều này khác với INT8-host vs INT8-board arithmetic parity.
- `fixture_comparison.csv`: đủ22 score FP32/INT8, code INT8, delta, quyết định và latency theo fixture. `FP32/all_runs.csv`, `INT8/all_runs.csv`: đủ726 lượt mỗi bản. Score lặp ổn định trong mỗi fixture.

Đây là bộ golden Validation được chọn để kiểm chứng số học/near-threshold; **khớp quyết định không có nghĩa22/22 đúng nhãn thật**, không thay cho confusion matrix trên cohort ECG độc lập và không chứng minh accuracy end-to-end.

## Firmware và bằng chứng

- FP32 application SHA256 `d303edbc662ec9a0863ec270583bcb43f8b1ee90b3397c3d9a4cddb99eca4218`.
- INT8 application SHA256 `228ba68bec0b6f713a1d0b53f650bdec15d910fd40454dfe4b6800ab3ef08389` — **đang nằm trên ESP32**. Benchmark đã kết thúc; không chạy ADC/replay.
- `FP32/uart_raw.log` SHA256 `6e8c7c9a7b6f3aaa6ae4601837d49e8d1274272e20ea47ad84e075ade0f8d892`.
- `INT8/uart_raw.log` SHA256 `941d565d472a2e6b61e16b686293935f8b99b4584708e3980227d229906f4f23`.
- Mỗi backend có build log/snapshot/ELF/sdkconfig/hash/compiler command, flash log/status, capture status, validated samples và CSV. Cả hai raw logs được giữ nguyên, không ghép/sửa để PASS.
- `config.json`, `device_info.json`, `benchmark_source.cpp`, `preprocessing_source.h`, `embedded_fixture_verification.json` lưu điều kiện và provenance.
- `restore_REPLAY_PVC/`: app/bootloader/partition/sdkconfig đã xác minh hash của firmware PVC cũ, cùng lệnh khôi phục **chưa thực hiện**. Đây là backup firmware để nạp lại, không phải full flash/NVS dump. Không ghi đè log/kết quả replay PVC/MIT100.
- `metrics.json`, `fixture_comparison.csv`, `paper_table.md`, `paper_table.csv`: dữ liệu thống kê và bảng sử dụng cho bài báo.

## Có thể đưa vào bài báo không?

**Có thể dùng làm benchmark kỹ thuật mô tả trên thiết bị thật**, nếu công bố chính xác board/clock/kernel/toolchain, hai modelhash, dataset fixture, warm-up/n, phương pháp thống kê và các giới hạn trên. Nên báo trung thực INT8 chậm hơn nhưng arena used/model nhỏ hơn trong cấu hình đã đo.

Chỉ một board và một boot/backend, thứ tự FP32→INT8;660 lần đo là lặp phụ thuộc trong22 fixture, không phải660 phiên/thiết bị độc lập. SD ở đây chỉ mô tả timing lặp; không dùng để suy luận ý nghĩa thống kê giữa nhiều board hoặc điều kiện nhiệt độ. Chưa đo năng lượng, throughput liên tục đầy đủ hoặc accuracy end-to-end trong phép thử này. Nếu bài báo cần kết luận tổng quát/thống kê mạnh hơn, cần thiết kế thêm nhiều phiên/đảo thứ tự sau phê duyệt; không tự chạy thêm ở lượt này.

**Dừng tại benchmark này.** Không khôi phục replay tự động, không chuyển V11/ADC, không train/tune hoặc push.
