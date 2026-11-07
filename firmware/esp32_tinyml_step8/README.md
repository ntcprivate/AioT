# Bước 8: ECG INT8 tĩnh trên ESP32-WROOM-32

Project ESP-IDF riêng, target **esp32**, không Arduino, không PSRAM, không ADC,
AD8232, Wi-Fi hoặc giao thức IoT. Đây là nguyên mẫu nghiên cứu, chưa kiểm chứng
lâm sàng. Không thay đổi ngưỡng chính thức **0.52**.

## Trạng thái bàn giao

Code được tạo; FlatBuffer thực tế được kiểm tra và model copy có SHA256 giống
nguồn. Trong phiên Codex không có IDF_PATH/idf.py/toolchain trên PATH, không phát
hiện COM và `.venv` không tìm thấy Python gốc. Vì vậy **chưa build/flash/chạy ESP32**.
Header metadata hiện chứa `#error` có chủ đích và binary mẫu chưa tồn tại: cần
chạy script tạo golden thật. Không có dữ liệu mẫu hay log phần cứng giả.

Component ghim: `espressif/esp-tflite-micro ==1.4.2`, `espressif/esp-nn ==1.3.0`.
TFLM source commit: `6368cd2ddebb72e047509ccbc529afc321e804b9`.
Manifest gốc yêu cầu ESP-IDF >=5.1; project giới hạn <6.1 theo dải tài liệu đã
kiểm tra. Chưa xác nhận phiên bản ESP-IDF trên máy bạn. Không đổi bản IDF đang
có một cách tự động. Giữ `dependencies.lock` khi Component Manager tạo ra.

Nguồn:
- https://components.espressif.com/components/espressif/esp-tflite-micro/versions/1.4.2
- https://components.espressif.com/components/espressif/esp-nn/versions/1.3.0
- https://github.com/espressif/esp-tflite-micro/tree/6368cd2ddebb72e047509ccbc529afc321e804b9

## 1. Tạo dữ liệu kiểm thử bằng môi trường ML

Trong Terminal PowerShell nơi `.venv` Python 3.11 của dự án đang hoạt động:

```powershell
Set-Location 'D:\Code Part Two\AIoT'
.\.venv\Scripts\python.exe python\08_prepare_esp32_test_data.py
```

Script đọc split cũ; chỉ inference Validation; chọn 12 nhịp thật theo seed 42,
bao phủ nhãn/dự đoán và hai mẫu gần ngưỡng nếu có. Toàn bộ Validation có thể
được inference để tìm mẫu kỹ thuật nhưng chỉ 12 nhịp được nhúng. Không dùng để
đánh giá độc lập, chọn lại threshold hay thay đổi mô hình.

Đầu ra: `main/test_data/ecg_test_samples_int8.bin`, `ecg_test_metadata.h`,
`results/esp32_golden_outputs.json`, `results/esp32_operator_compatibility.json`.
Mỗi mẫu là đúng 256 byte signed INT8 liên tiếp, thứ tự C của `(1,256,1)`, không
header nhị phân, không padding; byte thứ `sample_id*256` bắt đầu mẫu đó. Không
có trường nhiều byte nên không có vấn đề endian. Metadata chứa thứ tự mẫu,
dataset index, record, nhãn, golden output và checksum.

Làm tròn: `np.rint` ties-to-even như Bước 7, sau đó clip [-128,127]. Firmware
nhận input đã lượng tử hóa nên không thực hiện lại chuẩn hóa/resample.

Chỉ kiểm tra FlatBuffer/copy model (không tạo golden) có thể chạy với Python
stdlib bằng `python python\08_prepare_esp32_test_data.py --audit-only`.

## 2. Mở ESP-IDF Terminal

Mở folder `firmware/esp32_tinyml_step8` trong VS Code, dùng lệnh của extension
**ESP-IDF: Open ESP-IDF Terminal**. Nếu chưa cài ESP-IDF, cần tự hoàn thành cài
đặt chính thức trước khi build; không dùng Python ML `.venv` thay môi trường IDF.

```powershell
$env:IDF_PATH
idf.py --version
xtensa-esp32-elf-gcc --version
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_tinyml_step8'
idf.py set-target esp32
idf.py build
idf.py size
idf.py size-components
```

Component Manager tự giải dependency đã khai báo trong `main/idf_component.yml`;
không cần thêm dependency không ghim bằng `add-dependency`. Build đầu có thể cần
Internet. Giữ `dependencies.lock`, `sdkconfig` và log build để truy vết.

Để lưu bằng chứng build/kích thước:

```powershell
idf.py build 2>&1 | Tee-Object -FilePath '..\..\results\esp32_build.log'
# Kiểm tra LASTEXITCODE ngay sau lệnh build; giá trị 0 mới là build thành công.
$LASTEXITCODE
idf.py size 2>&1 | Tee-Object -FilePath '..\..\results\esp32_size.log'
idf.py size-components 2>&1 | Tee-Object -FilePath '..\..\results\esp32_size_components.log'
Get-Item '.\build\esp32_tinyml_step8.bin' | Select-Object Name,Length
```

