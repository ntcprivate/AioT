# Phân tích gián đoạn ADC V4 — chỉ dữ liệu đã ghi

## Kết luận

Tìm được bằng chứng 34 peak/31 nhịp được phân loại trong capture ECG Monitor, không phải trong phiên ADC 17:37. Đây là bộ đếm tích lũy của boot `bc71c753`, trước firmware LED/buzzer mới. Sau đó có boot `e5ab600c` và `a2f79094`; không gộp bộ đếm giữa boot. Không mở COM3, reset, flash, chạy CNN hoặc thay source firmware trong phân tích này.

Đầu vào lỗi **gián đoạn**: có hai khoảng ngắn vượt gate, xen giữa nhiều LEADS_OFF/ADC_SATURATION. Không có bằng chứng CNN tự dừng sau một số nhịp nhất định. Khi đầu vào đổi hoặc bão hòa, gate hủy kết quả và reset trạng thái phục hồi/detector đúng thiết kế.

## Bằng chứng inference thực tế

Các timestamp dưới đây là microsecond từ lúc boot, không phải giờ UTC. Tên capture mang UTC; không suy ra giờ treo tường chính xác cho từng beat chỉ từ tên file.

| Capture trong tools/ecg_monitor/captures | Result timestamp đầu–cuối (µs) | Công bố NORMAL/PVC | Bị từ chối |
|---|---|---:|---:|
| 20261120T110102Z_f0fe45e2.bin | 3692014652–3699456231 | 3 / 21 | 0 |
| 20261120T110601Z_7d859e74.bin | 3867118520–3869305061 | 0 / 7 | 1 |

31 kết quả thực được công bố; 32 V4_BEAT events. Event cuối ở `result_us=3869357359`, `r_us=3868281763` bị `SIGNAL_CHANGED_BEFORE_INFERENCE`, `invoke_us=0`, predicted=-1: không được tính là một inference. Dữ liệu mỗi beat, score, timestamp, latency và kiểm tra cửa sổ ở per_beat_audit.csv; không suy đoán nhãn thật.

## Gate và căn cửa sổ

- Tái dựng đủ 256 mẫu cho cả 32 event từ sample frame CRC hợp lệ. R index và end timestamp khớp chính xác log (sai khác 0 µs).
- 31 cửa sổ công bố đều không có rail, LO/error flags; các block 256 mẫu chứa chúng đầy đủ, không rail/lead-off, PTP>=20 và diff<=25%. Diff lớn nhất từng cửa sổ khoảng 8,39%.
- Source pipeline.cpp kiểm tra chất lượng block, 512 mẫu/tối thiểu 2 block phục hồi, generation, độ mới mẫu/cửa sổ, normalization, quantization clipping, rồi safety trước và sau Invoke. `rejected=0 reason=NONE` và counter classified tăng là bằng chứng runtime đi qua đường publish đó. Các biến nội bộ như good/generation ở từng lệnh không được dump đầy đủ; không tuyên bố quan sát trực tiếp mọi phép kiểm tra nội bộ.
- Gate hiện tại là heuristic cần thiết, **không phải bộ chứng nhận ECG/QRS thật**. Nó không có kiểm tra morphology đảm bảo tín hiệu không phải dao động analog. power50_ratio chỉ là thông tin chẩn đoán; không có ngưỡng rejection trực tiếp cho chỉ số này trong signal_block_reason.

## Trước — trong — sau

Khoảng cửa sổ thành công thứ nhất: 3690,397763–3698,881763 s, ADC 295–2142, không rail/lead-off. Trong 10 s trước có 118 mẫu lead-off và baseline trung bình khoảng 2527; trong khoảng thành công baseline trung bình khoảng 1593; 10 s sau khoảng 2389, có 75 mẫu lead-off. Lead-off đầu tiên sau output cuối xuất hiện ở 3699,729763 s; status SIGNAL_INVALID/LEADS_OFF ở 3700,240461 s. Rail tiếp theo quan sát được ở 3713,081763 s. Vì vậy lần ngừng đầu không bắt đầu bằng clipping: lead-off đã đủ để hủy xử lý.

