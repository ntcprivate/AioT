# Kết quả cuối Giai đoạn2B — tiếp tục và chốt phần đang dở

**Parity đã sửa EXACT; detector vẫn FAIL record121; AI-live LOCKED.** Giữ11 file
đang sửa, snapshot ở `debug/r_peak_phase2b/resume`; không làm lại nghiên cứu/tune.
Đính chính: curvature đã bị loại trên Train. Bản chạy là magnitude/EMA0,025,
xác nhận200ms, chỉ thay candidate khi mạnh hơn1,5lần; chọn tham số trên6 Train
record đã định trước. Không chọn lại tham số trong lượt tiếp tục này.

## 1. Source và nguyên nhân16 sai khác

Giữ nguyên `main/signal.h/.cpp` 2B, toàn bộ hàm FIFO2A khớp source. Sửa thêm đúng
`main/single_round_fc.cpp`: nhánh FC per-tensor INT8 cuối dùng cùng scoped
single-rounding helper như per-channel, giữ init/prepare/multipliers/shifts/
activation clamp. Không đổi global rounding của operator khác, weights/model,
threshold0,52, golden, preprocessing, telemetry/GUI,GPIO hoặc safety/FSM.

16 trường hợp là **8 input duy nhất lặp candidate/safe**. Mỗi input được kiểm
Python/C++ preprocessing khớp byte, TF đọc lại đúng INT8 bytes, SHA ghi riêng.
Operator0..13 EXACT; sai bắt đầu ở **op14 FULLY_CONNECTED per-tensor**,1LSB.
Accumulator vừa int32, không saturation; tính lại double-rounding đúng native
cũ và single-rounding đúng TensorFlow ở cả8 case. Logistic op15 khuếch đại thành
1..4LSB output, tối đa4/256=0,015625 probability.

Generic INT8 spec cho phép sai khác số học giữa backend, nên double-rounding
không tự nó là vi phạm mọi backend. Lỗi ở đây là **adapter chưa đủ nhánh cho
contract EXACT CPU-builtin của dự án**; không dùng đặc tả để nới tiêu chí.
[Đặc tả TensorFlow](https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/g3doc/performance/quantization_spec.md).

|Record|Center250Hz|Index candidate / safe trong33586|Code trước→TF/sau|p trước→TF/sau|Quyết định0,52|
|---|---:|---|---|---|---|
|118|5613|3923 / 6201|-55→-53|0.28515625→0.29296875|N / không đổi|
|118|12239|3955 / 6233|70→68|0.77343750→0.76562500|V / không đổi|
|118|416969|5983 / 8261|-116→-115|0.04687500→0.05078125|N / không đổi|
|210|200430|13355 / 15993|106→105|0.91406250→0.91015625|V / không đổi|
|214|22287|17549 / 19805|-109→-108|0.07421875→0.07812500|N / không đổi|
|233|20069|22088 / 25156|-7→-3|0.47265625→0.48828125|N / không đổi|
|233|59286|22360 / 25428|-23→-20|0.41015625→0.42187500|N / không đổi|
|233|291311|23940 / 27008|-93→-92|0.13671875→0.14062500|N / không đổi|

**Cả16 không đổi quyết định trước hoặc sau sửa.** Case233/20069 có annotationV
vẫn choN dù probability tăng: sửa parity không đồng nghĩa sửa classification.
CSV đủ16 dòng có code/probability/error/inputSHA/mode:
`debug/r_peak_phase2b/int8_fixed_checks/sixteen_case_review.csv`.
Operator tensors và accumulator/multiplier/shift ở `int8_diagnosis/`.

Sau sửa **33586/33586 EXACT**,9425/9425 EXACT và12/12 golden×33 ổn định. Cả16
operator của8 case khớp. Giữ evidence trước sửa; native host mới ở
`int8_fixed_host/`, không ghi đè executable cũ.