ESP-IDF kiểm tra app partition khi build. Nếu vượt partition, báo lỗi và xem
báo cáo size; không coi kích thước model 8.560 byte là kích thước firmware.

## 3. Tensor arena và kiểm tra khởi tạo

Arena mặc định 64 KiB, lấy từ internal 8-bit-capable RAM, căn chỉnh 16 byte.
Không tự tăng arena hay dùng PSRAM. Nếu `AllocateTensors` thất bại, kiểm tra
log lỗi kernel/quantization trước, sau đó thử có kiểm soát qua:

```powershell
idf.py menuconfig
```

Mục **ECG Step 8** cho phép 16–128 KiB và 30–100 lượt đo mỗi mẫu. Ghi lại mỗi
lần thử và chỉ chọn dung lượng đã đo đủ dùng. Allocation thành công không đảm
bảo Invoke thành công. Model được truy cập từ binary flash-mapped, không copy
toàn bộ vào arena. Binary được nhúng qua `EMBED_FILES` với đúng symbol đường dẫn.

Firmware đăng ký 7 operator; kiểm tra checksum model/mẫu, schema, tensor shape,
dtype, scale và zero point trước inference. Xem `esp32_operator_compatibility.json`:
có API/kernel tương ứng không chứng minh mọi operator version đều chạy được.

`ECG_ARENA` phân biệt allocated/used; `ECG_HEAP` là internal heap free/minimum/
largest block trước và sau init. RAM tĩnh/BSS xem `idf.py size`, không cộng nhầm
arena đã lấy từ heap thành một allocation thứ hai. ESP-NN build option được log,
không đồng nghĩa mọi operator đi qua kernel tối ưu.

## 4. Cắm USB, xác nhận COM và flash

Chỉ cắm ESP32 DevKit V1; chưa nối AD8232 hoặc điện cực lên người.

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```

Đối chiếu Device Manager và rút/cắm board để xác định đúng cổng. Các lệnh sau
dùng **COM5 chỉ làm ví dụ**; thay bằng COM thật đã xác nhận. Không flash khi
chưa xác định đúng board/cổng.

```powershell
idf.py -p COM5 flash
idf.py -p COM5 monitor
```

Không cần nạp lại Python hay sửa `.venv`. Nếu không vào bootloader, dùng nút
BOOT/EN theo hướng dẫn board, không đổi target sang S3/C3/P4.

## 5. Log thật và đối chiếu Python

Trong monitor, nhấn **Ctrl+T rồi Ctrl+L** để bật ghi file; sau đó nhấn
**Ctrl+T rồi Ctrl+R** hoặc EN để bắt đúng một boot hoàn chỉnh. Đợi `ECG_DONE`.
Nhấn Ctrl+T rồi Ctrl+L để ngừng ghi và Ctrl+] để thoát. Đường dẫn log được
monitor thông báo. Chỉ chọn file có đúng một `ECG_BOOT`, không ghép nhiều lần chạy.

Nguồn phím monitor: https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-guides/tools/idf-monitor.html

Copy log thật về `results/esp32_serial.log`, rồi chạy từ workspace:

```powershell
Set-Location 'D:\Code Part Two\AIoT'
python python\08_verify_esp32_output.py --log results\esp32_serial.log
```

Verifier chỉ dùng stdlib, đối chiếu checksum, ID/record/nhãn, input bytes, output
INT8, score, lớp dự đoán và 30–100 lần đo/mẫu. Tạo
`results/esp32_inference_comparison.json` và cập nhật runtime trong báo cáo Bước 8.
EXACT_MATCH chỉ khi mọi byte output khớp; sai khác LSB được báo NEEDS_REVIEW;
bất đồng lớp hoặc thiếu dữ liệu là FAILED. Không sửa threshold để ép khớp.

## 6. Đọc kết quả

- `ECG_RESULT`: kết quả từng mẫu, golden Python, chênh LSB và trạng thái.
- `ECG_TIME`/`ECG_LATENCY`: chỉ thời gian Invoke, sau 3 warm-up; log/copy input/
  delay watchdog nằm ngoài vùng đo. Chưa gồm ADC, lọc hay phát hiện nhịp.
- `ECG_DONE`: kết thúc toàn bộ kiểm thử; lỗi bất kỳ không được coi là PASS.
- `results/esp32_step8_report.json` và summary ghi trạng thái bàn giao ban đầu;
  verifier bổ sung runtime khi có log thật. Thông tin build/flash chỉ được cập
  nhật sau khi có log lệnh và báo cáo size thật, không từ việc code tồn tại.

Hiện tại arena thực tế dùng, heap runtime, latency, firmware/flash/BSS đều
**NOT_MEASURED**. Chỉ kích thước model và checksum đã đo trên máy tính.
Không thể kết luận chất lượng trên bệnh nhân mới hoặc ứng dụng y tế từ vài
mẫu kiểm thử kỹ thuật này. Chỉ dừng ở Bước 8, chưa triển khai Bước 9.
