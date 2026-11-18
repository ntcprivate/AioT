# Audit V11 trước ESP32: suy giảm F1 end-to-end

## Kết luận chính

Đã phân rã lại predictions đã lưu, không load model, không inference hay chạy lại Final Test. Số FP tổng tái dựng khớp artifact từng record. Nguyên nhân định lượng chính là **PVC alarm trên detection không match reference beat**, không phải chủ yếu nhịp N đã match bị CNN nhầm. Tuy nhiên “unmatched” là kết quả chấm điểm, chưa phải chẩn đoán waveform là nhiễu/T/P; cần tránh gọi mọi unmatched peak là peak giả đã được chuyên gia xác nhận.

| Test | Tổng FP | FP trên N đã match | PVC alarm trên unmatched peak | Tổng unmatched detections |
|---|---:|---:|---:|---:|
| MIT-BIH | 2450 | 102 | 2348 (95.84%) | 2955 |
| INCART | 3320 | 49 | 3271 (98.52%) | 3443 |

MIT 113+117 chiếm 2177/2450 FP (88.86%); INCART I63+I64, cùng patient27, chiếm 3110/3320 FP (93.67%). Đây là tập trung lỗi theo record/patient, không phải suy giảm đồng đều.

## Pipeline, source và cấu hình

Final Test `python/finalize_test_v11.py:35–87` dùng đúng lock threshold0.80, RR mean/std Fit và model SHA256
`61909ec7f93e3d8823627a0127422aefdd098f92a9c95619073968c7a3eb3601`.
Development F1 95.43%/94.22% được tạo bởi `python/evaluate_rpeak_candidate_v11.py:15–48`, stage `old_V11`, cùng **final model**, khác với các kết quả CV dùng checkpoint từng fold ở `end_to_end_detector/` trước đó. Không được trộn hai loại model/kết quả.

- Detector: Final Test chạy `results/cnn_v11/rr_detector_validation/detector.exe`; Development đọc các trace do chính executable này tạo. Current source `firmware/esp32_ecg_tinyml_integrated/main/signal.cpp:103–118` dùng baseline .025, envelope .01, threshold max(30,2.5*envelope), refractory75, confirmation50, replacement1.5. Không phải confirmation58 của claim bài báo.
- Replay50 từ source hiện tại đã lưu tại `paper_rpeak_verification/`: center arrays trùng **toàn bộ 7/7** trace MIT Development cũ. Đây là evidence hành vi trên cohort này; thiếu manifest source/compiler/binary có timestamp lúc tạo executable để chứng minh tuyệt đối binary provenance cho mọi record Test. Không phát hiện bằng chứng đổi detector version giữa hai lượt.
- Cửa sổ native replay: raw `[center-128, center+128)` đúng 256 mẫu; emit chỉ sau khi center+127 có mặt; float windows giữ raw ADC. Final Test đọc windows.bin; Development reconstruct từ cùng raw ADC tại chính các centers. Cả hai z-score toàn cửa sổ bằng float32 với epsilon1e-8.
- ADC mapping đều `clip(rint(2048+200*signal250),0,4095)`; Test INCART đọc return_res32 và cast resample float32, còn Development đọc float64. Đây là khác biệt precision nhỏ có thật, nhưng chưa có evidence đủ để gán hàng nghìn FP cho nó. Không điều chỉnh trong audit.
- Cả hai dùng **ungated `peak`**, không `safe_peak`. Harness có ghi quality/safe stream nhưng classification ở hai script bỏ qua safe gate. Vì vậy đây không phải hiệu năng full safety-gated firmware/AD8232 thực.
- RR: `python/run_v11_rr.py:16–24`: current interval, median tối đa7 preceding intervals, ratio, history fraction. Mọi feature detector dùng `peaks[:j+1]`, không future beat/label. Annotation offline dùng beat timestamps (oracle), chỉ N/V được chọn làm target; các beat OTHER vẫn tham gia RR history.

## Matching, OTHER và FP/FN

Final và Development đều one-to-one greedy nearest trong ±38 samples (152ms), tham chiếu tất cả symbols thuộc `NLRBAaJSVrFejnE/fQ?`. Chỉ matched N/V vào confusion matrix. Matched OTHER **không relabel N** và không tính FP dù CNN dự đoán PVC. Test có 2532/659 OTHER matched; 24/177 trong số đó dự đoán PVC nhưng đã được loại đúng theo scope N/V. Số liệu không chứng minh model phân biệt được PVC với tất cả OTHER.

Reference V không có detection được tính FN; matched V predicted N cũng FN. Missing N là abstention, không TN. Unmatched detection predicted PVC được cộng FP; unmatched predicted N không thêm TN. Không có duplicate center chính xác ở các Test records. Không có annotation-relative completion deadline trong final_test hay Development stage old.

Do accounting này, confusion matrix không có đúng một observation cho mọi reference event; “ledger accuracy” không phải accuracy thông thường trên tập nhịp cố định. F1 PVC vẫn giữ missing V trong mẫu số và thêm unmatched PVC alarms, nên giảm mạnh là có thực theo định nghĩa đã lưu.

