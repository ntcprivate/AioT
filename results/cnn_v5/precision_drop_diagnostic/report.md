# Fixed diagnostic V4/V5 — Precision drop

Phạm vi: inference đúng một lần trên MIT-BIH Test và INCART Test, checkpoint/threshold khóa (`V4=0.88`, `V5=0.33`). Không train, sweep threshold hay tuning trên Test.

## Kết quả tổng

| Dataset / model | Precision | Recall | F1 | FP | FN |
|---|---:|---:|---:|---:|---:|
| MIT-BIH V4 | 69.82% | 89.72% | 78.53% | 351 | 93 |
| MIT-BIH V5 | 33.74% | 95.58% | 49.87% | 1,699 | 40 |
| INCART V4 | 86.55% | 77.85% | 81.97% | 403 | 738 |
| INCART V5 | 50.64% | 97.39% | 66.63% | 3,163 | 87 |

## Bằng chứng theo record/patient

- INCART patient 30, records I70/I71, tạo 3,153/3,163 FP V5 (99.68%). I70: 1,529/1,539 N thành FP; I71: 1,624/1,625 N thành FP. Cả hai record không có nhịp V trong tập N/V Test.
- MIT-BIH record 108 tạo 1,642/1,699 FP V5 (96.65%), tương đương 94.48% các nhịp N của record.
- Ba record đứng đầu tạo 99.81% FP INCART; ba record đứng đầu tạo 99.88% FP MIT-BIH. Đây là lỗi domain/patient-specific, không phải tăng FP đồng đều.
- 2,832/3,163 FP INCART và 1,381/1,699 FP MIT-BIH là FP mới của V5 trong khi V4 dự đoán đúng N.

## Morphology và nhịp lân cận

- INCART patient 30 N có biên độ QRS thấp hơn development: median `peak_abs=4.519`, `ptp=5.193`; INCART Train N là `5.316/7.318`, Validation N là `6.918/8.382`. Median absolute center offset là 3 mẫu (p90=7), so với Train 1/5 và Validation 1/2.
- MIT record 108 N có 34.98% QRS polarity âm; MIT Train N chỉ 1.19%, Validation N 0.07%. Median `peak_abs=4.135`, thấp hơn Train 6.006 và Validation 5.928; p90 absolute center offset là 9 mẫu, so với 1 mẫu ở Train/Validation.
- FP không được giải thích bởi PVC lân cận: chỉ 0.13% FP INCART và 3.00% FP MIT có V ngay trước/sau. I70/I71 là 0%. Vì vậy giả thuyết “PVC lân cận kéo nhãn N thành V” bị bác bỏ cho đợt suy giảm Test này.
- V5 rất tự tin sai: median score FP là 0.9503 trên INCART và 0.9984 trên MIT-BIH. I70/I71 có q10 score lần lượt 0.8100/0.8147. Đây không chỉ là vài mẫu sát threshold 0.33.
- FN còn lại tập trung hơn ở INCART patient 27 (54/87) và MIT record 200 (27/40). INCART FN có morphology gần TP hơn FP; MIT FN có tỷ lệ V lân cận cao hơn (52.5% so với TP 16.65%), nhưng n=40 nên chỉ là tín hiệu phụ.

## Nguyên nhân chính đã xác minh

V5 không tổng quát hóa với một số morphology N đặc thù patient/record: QRS biên độ thấp, center offset lớn hơn và/hoặc polarity hiếm trong development. Nhánh position-aware `Crop + Flatten`, số tham số lớn hơn và việc chọn checkpoint/threshold thích nghi trên chỉ 5 INCART Validation patients phù hợp với hiện tượng này, nhưng đóng góp riêng của từng yếu tố kiến trúc chưa được chứng minh bằng ablation. Threshold không phải lỗi triển khai; score sai nằm rất xa threshold.

## Tối đa hai hướng V6

1. Thiết kế development protocol patient-level rộng hơn, tách checkpoint-selection và calibration; dùng grouped/nested validation. Chỉ dùng Train/Development để chọn model/threshold, giữ Test hiện tại làm dữ liệu mô tả đã xem.
2. Trên development mới, thử một V6 duy nhất tăng bất biến polarity/biên độ/center-shift (augmentation có kiểm soát và thay `Flatten` position-sensitive bằng pooling/aggregation nhẹ). Đánh giá riêng các nhóm morphology hiếm trước khi khóa model; không tối ưu theo I70/I71 hoặc record 108.