## 2. Detector cuối — cùng Validation và cách chấm

7 record/MLII/resample25/36/annotation/BEATS/greedy matching±12 mẫu=48ms giữ
nguyên; không crop startup/biên, không dùng Test. Tái chạy sau fix và khớp chính
xác detector trước fix. Không sửa detector để cứu121.

|Record|TP/FP/FN2A|TP/FP/FN2B|Sensitivity2B|PPV2B|Tiêu chí cũ|
|---|---:|---:|---:|---:|---|
|115|1939/12/14|1949/1/4|99.7952%|99.9487%|PASS|
|118|2256/23/22|2267/12/11|99.5171%|99.4735%|PASS|
|121|1781/65/82|1845/20/18|99.0338%|98.9276%|FAIL|
|210|2623/16/27|2635/5/15|99.4340%|99.8106%|PASS|
|214|2251/9/11|2253/4/9|99.6021%|99.8228%|PASS|
|233|3064/4/15|3068/2/11|99.6427%|99.9349%|PASS|
|234|2740/7/13|2749/1/4|99.8547%|99.9636%|PASS|

16838 reference: TP16654→16766,FP136→45,FN184→72;
sensitivity98.9072%→99.5724%,
PPV99.1900%→99.7323%. Detector tìm16811 peaks,16766 match,72 miss.
121 còn20FP/18FN,PPV98,9276%<99%; sensitivity99,0338% đã đạt. Giữ toàn bộ38 lỗi
và nearest-annotation delta ở `int8_fixed_checks/record121_errors.json`;
14 FP đứng trước reference bị miss (64..420ms). Probe chỉ đọc state của
class hiện tại tại18 FN:8 không có local maximum vượt threshold trong±12 mẫu,
5 thấy local maximum vượt ngưỡng nhưng bị refractory chặn,2 warm-up đầu,
1 thiếu phần cuối window;2 còn lại có candidate đủ điều kiện nhưng không phát
beat khớp sau confirmation/matching, cần theo dõi thêm cluster. Đây là phân nhóm
theo nhánh quan sát có thứ tự ưu tiên, không phải ablation nguyên nhân độc lập;
không khẳng định giải phẫu P/T hoặc đổi tham số dựa vào các ca này.
Trace ở `int8_fixed_checks/record121_branch_trace.csv` và summaryJSON.
Không conflict reset/full/duplicate/order;2 pending cuối không padding.
Flat/pure50Hz30s đều0peaks/0safe windows; no-QRS vẫn phát safety issue.

## 3. NORMAL/PVC end-to-end offline

C++ detector xuất raw256 thực, chuẩn hóa/quantize C++ thật, native INT8 đã sửa,
threshold0,52. Safe host mirror giữ quality/recovery2block, reset khi issue và
abstain/reset khi quantization clipping. Không phải full RTOS/generation/FSM
hay thử trên người. Clipping được preflight trước native batch để khỏi dùng
score không hợp lệ; firmware thật Invoke rồi loại score. Không đồng nhất số
lần gọi thực hoặc latency của hai đường.

Reference mọi loại16838; binary chỉ **11167N+1301V=12468**. Safe mirror có
**16777 cửa sổ formed, 2 không hợp lệ do clipping,
16775 cửa sổ qua CNN**. Trong đó matchedN/V=12378,
matched loại khác=4352, unmatched=45.
L/R/A/F/... liệt kê riêng trong JSON, **không tự gán thành N**.

Confusion matrix matchedN/V hợp lệ (hàng=true, cột=prediction):

| |Pred N|Pred V|
|---|---:|---:|
|True N|10673|428|
|True V|136|1141|

428 NORMAL→PVC, 136 PVC→NORMAL. Miss trước CNN gồm detection/gate/
recovery/clipping: **66N +24V**.
Thêm **21 cảnh báoPVC từ đỉnh không khớp annotation**;
24 unmatched choN. Các số này tách khỏi lỗi phân loại nhịp đã match.

