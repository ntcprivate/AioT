# AD8232 electronic ADC test

## LED/buzzer startup self-test

Module `main/alert.cpp` điều khiển LED HIGH-active ở GPIO23 (qua 220Ω,
cathode xuống GND) và buzzer chủ động HIGH-active GPIO25 (âm xuống GND),
theo giả định buzzer 3,3 V và dòng phù hợp GPIO. Cả hai được đặt LOW khi init.
Không dùng PWM cho buzzer chủ động.

Một task `alert_control` ưu tiên 2 chạy một lần: LED sáng 2 giây/buzzer tắt,
sau đó 6 chu kỳ cùng bật 150 ms/cùng tắt 350 ms; cuối cùng cả hai tắt.
Task dùng `vTaskDelay`, không busy-wait hoặc chặn task sampling ưu tiên 10.
Log `ALERT_TEST` khóa stdout cùng cơ chế logger để không xé dòng ADC_BUFFER.
Thời gian GPIO là thời gian FreeRTOS theo tick/scheduling, cần kiểm tra thực tế.

API task-context trong `alert.h` trả `esp_err_t` ngay, không dùng từ ISR:

- `alert_set_normal()`: LED sáng, buzzer tắt.
- `alert_set_pvc()`: cùng nhấp nháy/bíp 150 ms ON / 350 ms OFF cho đến khi đổi trạng thái.
- `alert_set_invalid()`: cả hai tắt.

Chỉ có một task, queue dài 1 dùng latest-state overwrite. Lệnh trong self-test
được giữ đến khi self-test hoàn tất; mặc định không có lệnh nên kết thúc tắt.
Lệnh PVC lặp lại không khởi động lại thời gian pha. Các API này chưa được gọi
từ dữ liệu ADC, không có dự đoán N/PVC hay tích hợp AI. Lỗi GPIO runtime sẽ cố
tắt cả hai, log lỗi và khóa module đến reboot; sampling tiếp tục độc lập.

Không thay đổi thuật toán ADC, ISR, buffer, checksum hoặc format ADC_BUFFER.
Chưa kiểm thử phần cứng bản LED/buzzer; cần xem lại late/missed_est khi chạy.
Build thử trong phiên Codex bị chặn ở activation ESP-IDF do thiếu
`C:\Espressif\espidf.constraints.v5.4.txt`; không cài hoặc sửa môi trường.
Sau khi môi trường ESP-IDF v5.4.4 của bạn hoạt động, mở ESP-IDF Terminal:

```powershell
Set-Location 'D:\Code Part Two\AIoT\firmware\esp32_ad8232_adc_test'
idf.py --version
idf.py build
```

Không tự flash. Không thể bảo đảm không mất mẫu chỉ từ kiểm tra code;
xác nhận trên thiết bị bằng integrity/late/missed_est/actual_hz.

Project độc lập cho ESP32 DevKit V1 / ESP32-WROOM-32, ESP-IDF **v5.4.4**.
Không Arduino hoặc TinyML. Chưa build/flash trong phiên tạo code.

Chỉ kiểm tra tín hiệu điện tử trên bàn thử, **không gắn điện cực vào người**.
Giá trị ADC không được xem là ECG hợp lệ hoặc dữ liệu chẩn đoán.

Đấu dây khi đã ngắt nguồn:

| AD8232 | ESP32 |
| --- | --- |
| 3.3V | 3V3 |
| GND | GND |
| OUTPUT | GPIO34 (ADC1 channel 6) |
| LO+ | GPIO26 |
| LO- | GPIO27 |

Không đưa tín hiệu 5 V vào chân ESP32. Các input LO không bật pull-up/down;
khi chưa đấu dây, mức logic có thể không ổn định.

## Lấy mẫu 250 Hz

ADC oneshot dùng `ADC_UNIT_1` + `ADC_CHANNEL_6`, 12 bit, attenuation 12 dB.
GPTimer chạy ở 1 MHz, alarm tự reload sau 4000 tick (4000 µs).
Callback ISR chỉ thông báo task qua `vTaskNotifyGiveFromISR`, không đọc ADC,
ghi timestamp hoặc in Serial. Task lấy mẫu ưu tiên 10 ghi timestamp bằng
`esp_timer_get_time()` ngay trước ADC read và đọc hai chân LO.

