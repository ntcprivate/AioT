# Phần còn thiếu — ưu tiên, không chạy ở lượt kiểm kê

## Không cần đo lại

Giữ25.010/25.010 host parity,22/22 golden, MIT100/PVC replay, hai benchmark FP32–INT8 và toàn bộ offline prediction hợp lệ. Không tái huấn luyện, xuất INT8 lại hoặc chỉnh threshold/detector để sửa F1. Chỉ làm regression chịu ảnh hưởng nếu source/hardware thật sự thay đổi sau khi được cho phép.

## 1. Hoàn tất điều kiện đo ADC, trước mọi flash

**Hiện trạng:** source ADC V4 và historical build PASS; analog NOT RUN. Board cuối cùng được ghi nhận đang BENCH_INT8. Đây không phải ADC đã sẵn sàng nghiệm thu accuracy.

Người dùng cần có máy mô phỏng ECG, module AD8232 với schematic/marking, DMM và oscilloscope thích hợp; kiểm nguồn3,3V, biên độ/offset, cực tính và chuyển đạo, LO+/LO−. Xem `adc_preparation.md`. Xác nhận không có đường nối người.

Hai phụ thuộc phần mềm cần được duyệt ở lượt riêng:

- GUI `ai.py:26` đang hard-code0,52. Không dùng GUI/CSV classifier hiện tại làm nguồn sự thật V4 cho score0,52–0,88; trước khi dùng cần sửa validator đọc threshold/model contract rồi test liên quan, không đổi threshold firmware.
- Cần logger/evaluator **ADC continuous**: thời gian bắt đầu/kết thúc, reference clock, CRC/sequence/sample-index và reason/drop counters; utility replay hiện chờ BEGIN/END/record, không dùng nguyên xi cho ADC. Raw UART có thể được lưu bằng capture duration-controlled riêng, nhưng chưa có phép xác minh ADC như vậy trong hồ sơ. Không sửa code ở lượt này.

**Hoàn thành khi:** schematic/nguồn/lead/voltage được đo và lưu; phương pháp capture và protocol ADC đã khóa; firmware ADC binary đúng model/hash có thể chọn chính xác. Nếu dùng snapshot ADC cũ phải kiểm manifest và dependency/boot settings, không flash cache hiện tại BENCH_INT8/PVC dựa vào tên directory.

## 2. ADC engineering smoke và safety, không accuracy trước

Sau phê duyệt, nạp đúng ADC mode, dùng simulator. Thu đầy đủ boot/golden/V4 hash, raw samples/timestamps/LOs, queue/drop, quality/rejected, R-index/code/score và memory/latency. Không cần chạy lại toàn bộ offline hoặc benchmark. Golden khi boot firmware ADC là kiểm tra gắn với binary mới, không thay thế parity đã có.

Các ca tối thiểu, lặp chỉ khi có lỗi cần xác minh: simulator Normal ổn định; lead-off từng đầu/kết nối lại; ngừng nguồn tín hiệu; tín hiệu phẳng hoặc clipping trong giới hạn điện an toàn; signal recovery. Không ép điện áp quá giới hạn để tạo lỗi. Dùng disconnect simulator thay cho điện cực người. Không tự kéo LO xuống LOW.

Điều kiện kỹ thuật khóa trước đo: đúng V4/threshold0,88/code98; sampling250Hz và dt/dropped được báo; không lỗi ADC/queue/block/mẫu mất trong đoạn ổn định đã định; invalid/lead-off/stale phải UNKNOWN và không tái dùng prediction cũ; khôi phục theo good512/two-good-blocks hiện có. Nếu FAIL giữ raw/reason, dừng, không nới gate. Bounds timestamp2–6ms là kiểm tra hiện hành, không đồng nghĩa jitter nào trong khoảng đó cũng đạt mọi tiêu chuẩn ứng dụng; ghi min/max thực tế và budget đã chọn trước.

**Hoàn thành khi:** raw log integrity, sample counts và sự chuyển safety state được chứng minh bằng log/mốc thao tác; chưa tự gọi đó là phát hiện PVC đúng.

## 3. Analog ECG N/V có nhãn và đồng bộ

