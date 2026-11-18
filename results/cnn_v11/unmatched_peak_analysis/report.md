# Unmatched peaks và giao thức evaluator trước ESP32

## Phạm vi và bằng chứng

Chỉ 38 MIT-BIH và 63 INCART records thuộc Train+Development; script assert record thuộc các split này trước khi đọc waveform. Không Test, CNN inference, training, detector tuning hoặc sửa firmware. Dùng native traces đã lưu trong `rr_detector_validation/`, ECG/annotation gốc và source firmware. `analysis.json` có thống kê mọi record/patient; `peak_cases.csv` có từng unmatched center, RR trước/sau, annotation gần nhất và đặc trưng waveform. RR sau chỉ dùng phân tích hồi cứu, không phải input/decision lúc chạy thực tế. `waveform_examples.png` gồm sáu ca chọn từ các record nhiều unmatched; không phải mẫu ngẫu nhiên đại diện toàn bộ.

## 1. Vì sao unmatched không đồng nghĩa peak giả

| Quan sát, phân loại sơ bộ | MIT-BIH | INCART |
|---|---:|---:|
| Tổng unmatched theo protocol38 | 483 | 8319 |
| Cách reference 39–75 samples, reference đã có match | 56 | 2537 |
| Cách reference 39–75 samples, reference chưa match | 133 | 1636 |
| Xa reference hơn75 samples, chưa xác định | 294 | 4001 |
| Window chứa ADC mapping rail (ưu tiên phân loại) | 0 | 145 |
| Matched OTHER, không phải unmatched | 18775 | 4761 |

Các nhóm trong bảng là **quan sát**, không phải ground truth sinh lý:

- Gần reference chưa match: phù hợp lỗi localization ngoài tolerance; chưa xác nhận đó chính là R thật. Không tự tăng tolerance.
- Gần reference đã có match: có thể secondary lobe/double detection hoặc sóng khác; không được ghép hai detections vào một beat để làm đẹp PPV. Không có duplicate center chính xác; physiological double detection vẫn có thể có.
- ADC rail là hiệu ứng mapping/clipping đã đo, không tự chứng minh nguồn ECG gốc nhiễu hoặc điện cực lỏng.
- Xa reference: cần phân biệt T/P, nhiễu, rhythm không có beat annotation hay annotation thiếu. Không tự gán thành Normal hoặc R thật.

### Các ca waveform đã xem trực tiếp

| Record/center250 | Bằng chứng waveform/annotation | Kết luận mức bằng chứng | Thay đổi tối thiểu đề xuất |
|---|---|---|---|
| INCART I16 /233699 | Detection trên sóng rộng sau QRS khoảng264ms; QRS trước có detector riêng | T-wave-compatible, chưa expert-adjudicated | QRS/T morphology confirmation trên development riêng, không kéo refractory hàng loạt |
| INCART I25 /180652 | Detection trên sóng tròn rộng ~308ms sau QRS rõ/đã match | T-wave-compatible | Như trên |
| INCART I26 /239652 | Detection trên sóng rộng ~336ms sau QRS rõ/đã match | T-wave-compatible | Như trên |
| INCART I11 /235049 | Sóng nhỏ rộng giữa hai QRS, khoảng400ms trước QRS sau | P/T-compatible nhưng chưa đủ bằng chứng phân biệt | Giữ unresolved, cần review nhiều chuyển đạo nếu có |
| MIT207 /389014 | Waveform phức tạp; annotation lân cận là `!` liên tiếp, không thuộc BEATS | Vùng annotation ventricular-flutter waves ngoài reference scope, không được gọi chắc là nhiễu | Đánh dấu ngoài phạm vi N/V; báo riêng scope, không sửa số FP chính hồi cứu |
| MIT228 /313029 | Sóng lớn rộng sau QRS, có biến thiên baseline/nhiều thành phần | T-wave/baseline-artifact-compatible, chưa phân định | Review waveform/quality; chưa sửa detector |

MIT207 annotations gần center ví dụ:388975 `!`,389055 `!`,389118 `!`. Script reference hiện dùng `NLRBAaJSVrFejnE/fQ?`, không `!`; vì thế ít nhất một phần unmatched do **annotation scope**, không phải beat N/V bị bỏ annotation. Không đủ evidence để phân loại sinh lý toàn bộ483/8319 events từ sáu hình; các ca còn lại giữ unresolved có chủ đích.

## 2. Matching và metric contract hiện tại

Giữ nguyên greedy one-to-one, nearest detection trong ±38 samples (152ms), annotation center round-half-up. Matched reference symbols ngoài N/V nhưng trong BEATS là OTHER; được tính detector TP, loại khỏi classification N/V, không relabel N. Unmatched detection predicted PVC là FP alarm; unmatched predicted N không TN. Missing V tính FN; missing N là abstention riêng, không TN. FP/FN có thể xuất hiện đồng thời khi R localized ngoài tolerance. Các non-beat/rhythm markers không tự thêm vào R reference.

Không tìm thấy lỗi cộng confusion counts hoặc OTHER→N. Tuy nhiên có ba hạn chế evaluator cần công bố: (i) ungated stream khác firmware thật; (ii) unmatched có thể ngoài annotation scope nên không tương đương noise; (iii) ledger accuracy không conventional binary accuracy vì có extra events và missed-N abstention. Lỗi cũ deadline annotation+128 trong RR-only evaluator đã được xác định ở audit trước; không hiện diện trong final detector-window scorer. Không chạy lại bước đó.