Buffer giữ 256 cấu trúc gồm raw ADC, timestamp µs, LO+ và LO−. Khi đủ buffer,
chỉ summary được gửi không chờ vào queue 4 phần tử. Task logger ưu tiên 3 in
summary và 10 raw đầu, không in từng mẫu. Bình thường một buffer đầy sau
khoảng 1,024 giây. Queue đầy thì bỏ summary, không chặn lấy mẫu; ID nhảy và
`summary_dropped_total` ở log sau cho biết có summary bị mất.

### Các trường log

- `id`, `samples=256`, `adc_ok`, `adc_errors`, `last_adc_error`.
- `min`, `max`, `mean`: chỉ tính ADC thành công; raw lỗi là -1, không dùng lại
  giá trị cũ. Nếu không có mẫu hợp lệ thì min/max=-1 và mean=0 là placeholder.
- `dt_mean_us`, `dt_min_us`, `dt_max_us`, `interval_count`: thống kê đúng 255
  khoảng cách timestamp bên trong cùng buffer. `boundary_dt_us` báo riêng
  khoảng cách từ mẫu cuối buffer trước đến mẫu đầu buffer này (buffer đầu =0).
- `actual_hz = 255 * 1e6 / (timestamp cuối - timestamp đầu)` trong buffer.
- `lo_any`: số mẫu có LO+ hoặc LO− bật, mỗi mẫu chỉ đếm một lần.
  Bất kỳ LO bật đều đánh dấu `INVALID_LEADS`. `LEADS_NOT_ASSERTED` khi cả hai
  không bật cũng **không có nghĩa ECG hợp lệ**; không đưa buffer vào AI.
- `pending_missed`: notification tích lũy ngoài lần mới nhất. Chỉ đọc một lần
  tại thời điểm hiện tại, không đọc bù quá khứ hoặc tạo burst giả 250 Hz.
- `missed_est`: ước lượng slot 4 ms mất, dùng cả notification và slot đã trôi
  theo timestamp. Hai nguồn không cộng vào nhau để tránh đếm trùng.
- `late`: số lần đọc có trễ pha >500 µs hoặc bỏ slot. 500 µs là dung sai chẩn
  đoán trong code, không phải tiêu chuẩn y tế. `max_lateness_us` phản ánh trễ
  pha slot hiện tại; nguyên chu kỳ mất được thống kê riêng ở `missed_est`.
  Không cộng late và missed thành tổng mẫu lỗi.
- `continuity=GAPPED_OR_ADC_ERROR` nếu có slot mất hoặc ADC lỗi: buffer là 256
  lần đọc theo thứ tự, khi đó không phải 256 mẫu đều 4 ms liên tục.

Đánh giá tần số thực tế bằng dt trung bình gần 4000 µs, `actual_hz` gần 250,
min/max dt để thấy jitter, cùng late/missed/ADC errors. Không chỉ dựa vào cấu
hình timer để khẳng định đạt 250 Hz. Timestamp là thời điểm gọi ADC trong
phần mềm, không phải timestamp chính xác của mạch sample-and-hold.

Mốc start GPTimer được kẹp bằng timestamp trước/sau `gptimer_start`; log ghi
độ rộng khoảng không chắc chắn. ISR có thể coalesce khi bị chặn, clock có sai
số: `missed_est` là ước lượng, không phải bộ đếm mất mẫu hardware tuyệt đối.
Đây là ADC oneshot do task đánh thức, không phải ADC hardware-triggered/DMA.

## Rà soát tính nhất quán và Serial

Buffer 256 mẫu chỉ do task sampling ghi/đọc; task logger không truy cập buffer.
Queue FreeRTOS sao chép toàn bộ `Summary` theo giá trị, không truyền con trỏ
về buffer đang được tái sử dụng. Sau khi đủ 256 mẫu, sampler giữ buffer bất biến
để tính lại sum/min/max/count/LO và đối chiếu với thống kê tích lũy, 10 raw đầu
và tính tăng của timestamp. Sau đó đóng dấu checksum snapshot rồi enqueue.
Logger nhận bản copy riêng và kiểm tra checksum, miền ADC, first10 trong min/max,
sum/count, timestamp và số thứ tự. Lỗi in `integrity=FAILED` cùng `ADC_WARNING`.

