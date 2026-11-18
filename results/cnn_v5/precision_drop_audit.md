# Rà soát suy giảm Precision của CNN V5

Phạm vi: chỉ đọc source, split metadata và kết quả hiện có. Không chạy lại inference, không train, không thay model, threshold hoặc preprocessing.

## Kết luận ngắn

Không phát hiện bằng chứng dùng sai checkpoint, threshold, nhãn hoặc preprocessing giữa Validation và Test. INCART được chia theo patient và không chồng lấn. MIT-BIH được chia theo record/group, không chia theo beat, nhưng patient identity chỉ được xác minh chắc chắn cho cặp 201/202; vì vậy patient-level leakage của MIT-BIH chưa thể loại trừ hoàn toàn.

Nguyên nhân đã có bằng chứng mạnh là **V5 bị lệch phân bố score trên các record/patient Test và Validation đã bị dùng thích nghi quá nhiều để chọn cả epoch lẫn threshold**. V5 dự đoán số PVC gần đúng prevalence trên Validation nhưng dự đoán PVC nhiều gần gấp đôi trên Test. Kiến trúc nhánh trung tâm dùng Crop + Flatten có khả năng học đặc trưng vị trí/patient cụ thể hơn V4 dùng GlobalAveragePooling; đây là giả thuyết hợp lý nhưng chưa được chứng minh bằng ablation hoặc phân tích từng FP.

## 1. Split và nguy cơ leakage

### INCART — đã xác minh

- Split metadata lưu 22/5/5 patient cho Train/Validation/Test và `patient_overlap=false` trong `data/processed/incart_patient_split_v4.json`.
- Train gồm patient 1,2,3,5,6,7,8,11,12,13,14,16,18,19,21,22,23,24,26,29,31,32.
- Validation gồm patient 4,15,20,25,28.
- Test gồm patient 9,10,17,27,30.
- Extractor ghi `patient_ids`, `record_ids` và split cho từng beat tại `python/prepare_cnn_v4_incart.py:68-90`.

Kết luận: không có beat/record/patient overlap đã biết trong INCART. Suy giảm INCART không thể giải thích bằng việc cùng patient xuất hiện ở Train và Test.

### MIT-BIH — record-level, patient-level chưa hoàn toàn xác minh

- Dataset lưu `record_ids`, không lưu patient ID; source cảnh báo record ID không phải unique patient tại `python/05_build_dataset.py:177`.
- Split được tạo bằng group tại `python/06_train_evaluate.py:77-113`; kiểm tra cấm record/group overlap tại dòng 61-74.
- Cặp 201/202 được gộp thành một patient group và đã PASS.
- `results/data_leakage_audit.json` ghi `patient_identity_completeness.status=UNKNOWN`: ngoài 201/202, các record được dùng như patient proxy và chưa xác minh độc lập.

Kết luận: không có beat-level hoặc record-level leakage. Tuy nhiên chưa đủ bằng chứng để tuyên bố MIT-BIH hoàn toàn patient-disjoint. Đây là rủi ro có thể làm Validation lạc quan, nhưng chưa chứng minh là nguyên nhân trực tiếp.

## 2. Preprocessing và nhãn

### MIT-BIH

- Chỉ dùng MLII, resample 360→250 Hz tại `python/05_build_dataset.py:43-63`.
- Annotation N→0, V→1; nhãn khác bị loại tại dòng 65-68 và 85.
- Cửa sổ `[center-128:center+128]`; z-score riêng từng cửa sổ tại dòng 69-80.
- Train/Validation/Test đều lấy từ cùng NPZ đã preprocessing một lần, nên không có nhánh preprocessing khác nhau theo split.

### INCART

- Chỉ dùng lead II, resample 257→250 tại `python/prepare_cnn_v4_incart.py:37-52`.
- Chỉ giữ N/V; cùng cửa sổ 256 và cùng z-score tại dòng 49-68.
- Split được gắn sau khi cùng một pipeline tạo beat tại dòng 68-90.