Không đổi BEATS, tolerance hay accounting trong lượt này. Đề xuất report bổ sung non-beat/rhythm-scope buckets song song với metric chính; muốn thay protocol ở thí nghiệm sau phải khóa trước trên Train/Development, không sửa Test hồi cứu.

## 3. Đối chiếu evaluator ↔ firmware hiện tại

| Thành phần | Evaluator V11 đã dùng | Firmware hiện có | Kết luận |
|---|---|---|---|
| ADC | mapping synthetic2048+200*mV, clip12bit | GPIO34 ADC thật | Không phải calibration AD8232 |
| Lead-off/ADC errors | Không có kênh đo | pipeline_observe:357+, immediate invalidate | Không mô phỏng như luôn pass |
| Block quality | log chất lượng có sẵn nhưng classification chọn ungated `peak` | signal_block_reason; block failure invalidate/reset | Không tương đương |
| Recovery | Không áp dụng đầy đủ | good>=512, good_blocks>=2, generation checks | Cần replay state machine có điều kiện, không xóa mẫu tùy tiện |
| R-peak | native signal.cpp | cùng BeatDetector | MIT Validation trace arrays đã xác nhận khớp; không chứng thực đầy đủ binary build provenance |
| Window | [center-128,center+128),256 raw | cùng FIFO4, ring512 | Cùng hình học cắt; queue runtime riêng chưa mô phỏng |
| Normalize | numpy float32 z-score | preprocessing.h double mean/variance → normalized float | Cùng ý nghĩa, chưa phải bit-exact V11 contract |
| Quantization gate | FP32, không clipping int8 | quantize theo scale/zero model hiện hành; reject nếu clipped | Không dùng scale/zero V1 để suy ra V11 |
| RR | 4 causal features + Fit statistics | chưa có nhánh RR V11 trong engine | Firmware chưa tích hợp V11 |
| Model/threshold | V11 FP32,0.80 | ecg_ai::publish trong research_shadow.h dùng0.52, một input ECG | Phải cập nhật khi tích hợp; chưa sửa trong lượt này |
| Launch/publish | batch predict offline | model/golden ready, generation, queue, window age<=1.5s, recent sample<20ms; check lại sau Invoke | Không tương đương end-to-end firmware |

Source chính: `main/signal.cpp`, `pipeline.cpp:259–339,357–393`, `research_shadow.h`, `preprocessing.h`. Không dùng 50Hz power ratio làm gate: signal_metrics chỉ là diagnostic; signal_block_reason dùng ADC rail, minPTP và tổng chênh lệch mẫu, cùng timestamps.

## 4. Gate nào có thể tái hiện có căn cứ?

**Có thể tính trên synthetic ADC đã định nghĩa:** ADC rail margin16; blockPTP<20; high-frequency-difference test25%; validity/std của256 samples; sample/center continuity trong file; native window/FIFO invariants. Trace hiện có chứa `quality` theo block256 và lý do. Các phép tính này chỉ chứng minh pass/fail trên representation mô phỏng, không physical ECG quality.

**Có thể replay có điều kiện, chưa được xác minh đầy đủ:** recovery hai block/512 samples và resets theo quality; cần clone đúng worker state machine và ghi coverage/missed beats, không coi `safe_peak` harness là exact firmware. Harness safe path có quantization V1 và logic recovery riêng; dùng trực tiếp cho V11 sẽ gán nhầm contract. Có thể tính lượng tử clipping **sau khi** có V11 INT8 thật/scale thật.

**Không đủ dữ liệu để đo:** LO+/LO−, ADC read failures, nguồn/gain/common-mode thực, buffer integrity faults phần cứng, GPTimer jitter/gaps thực, queue/backpressure/RTOS latency, heap/stack, window-age theo wall clock và signal changed during inference. Timestamp đều4000us chỉ là giả định synthetic; không phải bằng chứng board không mất mẫu. Không giả lập pass hoặc tạo lỗi để tuyên bố tái hiện phần cứng.

## 5. Quyết định và bước tối thiểu tiếp theo (chỉ đề xuất)

1. Có evidence detector còn bắt sóng rộng ngoài QRS trên INCART; cần cải thiện/kiểm chứng QRS confirmation trước deployment. Chưa có candidate được chấp nhận. Không áp dụng lại cổng slope/refractory đã biết làm mất PVC.
2. Adjudication Train/Development cần mở rộng và lưu nhãn có độ tin cậy cho localization, secondary, T/P, rhythm-scope và noise; không dùng Test113/117/I63/I64 để chọn tham số. Bảng per-record và mọi case đã lưu để hỗ trợ review, không giả vờ có expert ground truth.
3. Khóa evaluator chung gồm matching/scope, subgroup metrics, abstention coverage, synthetic ADC và gate state; sau đó mới yêu cầu triển khai replay gate đúng. Không đổi định nghĩa metric đang báo cáo.
4. **Có thể chuẩn bị V11 INT8 và golden parity như kiểm thử kỹ thuật độc lập**, vì mục tiêu là arithmetic/operator/runtime compatibility. Chưa đủ điều kiện coi parity PASS là PVC system PASS hoặc bật AI-live. Cần representative Train-only calibration cho cả ECG và RR, kiểm tra missing-history/scaling và quantization, giữ model FP32/threshold0.80.
5. Trước thử end-to-end board: triển khai input RR causal/scaling/reset policy, threshold0.80, gate/queue contract với model V11, bộ replay ECG+RR có timestamp và kỳ vọng, rồi bench simulator kiểm thử timing/memory/gates. Các việc này chưa được thực hiện ở lượt audit này. Cần cohort độc lập mới để chốt hiệu năng, vì các tập cũ đã exposure.