Khoảng thứ hai: 3865,533763–3868,469763 s, ADC 1131–2017, không rail/lead-off. Trong 10 s trước có 73 mẫu lead-off, mean~2493; trong khoảng thành công mean~1733; 10 s sau mean~3085, có 35 mẫu rail và 136 mẫu lead-off. Rail đầu tiên sau kết quả cuối ở 3869,337763 s (raw4081), tiếp đến event bị chặn trước Invoke ở 3869,357359 s. Status ADC_SATURATION ở 3869,712461 s; lead-off đầu tiếp theo ở 3870,713763 s. Lần này clipping đi trước lead-off. Thứ tự cho thấy hai lỗi không đồng nghĩa nhau.

Status được phát định kỳ, khác timestamp mẫu; không dùng thời điểm status làm chính xác thời điểm lỗi vật lý bắt đầu. Quality descriptors phải đọc cùng quality_t_us, có thể là block trước đó.

## Nguy cơ nhiễu bị nhận thành nhịp

recorded_windows.png vẽ trực tiếp ADC đã lưu: dạng rơi nhanh rồi hồi chậm lặp khoảng160ms, với thành phần nổi bật6,25Hz và các harmonic12,5/18,75Hz. Detected RR phần lớn316–324ms, tương ứng detector bỏ qua chu kỳ xen kẽ do refractory75mẫu=300ms. Đây là bằng chứng mạnh rằng detector đang theo một dao động tuần hoàn; chưa chứng minh đó là QRS sinh lý. Không có annotation/reference độc lập nên không thể kết luận 28 output PVC là 28 PVC thật, cũng không thể tính tỷ lệ phân loại sai.

Không có bằng chứng nhiễu50Hz là nguyên nhân chính trong chính các cửa sổ được công bố: phép tính power50 theo công thức firmware khoảng1,2–6,3%, thấp hơn nhiều các status ngoài khoảng này. Artefact/mất tiếp xúc/common-mode/bias hoặc dao động phục hồi analog là giả thuyết phù hợp; log không xác định được linh kiện hay dây nào gây ra. Không kết luận lỗi isolation hay điện áp cụ thể từ raw counts.

## Giới hạn UART và dữ liệu mới nhất

Hai file inference có lần lượt1 và39 dòng có dạng frame nhưng không vượt CRC theo parser chẩn đoán theo dòng; một số là fragment ngắn lặp lại. Đã loại các dòng đó, không sửa chúng. Tất cả32 cửa sổ vẫn có đủ mẫu CRC hợp lệ; event V4_BEAT là plain text, không có CRC riêng, được đối chiếu với status/counter. Không suy diễn nguồn gây fragment là UART phần cứng nếu chưa có bằng chứng. Các capture gần đây ở boot mới chưa có inference trong snapshot được đọc. File capture mới nhất có thể vẫn đang được ECG Monitor ghi; thống kê của nó trong analysis.json chỉ thuộc snapshot đọc lúc phân tích, không phải phiên đã đóng.

## Hướng xử lý không cần đồng hồ điện áp

1. Khi đã tháo điện cực khỏi người và tắt nguồn: kiểm tra bằng mắt/đấu lại OUT34, LO+27, LO-26, GND, chân nguồn theo nhãn; kiểm tra đầu cắm và dây chập chờn, dùng dây ngắn/cố định, thay dây hoặc bộ cáp nghi lỗi. Không kéo LO xuống LOW để vượt gate.
2. Dùng nguồn ECG mô phỏng phù hợp hoặc module/cáp tốt đã biết để đối chứng trên bench, không nối người. Đây là cách phân biệt lỗi front-end/cáp với pipeline khi chưa có thiết bị đo; nếu chưa có nguồn/module đối chứng thì chưa thể khoanh vùng phần cứng chắc chắn.
3. Giữ nguyên model/gate. Cần kiểm chứng morphology bằng tín hiệu tham chiếu trước khi coi output là ECG/PVC thật; không giảm ngưỡng clipping hoặc ép inference. Chưa sửa detector/quality gate trong lượt này.

Không yêu cầu đo VCC/OUT, không đo lại hoặc thay thuật toán. Xem analysis.json, per_beat_audit.csv, periodicity.json, hình waveform và evidence_manifest.json để truy vết.