Dùng simulator hỗ trợ PVC có lịch nhịp/marker xuất ra, hoặc analog playback waveform có annotation được khóa từ Train/Development. Cố định lead/polarity/amplitude/filter/RR/chương trình beat và khoảng thời gian trước chạy; không đổi waveform sau khi thấy dự đoán. Tốt nhất có hardware trigger/reference timestamp phù hợp mức điện với ESP32; nếu chưa có reference đồng bộ, chỉ đo vận hành, không công bố TP/FN/accuracy.

Chấm với một-một/tolerance đã đăng ký và ghi rõ analog filter/group delay. Không ước lượng/chỉnh delay từ nhãn Evaluation rồi làm matching đẹp hơn; nếu cần xác định delay thiết bị, làm calibration bench riêng trước đoạn chấm và giữ cố định. Báo detector miss, localization, window/gate abstention, classifier errors và unmatched alarm riêng. Missing PVC luôn FN, missing N không TN, FP unmatched tách N→PVC.

**Hoàn thành khi:** có bộ reference độc lập với detector/CNN, alignment có bằng chứng, raw ADC→classification đầy đủ và metrics per-case. Không có P/R/F1 mục tiêu nghiệm thu được người dùng chốt trong lượt này; phải chốt trước để không tự đặt tiêu chí rồi PASS trên dữ liệu đã xem. Simulator chỉ xác minh electrical chain và các waveform đó, không chứng minh clinical population accuracy.

## 4. Độ ổn định PVC và tính độc lập nghiên cứu

Pilot20PVC hiện có Recall9/20=45%; một lỗi làm Recall đổi5điểm phần trăm. Beat cùng segment/patient tương quan; không xem20beat là20patient độc lập. Existing Validation dùng trong phát triển và Test đã được xem/chọn ứng viên; không đổi tên chúng thành final independent cohort.

Cần thiết kế cố định thêm nhiều đoạn/patient, N/PVC morphology/RR và điều kiện đã định, group-disjoint, có cỡ mẫu dựa mục tiêu/độ chính xác ước lượng; không chỉ chọn đoạn có model dự đoán tốt. Có thể dùng Development để định lượng lỗi vận hành nhưng phải ghi exploratory. Muốn tuyên bố tổng quát hóa xác nhận sau lựa chọn model cuối, cần cohort ECG thật có nhãn **chưa từng dùng cho fit/checkpoint/threshold/thiết kế/phân tích lỗi/lựa chọn ứng viên** và kiểm tra overlap patient/source. Nghiên cứu không bắt buộc kết nối người trực tiếp: dữ liệu đã được cấp phép hoặc simulator/playback có thể phục vụ mục tiêu phù hợp, nhưng simulator không thay cohort cho kết luận clinical accuracy.

Chưa chỉ định dataset hay chạy cohort mới ở lượt này. Không dùng Test cũ để tuning. Trước lượt xác nhận phải khóa model, detector, preprocessing, threshold, quality/matching, scope/abstention và tiêu chí; đánh giá một lần, báo cả thất bại.

## 5. Những bổ sung chỉ khi bài báo cần

Benchmark hiện đủ mô tả một board/boot mỗi dtype. Nếu cần suy luận thống kê timing, mới lập thêm nhiều boot/session, đảo thứ tự AB/BA và điều kiện clock/nhiệt/nguồn; không chạy lại660lượt chỉ để có thêm hàng dữ liệu. Nếu yêu cầu năng lượng/power thì cần dụng cụ và phép đo riêng; hiện thiếu, không điền số ước lượng. Không bắt buộc các phép này để lưu hồ sơ mô tả hiện tại.

## Thao tác tay và điểm dừng

Người dùng: xác nhận model/revision module, chụp schematic/đấu dây, chuẩn bị ECG simulator/adapter/nguồn và dụng cụ; đo điện áp khi chưa nối GPIO; chọn đúng lead và chế độ PVC/marker; cắm USB đúng board rồi cho phép build/flash/capture ADC khi sẵn sàng. Không flash/reset/COM nào trong lượt kiểm kê. Không cần người dùng thực hiện phép đo trên cơ thể để hoàn tất các bước bench trên.
