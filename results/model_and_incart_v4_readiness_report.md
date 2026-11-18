# Kiểm tra model hiện hành và chuẩn bị INCART cho V4

Ngày kiểm tra: 2026-11-15. Phạm vi là mã nguồn và artifact thực tế trong workspace. Không train model, không chạy Test inference, không sửa firmware/GUI và không flash ESP32.

## 1. Model đang được firmware ESP32 sử dụng

Firmware tích hợp nhúng trực tiếp `main/model/ecg_cnn_int8.tflite` bằng `EMBED_FILES`. `model.cpp` kiểm tra kích thước, SHA-256, tensor INT8 và dùng threshold 0,52 trước khi khởi tạo interpreter.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `models/ecg_cnn_int8.tflite` | 8.560 | `38705f5399ada9b87f466725608a053ae2305295a8a3cae7bda01f4928f4a394` |
| `firmware/esp32_tinyml_step8/main/model/ecg_cnn_int8.tflite` | 8.560 | cùng hash |
| `firmware/esp32_ecg_tinyml_integrated/main/model/ecg_cnn_int8.tflite` | 8.560 | cùng hash |

TFLite nhúng có chuỗi operator `Conv/Pool/Conv/Pool/MEAN/FullyConnected/FullyConnected/Logistic`, đúng kiến trúc V1 dùng GlobalAveragePooling. Resolver firmware đăng ký `MEAN` và không đăng ký `STRIDED_SLICE`, `SHAPE`, `PACK` mà V3 cần.

**Kết luận:** ESP32 vẫn dùng V1 INT8. Không có bằng chứng V3 đã thay V1. Ngược lại, hash, operator graph, resolver và kiểm tra `kModelSha` đều chứng minh V1 đang là model build-time. V3 không có file INT8 và không tương thích resolver hiện tại nếu chỉ thay binary.

Lưu ý: kết luận này xác định source/build input hiện hành. Không đọc flash của board trong nhiệm vụ này; board chỉ chắc chắn chạy đúng binary này sau một lần build/flash được xác minh riêng.

## 2. Inventory V1, V2 và V3

### V1

- Checkpoint: `models/ecg_cnn_best.keras` (48.247 B, SHA-256 `254595d658838de6525f4dc0a2821415a9197443e529d838e362044cd2e32399`) và `models/ecg_cnn_final.keras` (48.002 B).
- TFLite Float32: `models/ecg_cnn_float32.tflite` (9.424 B). TFLite INT8: `models/ecg_cnn_int8.tflite` (8.560 B).
- Kiến trúc trực tiếp từ Keras: Conv1D 8×5 → Pool2 → Conv1D 16×5 → Pool2 → GlobalAveragePooling → Dense8 → Dense1 sigmoid; 849 tham số; input `(256,1)`.
- Dataset: MIT-BIH N/V 250 Hz, 81.872 cửa sổ. Train 58.134, Validation 12.459, Test 11.279. Chỉ chọn MLII; resample 360→250 bằng 25/36; cửa sổ 128 mẫu trước và 128 mẫu từ annotation; z-score theo từng cửa sổ.
- Train: seed 42, Adam 0,001, batch 64, class weight từ Train, tối đa 30 epoch, early stopping patience 5 theo validation loss; best epoch 15.
- Threshold triển khai: 0,52. Trên Validation CNN-only tại 0,52: Precision PVC 70,5669%, Recall 90,0000%, F1 79,1075%, FP 488, FN 130. Historical Phase 2B end-to-end INT8 trên cùng Validation: Precision 71,7610%, Recall 87,7018%, F1 78,9346%.

### V2

- Checkpoint riêng: `models/v2/ecg_cnn_v2_best.keras` (47.482 B, SHA-256 `e609077580bf396f9775e7491a1cf3815e31f671d44278a609494e86a13e2036`). Không có TFLite/INT8 V2.
- Kiến trúc V1 giữ nguyên, 849 tham số. Fresh weights, không nạp weights V1.
- Dùng duy nhất original MIT-BIH Train. Fit 52.927 beat; development 5.207 beat theo record group. 1.225 hard-negative N trong fit được lặp tổng cộng 4 lần/epoch; seed 42; class weight; early stopping patience 5 theo development F1 tại 0,52; best epoch 15/20.
- Development tại 0,52: Precision 98,8113%, Recall 99,8498%, F1 99,3279%, FP 8, FN 1. V1 đã từng học toàn bộ development này nên so sánh V1/V2 tại đây không độc lập.
- Historical Validation exploratory: CNN-only Precision 56,9309%, Recall 96,1629%, F1 71,5201%; end-to-end Precision 56,2529%, Recall 94,3889%, F1 70,4937%.
- Threshold review chọn 0,53 trên development, F1 99,4764%; không vượt V1 theo quyết định triển khai. `KEEP_V1`, không export INT8.