Kết luận: preprocessing, segmentation và label mapping nhất quán trong từng dataset. Khác biệt MLII/II tồn tại giữa hai database nhưng không giải thích riêng sự sụt giảm Validation→Test bên trong cùng database. Không có bằng chứng OTHER bị đổi thành NORMAL.

## 3. Checkpoint và threshold

- Checkpoint hiện tại có SHA-256 `3b7c815814b6c6336118f536b36e36f096438055b3d1647b43277bce07fc24e3`, khớp `results/cnn_v5/evaluation.json`.
- Training lưu best checkpoint tại `python/train_evaluate_cnn_v5.py:76-85`, sau đó load lại tại dòng 112.
- Threshold 0.33 được chọn lại trên chính checkpoint đã load tại dòng 113-114.
- Test evaluator load đúng `models/v5/ecg_cnn_v5_best.keras` và dùng 0.33 cho cả MIT-BIH/INCART tại `python/final_evaluate_cnn_v5.py:40-50,61,67`.
- V4 dùng checkpoint riêng và threshold 0.88 trong các artifact so sánh.

Kết luận: không phát hiện nhầm checkpoint hoặc threshold.

## 4. Bằng chứng dịch phân bố dự đoán

| Dataset/split | Actual V | Predicted V V5 | Tỷ lệ actual V | Tỷ lệ predicted V | FP |
| --- | ---: | ---: | ---: | ---: | ---: |
| INCART Validation | 3.094 | 3.096 | 12,37% | 12,38% | 6 |
| INCART Test | 3.332 | 6.408 | 12,61% | 24,26% | 3.163 |
| MIT-BIH Validation | 1.300 | 1.266 | 10,43% | 10,16% | 26 |
| MIT-BIH Test | 905 | 2.564 | 8,02% | 22,73% | 1.699 |

Prevalence INCART Validation/Test gần như giống nhau, nhưng V5 tăng gấp 1,96 lần số prediction PVC trên Test. Do đó class-prior shift không giải thích 3.163 FP. MIT-BIH có giảm prevalence V ở Test, nhưng prediction PVC vẫn tăng hơn hai lần; đây cũng là score/morphology distribution shift.

V4 ổn định hơn trên INCART:

- Validation: predicted V 3.007, actual V 3.094, FP 131.
- Test: predicted V 2.997, actual V 3.332, FP 403.

V5 tăng recall bằng cách đẩy nhiều Normal qua threshold, trong khi V4 không có hiện tượng tăng predicted-positive tương tự.

## 5. Vì sao Validation V5 quá lạc quan

### Đã xác minh

1. Chỉ INCART Validation gồm 5 patient được dùng ở cuối mỗi epoch để quét 91 threshold từ 0.05 đến 0.95 (`python/train_evaluate_cnn_v5.py:66-85`).
2. Cùng Validation quyết định checkpoint, early stopping và threshold cuối (`python/train_evaluate_cnn_v5.py:109-114`).
3. Có 25.010 beat nhưng chỉ 5 đơn vị patient độc lập. Beat count lớn không thay thế số patient độc lập.
4. MIT-BIH Validation không chọn checkpoint/threshold, nhưng được dùng trong quyết định “worth testing” tại dòng 122-138; nó cũng không còn là đánh giá độc lập mới.

Đây không phải data leakage Train→Validation, nhưng là **adaptive overfitting vào Validation** và làm 99,84% F1 trở nên lạc quan.

### Giả thuyết có cơ sở, chưa chứng minh

- V5 crop 128 mẫu trung tâm rồi Flatten tại `python/train_evaluate_cnn_v5.py:30-40`. Flatten giữ vị trí tuyệt đối và có thể học morphology/alignment đặc thù patient hoặc record.
- V4 dùng GlobalAveragePooling tại `python/train_evaluate_cnn_v4.py:26-36`, có inductive bias ít phụ thuộc vị trí hơn.
- Nhánh multi-scale V5 có 4.585 tham số so với 849 của V4. Dung lượng lớn hơn cộng với chỉ 5 patient Validation có thể làm mô hình/threshold đặc thù cohort.

