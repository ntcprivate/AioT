# ECG1 framing — body version2 và tài liệu version1

Bản mới phát JSON `v=2`, giữ CRC32/framing ECG1 bên dưới; thêm LF trước frame.
`source` bắt buộc HARDWARE/SYNTHETIC_TEST ở mọi packet. GUI2.0 đọc cả v1 cũ;
GUI cũ từ chối v2 để tránh nhận nhầm nguồn synthetic là hardware.
Sample synthetic thêm `pattern=saw17-v1`, giá trị `512+((uint64(index)*17)%3072)`.
Status thêm `baud`, `uart_baud_actual`, `sample_attempts`, `tx_samples`, `tx_bytes`,
`acq_hz`, `tx_hz`, `dt_mean_us`, `dt_min_us`, `dt_max_us`, `clock_last_us`,
`format_errors`, `uart_write_errors`, `uart_tx_timeouts`. Hz/mean chưa đo được là null.
Xem [định nghĩa clock/counter, UART và kiểm thử mới](telemetry_reliability_review.md).
Phần bên dưới mô tả body v1 nền; field/layout cũ tiếp tục được giữ trong v2.

UART USB115200/8N1, ASCII một frame trên một dòng:

```text
ECG1 <CRC32 8 ký tự HEX> <JSON compact ASCII>\n
```

CRC32 IEEE reflected polynomial0xedb88320, init/final xor0xffffffff, tương ứng
zlib.crc32. Chỉ tính trên bytes JSON, không tính prefix, CRC hay CR/LF. Đây là
kiểm tra lỗi truyền, không phải xác thực mật mã. Python parser giới hạn4096byte
mỗi dòng, từ chối CRC sai/cắt gói/schema sai/sequence lùi hoặc lặp. Không sửa
dòng hỏng. Debug/boot logs không có prefix được bỏ qua; nếu writer ngoài khóa
làm hỏng một frame, CRC phải loại nó. Console ứng dụng dùng chung khóa ghi.

Mỗi JSON có v=1, type, boot (nonce hex mỗi boot), seq uint32 tăng trên **cả hai
loại gói**. Wrap2^32 hỗ trợ; boot mới/reconnect bắt đầu timeline mới, xóa kết quả
AI cũ. Không gửi lệnh từ GUI đến firmware, không có remote unlock/flash/reset.

## samples

Các trường: fs=250,n=32,first (chỉ số mẫu đã đọc),t0 (timestamp us mẫu đầu),
data (HEX448 ký tự),dropped (số batch bị bỏ vì queue đầy). last batch đang chưa
đủ32 mẫu được giữ trong producer; không tự tạo mẫu bù khi dừng/mất nguồn.

data gồm32 records7byte little endian:

| Offset | Kiểu | Ý nghĩa |
|---|---|---|
|0..3|uint32|Timestamp thực trừ t0, microsecond; mẫu đầu bằng0 |
|4..5|uint16|ADC12bit0..4095;65535 là ADC error sentinel |
|6|uint8|bit0 LO+ HIGH, bit1 LO- HIGH, bit2 ADC error, bit3 missed/timer notification gap |

Timestamp được chụp trước lời gọi adc_oneshot_read, không phải lịch alarm dự kiến.
GPIO được đọc tuần tự sau ADC; hai chân không phải phép chụp điện đồng thời.
first tăng theo số mẫu **thực sự đọc**, không bù slot timer mất. Mất slot thể hiện
ở flag/timestamp và missed_est; mất batch UART thể hiện qua first/seq/dropped.

## status (khoảng2Hz)

t_us,firmware,source=HARDWARE,state,reason,model,golden,classification,p_pvc,
threshold,r_validated,bpm,rr_ms,r_peaks,led,buzzer,self_test. Bản hiện tại luôn
classification=UNKNOWN,p_pvc=null,r_validated=false,bpm/rr_ms=null,r_peaks=[];
model=LOCKED sau golden PASS, DISABLED khi chưa sẵn sàng. GUI không biến kết quả
golden thành dự đoán live. LED/buzzer là mức output được firmware điều khiển,
không phải phép đo điện bên ngoài.

quality_known,quality_valid,quality_t_us,clip_count,ptp,diff_percent,
power50_ratio,baseline_delta là metrics của block256 gần nhất. Ước lượng50Hz là
DFT tại50Hz so với tổng năng lượng, không phải chứng minh nguồn nhiễu điện lưới.
Không dùng metric mới để nới ngưỡng cũ. quality_valid chỉ là vượt qua bench
heuristics, không chứng nhận ECG thật hợp lệ.

adc_errors,missed_est,late,snapshot_errors là tổng tích lũy từ summary sampler;
tx_dropped và write_errors phản ánh transport. missed_est là ước lượng theo
timestamp/notification, không phải đo độc lập bằng logic analyzer.

## Tài nguyên và kiểm tra

Queue TX6 batch, tối đa khoảng768ms dữ liệu; sampling ghi batch tĩnh và
xQueueSend(...,0), không chờ UART. TX task priority2/core0, ADC priority10/core1.
Khi queue đầy bỏ nguyên batch và đếm; không ngưng sampling, không che lỗi mất gói.
Counter32bit có thể wrap sau vận hành dài. Giá trị lý thuyết/host khoảng5.8KB/s
trên11.52KB/s capacity. Xem tools/ecg_monitor/reports/transport_load.json.
Chưa đo băng thông/CPU/stack/missed trên board revision này.

CONFIG_ECG_TELEMETRY=y mặc định: tắt operator/arithmetic dump dài và ADC_BUFFER
Serial thường kỳ, vẫn tính/kiểm tra summary và thống kê. Golden12 mẫu vẫn chạy.
Chế độ diagnostic: tắt telemetry, bật ECG_OPERATOR_TRACE khi cần; protocol2
comparator cũ giữ strict. Khi đó GUI không thể dựng sóng từ first10 log.

Phiên CSV giữ source/boot/sample index/timestamps và timestamp snapshot status.
Pause Display không ảnh hưởng nhận/ghi. Khi mất kết nối/timeout, AI/BPM trở về
UNKNOWN; dữ liệu lịch sử không được trình bày như phép đo hiện thời.