### V3

- Checkpoint riêng: `models/v3/ecg_cnn_v3_best.keras` (68.350 B, SHA-256 `788cd415a6ef5deb2a7015a6314284e6effd79617115f0971058d8679d413260`). Float TFLite: `models/v3/ecg_cnn_v3_float32.tflite` (17.112 B). Không có INT8 V3.
- Kiến trúc trực tiếp từ Keras: crop mẫu 96:160 → Conv1D 8×5 → Pool2 → Conv1D 16×5 → Pool2 → Flatten208 → Dense8 → Dense1 sigmoid; 2.385 tham số.
- Cùng fit/development của V2 nhưng mỗi fit sample xuất hiện đúng một lần/epoch, không hard-negative oversampling; seed 42; class weight; early stopping patience 5 theo development F1 tại 0,52; best epoch 6/11.
- Development CNN-only tại 0,52: Precision 100%, Recall 99,3994%, F1 99,6988%, FP 0, FN 4. End-to-end trên đúng sáu development record: Precision 76,5700%, Recall 95,1952%, F1 84,8728%; 193 predicted PVC không match annotation.
- V3 không vượt tiêu chí chọn đã đóng băng; `int8_export_selected=false`. Kết quả development đã được dùng cho V2/V3 và V1 từng học các record này, nên không phải đánh giá tổng quát hóa độc lập.

## 3. INCART: tính đầy đủ và khả năng đọc

Nguồn hợp lệ hiện tại là `files/`; không cần sao chép gần 1 GB sang `data/incartdb/`. `.old-headers/` chỉ chứa header cũ và không được truyền vào WFDB.

- `RECORDS` liệt kê đúng 75 record I01–I75.
- 75/75 record có đủ `.dat`, `.hea`, `.atr`.
- 230/230 entry trong `SHA256SUMS.txt` khớp; không có checksum lỗi.
- WFDB 4.3.1 đọc được header, annotation, signal probe và toàn bộ lead II của 75/75 record; không có NaN/Inf hay lỗi shape.
- Header hiện hành cho biết 32 patient. Mỗi record dài 462.600 mẫu ở 257 Hz, 12 chuyển đạo: I, II, III, AVR, AVL, AVF, V1–V6. Lead II luôn ở index 1.
- Tổng annotation: N 150.410, V 20.013, OTHER 5.496. OTHER gồm `A=1.944`, `R=3.174`, `F=219`, `j=92`, `n=32`, `S=16`, `+=12`, `Q=6`, `B=1`. Không nhãn nào trong nhóm này được đổi thành N.

Lead II là limb lead II chuẩn; MLII của MIT-BIH là modified lead II. Cùng hướng II không làm chúng tương đương về vị trí điện cực, morphology, gain hoặc nhiễu. Z-score giảm khác biệt offset/gain nhưng không loại domain shift hình thái.

Kiểm tra căn annotation trên 170.384 beat N/V dùng cực trị tuyệt đối cục bộ của lead II trong ±100 ms, so với median ±250 ms: median offset 0 mẫu; percentile 95 của |offset| là 6 mẫu tại 257 Hz, tương đương 23,35 ms. Chưa có bằng chứng cần dịch toàn bộ annotation. Đây chỉ là screening; extraction V4 vẫn phải kiểm tra cửa sổ theo morphology/label và không tự sửa annotation.

## 4. N/V/OTHER theo patient và split cố định đề xuất