Chưa có activation/ablation hoặc phân nhóm morphology để khẳng định nhánh nào gây FP.

## 6. False Positive theo record

Artifact hiện tại **không đủ để phân bổ 3.163 FP theo record**:

- `python/final_evaluate_cnn_v5.py:48-50` tạo `scores_inc`.
- Dòng 66-67 chỉ tổng hợp toàn Test bằng `metrics()`.
- `results/cnn_v5/final_evaluation/evaluation.json` không lưu score, prediction, `record_ids` hoặc thống kê từng record.
- Dataset vẫn có `record_ids`, `patient_ids` và `centers_250hz`, nên có thể chẩn đoán nếu chạy lại inference cố định.

Không thể kết luận record I18–I71 nào đóng góp nhiều FP từ artifact hiện có. Đặc biệt không được tự quy 3.163 FP cho patient 30 hay record cụ thể chỉ dựa trên V4 per-patient result.

## 7. Nguyên nhân theo mức độ bằng chứng

### Đã xác minh

1. V5 bị predicted-positive/score distribution shift mạnh trên cả hai Test.
2. INCART không có patient overlap; MIT-BIH không có beat/record overlap.
3. Threshold/checkpoint/preprocessing/label mapping được dùng đúng.
4. Checkpoint và threshold được tối ưu thích nghi nhiều lần trên chỉ 5 INCART Validation patients.
5. V4 ổn định hơn V5 trên INCART Test; chênh lệch không đến từ class weights vì V4/V5 dùng cùng Train và cùng công thức weight.

### Chưa đủ dữ liệu để kết luận

1. FP tập trung ở record/patient nào.
2. FP do QRS type, nhịp lân cận, lệch center, biên độ hay noise nào.
3. Nhánh central Flatten hay nhánh context là nguyên nhân chính.
4. MIT-BIH có hidden patient overlap ngoài cặp 201/202 hay không.

## 8. Hướng khắc phục ưu tiên

1. **Chẩn đoán cố định theo record trước khi sửa model.** Không tuning: chạy lại V4/V5 tại threshold 0.88/0.33, lưu `{dataset, split, patient, record, center, y, score, prediction}` và thống kê FP/FN theo record/patient, score quantile, khoảng cách tới threshold.
2. Phân tích morphology của FP bằng metadata có sẵn: central offset, peak polarity, amplitude trước z-score, PVC lân cận và annotation OTHER gần cửa sổ. Không đổi nhãn hoặc threshold.
3. Xác minh patient mapping MIT-BIH từ nguồn chính thức trước bất kỳ split mới nào.
4. Với model tương lai, tách một development cohort patient-level đủ lớn; không dùng cùng 5 patient để đồng thời chọn epoch, architecture và threshold. Dùng nested/grouped validation hoặc khóa threshold trên calibration subset riêng.
5. Chỉ sau chẩn đoán mới cân nhắc giảm phụ thuộc vị trí của Flatten, regularization hoặc augmentation alignment. Không sửa architecture theo Test hiện tại.

## Kế hoạch cần phê duyệt nếu muốn hoàn tất phân tích FP

- Tạo script read-only inference chẩn đoán mới; không ghi đè kết quả cũ.
- Chạy đúng một lần V4/V5 trên MIT-BIH và INCART Validation/Test với checkpoint/threshold đã khóa.
- Lưu output mới dưới `results/cnn_v5/precision_drop_diagnostic/`.
- Sinh bảng per-record/per-patient và danh sách FP đại diện; không sweep threshold, không train và không thay preprocessing.

Kế hoạch trên là bước cần thiết để trả lời định lượng phần 3.163 FP theo record. Chưa thực hiện trong lần rà soát này.