|Lớp|Precision matched|Recall matched|F1 matched|Recall toàn reference N/V|F1 gồm miss/unmatched|
|---|---:|---:|---:|---:|---:|
|N|98.7418%|96.1445%|97.4258%|95.5763%|97.0273%|
|V|72.7215%|89.3500%|80.1827%|87.7018%|78.9346%|

Metric cột cuối cộng miss trước CNN vàoFN và unmatched prediction vàoFP;
precisionPVC theo cách này=71.7610%.
Matched các nhãn ngoài N/V vẫn ngoài phạm vi binary — đây không phải precision
lâm sàng trên mọi loại nhịp. Parity là đồng nhất tính toán, **không phải accuracy**.
Detector tốt hơn vẫn để CNN nhầm lớp đáng kể; không có ngưỡng nghiệm thu
classification độc lập đã định trước, nên không tự tạo tiêu chíPASS.

Center→window-ready508ms (giữ128trước/128từcenter); host native batch trung bình
0.1163ms/window gồm process/I/O, **không phải Invoke/WCET ESP32**.
Inference/scheduler/heap/stack/tổng latency board: PENDING.

## 4. Regression, build và bảo toàn

|Kiểm tra|Kết quả|
|---|---|
|Detector từng record cũ|FAIL121 PPV;6 record khácPASS|
|Golden|PASS12/12×33|
|Preprocessing+parity corpus cũ|PASS9425/9425|
|Extended parity|PASS33586/33586,0 đổi class|
|Operator trace8 input|PASS16operator/input|
|Python / operator trace tests|PASS58 /14|
|C++ FIFO/window/signal/safety/lead-off/UART/rounding|PASS|
|ESP-IDF5.4.4 ADC thật /Synthetic|PASS /PASS|
|Classification, hardware readiness|Chưa nghiệm thu /PENDING|

DetectorRAM6496byte, tăng48byte so2A; FIFO6336byte không đổi, không heap/task
mới trong đường lấy mẫu. Sửa FC dùng reference single-round loop, không đổi
arena/init/prepare; CPU/WCET thực cần đo trên board, không suy từ benchmark host.
Binary ADC=317792byte;Synthetic=316352byte,
SHA trong JSON; log mới ở `int8_fixed_checks/build_*.log`.

Giữ11 source đang dở, thêm sửa kernel1file có bằng chứng và công cụ chẩn đoán/
regression; 65 file còn lại khớp SHA gồm model/golden/preprocessing,
dataset/split,telemetry/GUI,ADC/GPIO/quality/FSM và cấu hình khóa live. Report và
binary trước fix giữ ở `resume/`;2A không ghi đè. Thử nghiệm Train không chạy lại.

## 5. Việc tối thiểu còn lại

1. Phân tích20FP record121 trên dữ liệu phát triển; giữ nguyên tiêu chí và tách
   đánh giá độc lập khỏi Validation đã dùng lại.
2. Xác lập tiêu chí nghiệm thu classification cho N/V và xử lý nhãn ngoài phạm
   vi; không sửa threshold/model trong lượt này.
3. Khi có yêu cầu riêng, thử bench/simulator với **AI-live vẫn LOCKED**: đúng
   binarySHA,12golden+8input trace trên Xtensa,250Hz dưới tảiCNN,queue/heap/stack/
   latency và signal-quality/lead-off. Không nối cơ thể hay dùng INVALID_LEADS
   để kết luận N/PVC. Chưa đủ bằng chứng mở live hoặc tuyên bố hiệu quả lâm sàng.

Source detector/FIFO không retune khi tiếp tục. Không COM3/flash/reset/train/
unlock. Dừng tại báo cáo này. Máy đọc: `debug/r_peak_phase2b_results.json`;
evidence end-to-end mới ở `debug/r_peak_phase2b/fixed_validation/`.