| Patient | Records | N | V | OTHER | Split |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | I01,I02 | 4.858 | 573 | 0 | Train |
| 2 | I03,I04,I05 | 6.115 | 493 | 44 | Train |
| 3 | I06,I07 | 5.076 | 10 | 113 | Train |
| 4 | I08 | 1.777 | 351 | 3 | Validation |
| 5 | I09,I10,I11 | 8.625 | 128 | 32 | Train |
| 6 | I12,I13,I14 | 6.395 | 300 | 3 | Train |
| 7 | I15 | 2.632 | 3 | 0 | Train |
| 8 | I16,I17 | 0 | 29 | 3.166 | Train |
| 9 | I18,I19 | 3.874 | 1.216 | 57 | Test |
| 10 | I20,I21,I22 | 7.249 | 304 | 409 | Test |
| 11 | I23,I24 | 4.757 | 19 | 0 | Train |
| 12 | I25,I26 | 3.203 | 9 | 9 | Train |
| 13 | I27,I28 | 3.598 | 724 | 0 | Train |
| 14 | I29,I30,I31,I32 | 6.949 | 2.961 | 2 | Train |
| 15 | I33,I34 | 2.674 | 1 | 1.127 | Validation |
| 16 | I35,I36,I37 | 8.658 | 1.360 | 30 | Train |
| 17 | I38,I39 | 3.615 | 858 | 1 | Test |
| 18 | I40,I41 | 4.192 | 93 | 11 | Train |
| 19 | I42,I43 | 2.633 | 2.674 | 11 | Train |
| 20 | I44,I45,I46 | 5.472 | 1.597 | 12 | Validation |
| 21 | I47,I48 | 3.978 | 328 | 4 | Train |
| 22 | I49,I50 | 5.114 | 31 | 2 | Train |
| 23 | I51,I52,I53 | 4.731 | 2.051 | 4 | Train |
| 24 | I54,I55,I56 | 6.160 | 46 | 28 | Train |
| 25 | I57,I58 | 5.155 | 33 | 8 | Validation |
| 26 | I59,I60,I61 | 5.903 | 81 | 93 | Train |
| 27 | I62,I63,I64 | 5.187 | 956 | 33 | Test |
| 28 | I65,I66,I67 | 6.850 | 1.113 | 16 | Validation |
| 29 | I68,I69 | 4.481 | 328 | 6 | Train |
| 30 | I70,I71 | 3.167 | 0 | 177 | Test |
| 31 | I72,I73 | 3.766 | 456 | 40 | Train |
| 32 | I74,I75 | 3.566 | 887 | 55 | Train |

Split dùng seed 42 và 100.000 permutation patient, chỉ tối ưu cân bằng số N/V/OTHER; không dùng waveform hoặc output model. Không có patient overlap.

| Split | Patients | Records | N | V | OTHER |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 22 | 52 | 105.390 | 13.584 | 3.653 |
| Validation | 5 | 11 | 21.928 | 3.095 | 1.166 |
| Test | 5 | 12 | 23.092 | 3.334 | 677 |

Test patient cố định: 9, 10, 17, 27, 30. Việc audit đã đọc metadata, label count và signal probe để kiểm tra integrity; chưa chạy V1/V2/V3 hay dùng performance Test để chọn kiến trúc/threshold.

## 5. Contract chuẩn bị V4

1. Chỉ dùng N→0 và V→1; loại OTHER trước extraction.
2. INCART dùng lead `II`; MIT-BIH giữ MLII. Lưu `database`, `patient_id`, `record_id`, lead và sample center cho từng beat.
3. INCART resample 257→250 bằng `scipy.signal.resample_poly(up=250, down=257)`. Map annotation bằng round-half-up `floor(sample*250/257 + 0,5)`, sau đó kiểm tra biên trên chính chiều dài signal đã resample.
4. Cắt 256 mẫu `[center-128:center+128]`; z-score từng cửa sổ với epsilon/finite guard giống V1.
5. Fit V4 chỉ dùng MIT-BIH Train hiện hành cộng INCART Train. Không đưa MIT-BIH Validation/Test cũ hoặc INCART Validation/Test vào fit.
6. Chọn checkpoint/threshold chỉ trên development đã định trước. INCART Validation là patient-disjoint; threshold không được chọn trên INCART Test.
7. So sánh V1 và V4 cuối cùng trên cùng sealed INCART Test bằng CNN-only. Nếu đánh giá end-to-end, phải dùng cùng detector/matching/tolerance và báo riêng nhịp bỏ trước CNN. Không trộn CNN-only F1 với end-to-end F1.

## 6. Trạng thái sẵn sàng

**Dataset đã đủ và đọc được; split patient-disjoint đã được cố định. Chưa nên bấm train V4 ngay.** Các bước tối thiểu còn thiếu:

- Viết extractor INCART theo contract trên và kiểm tra count sau boundary/finite filtering, không chỉ count annotation.
- Kiểm tra trực quan/định lượng riêng N và V sau resample; screening hiện tại không chứng minh mọi morphology được center đúng.
- Xác minh preprocessing parity với V1 trên fixture và lưu provenance/hash của dataset V4.
- Đóng băng kiến trúc V4, seed, sampling/class weight và tiêu chí checkpoint trước lần train đầu tiên.
- Niêm phong danh sách INCART Test; không chạy dự đoán cho đến khi model và threshold đã khóa.

Không tạo `data/incartdb/` vì `files/` đã là WFDB root hoàn chỉnh; sao chép sẽ chỉ tạo bản dữ liệu trùng lặp. Metadata máy đọc nằm trong `results/incart_v4_preparation.json`, split cố định nằm trong `data/processed/incart_patient_split_v4.json`.