`ADC_FIRST10` rời đã được thay bằng trường `first10=` ngay trong dòng
`ADC_BUFFER`: thống kê và raw đầu không thể bị ghép nhầm buffer từ hai dòng.
Logger format một record bằng snprintf có kiểm tra độ dài, giữ `flockfile(stdout)`
trong một lần fwrite và flush. Chỉ logger xuất dữ liệu định kỳ, sampler không
in mỗi lần đọc. Khóa stdio không bảo vệ writer bypass stdout, panic/ROM log,
cáp USB/UART, driver hoặc terminal phía máy tính; không bảo đảm chống mọi mất byte.

- `snapshot_hash`: FNV-1a 32-bit trên byte snapshot (padding được khởi tạo zero),
  kiểm tra bản copy qua queue; không phải checksum có thể tính từ text min/max.
- `line_fnv1a`: FNV-1a 32-bit trên byte ASCII từ chữ `A` của `ADC_BUFFER` đến
  hết giá trị `first10`, **không gồm** dấu cách trước `line_fnv1a`, suffix hoặc
  CR/LF. Checksum này cho phép kiểm tra mất/thay byte trong log đã nhận. Bỏ
  timestamp/prefix do monitor chèn trước `ADC_BUFFER` khi kiểm tra. Checksum chỉ
  phát hiện lỗi, không sửa lỗi và không bảo đảm không có collision.
- `id_gap`, `summary_dropped_total`: phát hiện thiếu record. `uart_write_errors`
  đếm lỗi fwrite/flush được firmware phát hiện; bằng 0 không chứng minh PC nhận đủ.
- `first_us`, `last_us`, `read_max_us`: timestamp thực tế ngay trước ADC call,
  timestamp cuối buffer và thời gian ADC call dài nhất. Không dùng timestamp
  alarm lý tưởng để thay cho thời gian đọc. Chưa xác định chính xác thời điểm
  sample-and-hold; độ trễ driver/chuyển đổi nằm trong khoảng gọi đọc này.

Sửa công thức slot: dùng `max(tổng notification từ start, slot thời gian đã trôi)`
thay cho `max(slot ước lượng trước + notification mới, slot thời gian đã trôi)`.
Công thức cũ có thể mang slot bù do ISR coalesce sang các lần sau và đếm dư.
`missed_est` vẫn là ước lượng nhạy với sai số mốc start/clock; `pending_missed`
là bằng chứng riêng về notification bị dồn, không cộng hai số này lại.

Mâu thuẫn max=393 nhưng first10 chứa 3770 không thể hợp lệ trong cùng snapshot.
Rà soát nguồn không thấy race buffer/queue giải thích trực tiếp mâu thuẫn đó.
Việc in first10 cũ bằng nhiều printf là điểm yếu đã sửa, chưa đủ bằng chứng
kết luận nguyên nhân mất ký tự trên phần cứng. Cần log thô mới có checksum,
xác nhận đúng firmware được nạp, baud monitor khớp cấu hình console và kết nối
USB/UART để phân biệt lỗi tính dữ liệu với lỗi truyền/hiển thị.

Kết quả 250 Hz/không ADC error do người dùng báo là bằng chứng của bản chạy
trước, không phải phép đo bản sửa này. Chưa tự build/flash hoặc xác nhận sửa
xong lỗi Serial trên thiết bị. Khi lo_any=256, INVALID_LEADS vẫn là trạng thái
đúng và không chứng minh dữ liệu ECG hợp lệ.

Các API setup được kiểm tra, thu hồi tài nguyên khi lỗi trước start. Start
thất bại sẽ disable timer và dừng task lấy mẫu. ADC lỗi runtime được đếm và
báo mã trong summary, không in lỗi từng mẫu. GPIO read trả mức logic, không
phải `esp_err_t`. Chưa tích hợp TinyML, chuẩn hóa, hiệu chuẩn điện áp hay N/PVC.

Nếu muốn kiểm thử sau này, mở ESP-IDF Terminal v5.4.4 trong folder này,
chọn target `esp32`. Code có kiểm tra phiên bản IDF lúc biên dịch.
Không có thao tác build hoặc flash tự động.

API tham chiếu đúng phiên bản:
https://github.com/espressif/esp-idf/blob/v5.4.4/components/esp_adc/include/esp_adc/adc_oneshot.h

https://github.com/espressif/esp-idf/blob/v5.4.4/components/esp_driver_gptimer/include/driver/gptimer.h