Không có lỗi số học FP tổng hoặc xử lý OTHER giải thích được suy giảm. Các scores offline và detector đã lưu được đối chiếu: ít nhất 55 MIT/22 INCART matched N chuyển từ offline-correct sang detector-PVC. Nhưng cửa sổ và RR cùng đổi, nên chưa tách được ảnh hưởng nhân quả riêng từng thành phần.

## FP theo record

| Dataset | Record/patient | Tổng FP | FP matched N | FP unmatched alarm | Unmatched alarm cách reference gần nhất ≤75 samples |
|---|---|---:|---:|---:|---:|
| MIT | 113 | 1580 | 0 | 1580 | 161 |
| MIT | 117 | 597 | 0 | 597 | 592 |
| MIT | 108 | 158 | 67 | 91 | 61 |
| MIT | 222 | 91 | 29 | 62 | 30 |
| INCART | I64 / patient27 | 1749 | 0 | 1749 | 400 |
| INCART | I63 / patient27 | 1361 | 0 | 1361 | 274 |
| INCART | I21 / patient10 | 40 | 0 | 40 | 10 |
| INCART | I62 / patient27 | 40 | 4 | 36 | 6 |

Toàn bộ records trong `analysis.json`. Tổng unmatched PVC alarm nằm trong75 samples của reference là 853 MIT/742 INCART. Đây là near-reference/secondary/localization ambiguity, **không** chứng minh đổi tolerance sẽ đúng: nhiều reference đã có một detection match và peak thứ hai vẫn phải coi extra theo one-to-one. Không sweep tolerance hoặc dùng annotation chỉnh peak. P95 error của *matched* peaks thấp ở113(1 mẫu), I63/I64(2 mẫu) nhưng không đo error của unmatched peak; không dùng nó để kết luận mọi peak chính xác.

## Development có nằm trong training V11 cuối không?

`finalize_test_v11.py:19–31` lấy pool Train+Development; Checkpoint/Calibration theo nhóm V6; Fit là phần bù trong pool đó. Kiểm tra lock cho thấy Fit∩Development rỗng theo MIT record và INCART patient.

Nhưng Development **được sử dụng trong quá trình phát triển cuối**:

- MIT checkpoint:115,118,121,214,234; calibration:210,233.
- INCART checkpoint patients:4,20,25; calibration:15,28.

Toàn bộ cohort Development tính F1 95.43%/94.22% nằm trong các nhóm chọn checkpoint/threshold, không phải holdout độc lập của final model. Cần phân biệt không có gradient Fit trên Development với việc Development vẫn được dùng lựa chọn. So sánh F1 Development cao với Test thấp không chứng minh bug; nó phù hợp với selection optimism và distribution shift, nhưng chưa lượng hóa riêng đóng góp của hai yếu tố.

## Bằng chứng và giả thuyết

**Đã xác minh:** FP tăng chủ yếu unmatched alarms; lỗi tập trung record/patient; OTHER không bị gộp N; threshold và feature contract thống nhất trong code; zero duplicate centers; Development đã dùng selection; quality-gated stream không được dùng; annotation-RR/window là input oracle khác detector-window.

**Chưa đủ bằng chứng:** unmatched peak thật là T/P hay nhiễu, beat thật thiếu annotation, secondary QRS lobe hoặc localization > tolerance; RR bị rút ngắn do peak thừa có phải cơ chế chính khiến score PVC cao; tỷ lệ đóng góp riêng window miscentering/RR corruption; precision float32 là nguyên nhân đáng kể; mức quality gate có thể sửa hiệu năng và mức bỏ sót nó gây ra. Không kết luận từ ngữ “RR hợp lý” rằng peak đúng: refractory75 đã giới hạn RR>=300ms nên một số extra events vẫn nằm trong khoảng sinh lý.

## Khắc phục tối thiểu đề xuất — chưa thực hiện

1. Chuẩn hóa một evaluator chung, version/hash detector+runtime và ECG/RR contract; giữ score ledger riêng matched N/V, OTHER, missed N/V, unmatched alerts. Chọn một convention precision float và mô tả rõ ungated/full quality gate. Không thay tolerance để làm đẹp Test.
2. Trên Train/Development, adjudicate waveform các nhóm lỗi tương tự và cố định thiết kế kiểm tra QRS/T rejection/quality từ evidence đó. Phân rã window-only/RR-only trên Development nếu được duyệt để định vị thành phần, không chỉnh theo Test113/117/I63/I64. Giữ CNN/threshold hiện tại trong lượt chẩn đoán.
3. Chưa tích hợp V11 như mô hình triển khai đã được kiểm chứng. Sau khi khóa toàn pipeline, cần cohort độc lập mới và đánh giá detector-centered cùng quality gate thực; các Test hiện tại đã exposure nên chỉ là hồi cứu.

Audit này chỉ phân tích source, configuration, predictions và annotation đã có; không train, tuning, inference lại, replay Final Test hay sửa firmware.
