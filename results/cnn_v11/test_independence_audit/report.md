# Audit tính độc lập Test V11

Phạm vi: kiểm tra chỉ đọc Git, source, cấu hình, split metadata và artifact hiện có. Không training, inference, chạy Test hay chỉnh model/code. Thời gian dưới đây là UTC+07 từ LastWriteTime của filesystem, chỉ là bằng chứng thứ tự artifact, không phải timestamp thực thi được ký hoặc chứng thực.

## Kết luận

Không tìm thấy bằng chứng mẫu MIT-BIH/INCART Test được dùng để fit, chọn checkpoint, tính thống kê RR hay calibration threshold V11. Code và giao index/group hiện tại hỗ trợ kết luận này. Tuy nhiên không thể chứng minh đầy đủ nguồn gốc mọi lần chạy chỉ từ source chưa được version-control.

Có bằng chứng rõ Test feedback ảnh hưởng gián tiếp tới dòng kiến trúc dẫn đến V11: phân tích lỗi Test V5 đề xuất pooling thay Flatten và augmentation; V6 thực hiện hướng đó; V11 kế thừa V6. Vì vậy không được gọi Test V11 là đánh giá độc lập cuối cùng. Cách gọi phù hợp: “retrospective evaluation on previously inspected held-out records/patients, with final checkpoint and threshold frozen before V11 inference”.

## 1. Git và khả năng truy nguyên

Git HEAD `3d85e1d`, 2026-11-07 12:05 +07: “Complete AI LIVE and bench LED buzzer feedback”. Hai commit trước: `31509f5` (09:40:05, “Complete AIoT research backup”), `0f0c204` (09:29:36, “Initial backup ESP32 ECG TinyML”).

`git log --all --` cho script V6/V11 không có commit. `git status --short` xác nhận models/v4–v9, models/v11, script training/evaluation tương ứng và results tương ứng là **untracked**. Không có commit cụ thể cho các thí nghiệm V4–V11. Không được gán chúng cho HEAD hoặc coi Git đã chứng thực thứ tự phát triển. Không có lịch sử sửa từng phiên bản source để loại trừ việc thay đổi sau chạy.

## 2. Timeline artifact

Mọi đường dẫn tương đối từ root repository. Commit cho các dòng dưới: **không có; untracked**.

| Thời điểm +07 | Sự kiện/bằng chứng | Đường dẫn |
|---|---|---|
| 2026-11-15 23:27:04 | V4 INCART Test và lock | `results/cnn_v4/test_evaluation.json`, `test_evaluation.lock.json` |
| 2026-11-16 00:35:00 | V5 Test hai dataset; V4 INCART tái sử dụng, V4 MIT còn null | `results/cnn_v5/final_evaluation/evaluation.json`; `python/final_evaluate_cnn_v5.py:39–67` |
| 01:09:29 | Fixed diagnostic V4/V5 trên hai Test, bao gồm V4 MIT-BIH | `results/cnn_v5/precision_drop_diagnostic/summary.json`, `beat_predictions.csv` |
| 01:11:56 | Phân tích Test và đề xuất thiết kế V6 | `results/cnn_v5/precision_drop_diagnostic/report.md:16–36` |
| 01:34:03 | V6 Development, chọn pooling candidate/checkpoint/threshold | `results/cnn_v6/evaluation.json`; `python/train_evaluate_cnn_v6.py` |
| 01:56:22 | V6 Test hai dataset; V4/V5 chỉ đọc artifact | `results/cnn_v6/main_dataset_comparison/evaluation.json`, `evaluation.lock.json`; `python/evaluate_v6_main_tests_once.py` |
| 02:29:16 | V8 config ghi DESIGN_LOCKED_BEFORE_V7_TEST | `results/cnn_v8/config.json:3–6` |
| 02:30:04 | V7 Test hai dataset | `results/cnn_v7/final_test/evaluation.json`, `evaluation.lock.json`; `python/evaluate_v7_tests_once.py:51–55` |
| 02:49:55 | V8 Test hai dataset, tái sử dụng V4–V7 | `results/cnn_v8/final_test/evaluation.json`; `python/evaluate_v8_tests_once.py:61–105` |
| 03:10:23 | V9 A/B chọn theo Development, không Test mới | `results/cnn_v9/evaluation.json`, `config.json`; `python/train_evaluate_cnn_v9.py:197–221` |
| 04:11:41 | 5-fold grouped CV V4/V6 trên Train+Validation | `results/v10_research/step1_5fold_cv/cv_evaluation.json`, `folds_split.json` |
| Trước 05:07:20 | V10-A/B/C, so sánh thích nghi dựa trên outer đã xem | `results/v10_research/step2/`, `step3_consistent_runtime/`, `step4_hybrid/` |
| 05:28:53 | V11 RR 5-fold CV hoàn tất | `results/cnn_v11/evaluation.json`; `python/run_v11_rr.py` |
| Sau CV, trước final fit | RR detector và detector-window Development | `results/cnn_v11/rr_detector_validation/`, `end_to_end_detector/` |
| 05:58:42 | Final V11 lock, threshold 0.80, best epoch 5/10 | `results/cnn_v11/final_test/locked.json` |
| 05:59:02 | Final V11 offline và detector Test hoàn tất | `results/cnn_v11/final_test/evaluation.json`, per-record score files |

Không xác định chính xác giây bắt đầu/kết thúc từng dataset. Các marker “one run”, lock và mtime không tự chứng minh chưa từng có chạy ngoài script. V4 MIT-BIH Test sớm nhất **tìm được** là diagnostic 01:09:29; V4 final V5 artifact ban đầu ghi rõ chưa có kết quả đó.

## 3. Evidence: Test feedback và lý do chọn V6

**Ảnh hưởng gián tiếp có bằng chứng:**

- `results/cnn_v5/precision_drop_diagnostic/report.md:16–27` phân tích sâu Test patient 30, I70/I71 và MIT record 108: phân bố FP, biên độ, polarity, lệch tâm, score tự tin sai.
- Cùng báo cáo `:31–36` liên hệ position-aware Crop+Flatten và morphology, rồi đề xuất V6 với pooling/aggregation, shift/amplitude/polarity robustness và development nhóm riêng. Đây là một đường feedback cụ thể từ Test đến đề xuất mô hình; không chỉ là “đã xem bảng Test”.
- `python/train_evaluate_cnn_v6.py` thực hiện `build_pooling_v6`, ablation Flatten/pooling và augmentation. Chọn pooling variant bằng checkpoint PR-AUC; threshold bằng calibration F1. Cơ chế chọn run dùng Development không xóa ảnh hưởng Test ở giai đoạn hình thành ý tưởng.
- V11 `python/run_v11_rr.py:76–80` dùng `build_v6_baseline()`, thêm RR Dense(8) và đầu ra mới. V11 vì vậy kế thừa dòng phát triển đã có feedback Test.

**Chọn lại V6 có bằng chứng Development/CV:** `results/v10_research/step1_5fold_cv/report.md:12–24` cho thấy V6 F1/PR-AUC tốt hơn V4; V10-A/B/C không cải thiện ổn định. Điều này hỗ trợ việc dùng V6 làm baseline trực tiếp cho V11. Không tìm thấy rule source kiểu “chọn V6 nếu Test F1 cao nhất”. Không thể suy ra rằng mọi quyết định lựa chọn V6 chỉ dựa trên Test.

**Bổ sung RR:** source/config V11 thể hiện RR nhân quả, thống kê từ Fit, và phân chia checkpoint/calibration/outer. Không tìm thấy bằng chứng artifact cụ thể rằng một record Test hoặc score Test được dùng để chọn 4 đặc trưng RR, số neuron RR hay threshold 0.80. Nhưng không có preregistration/commit trước exposure Test để chứng minh ý tưởng RR hoàn toàn không bị ảnh hưởng. Cần phân biệt “không thấy bằng chứng ảnh hưởng trực tiếp” với “đã chứng minh độc lập”.

V7/V8 có lock và quy định không Test khi chọn run; V8 config trước mtime V7 Test hỗ trợ riêng việc khóa thiết kế V8 trước V7 Test. Nó không phục hồi tính độc lập đối với Test V4/V5/V6 đã được xem. V9–V11 không có Test mới trong CV, nhưng đã dùng các Development/outer kết quả nhiều lần để quyết định biến thể; outer CV đó cũng là đánh giá thích nghi, không phải nested estimate hoàn toàn chưa nhìn.

## 4. Audit direct leakage V11

`python/run_v11_rr.py:30–31` chỉ chọn `train_indices + validation_indices` và INCART split Train/Validation. `:16–24` dùng current/history RR; không dùng RR tương lai hoặc nhãn trước làm feature. Symbols dùng lọc vị trí beat và chọn target N/V; annotation timing vẫn là thông tin oracle trong nhánh offline.

Final training `python/finalize_test_v11.py:19–31`:

- gọi loader Train+Development; group Checkpoint/Calibration lấy từ V6 config;
- Fit là phần bù **bên trong pool Train+Development**, không phải toàn dataset;
- mean/std RR và class weights chỉ Fit;
- callback checkpoint dùng Checkpoint, threshold F1 dùng Calibration;
- `:93 test(train())` hoàn tất train/lock rồi mới gọi Test; `:40` chọn Test arrays.

Kiểm tra metadata đọc tại thời điểm audit, không inference:

| Kiểm tra | Kết quả |
|---|---|
| MIT Train index ∩ Test index | 0 |
| MIT Validation index ∩ Test index | 0 |
| MIT Test records ∩ locked Fit/Checkpoint/Calibration records | rỗng |
| INCART Test patients ∩ locked Fit/Checkpoint/Calibration patients | rỗng |
| INCART Test records ∩ Train/Validation records | rỗng |

MIT Test records: 107,108,113,117,123,200,222. INCART Test patients: 9,10,17,27,30. MIT index counts Train=58,134; Validation=12,459; Test=11,279. MIT grouping là record, không đủ để tự tuyên bố patient-disjoint; không xác minh patient identity ngoài metadata đã có trong audit này.

NPZ có thể chứa chung cả ba split; việc mở file chung hoặc đọc split metadata để kiểm tra không đồng nghĩa training dùng Test. Evidence quan trọng là index/group thực sự cấp cho Fit/Checkpoint/Calibration. Không phát hiện đường Test vào các phép tính đó trong source hiện tại. Chưa kiểm tra waveform trùng lặp xuyên record/patient, provenance của mọi file trước khi được tạo, hoặc mọi lệnh tương tác lịch sử.

Final SHA-256 khóa: `61909ec7f93e3d8823627a0127422aefdd098f92a9c95619073968c7a3eb3601`. Metadata `test_accessed_before_lock=false` là khai báo của script, không phải attestation độc lập. Các mtime lock 05:58:42 và evaluation 05:59:02 phù hợp trình tự source, nhưng file untracked có thể sửa/copy.

## 5. Cách trình bày trong bài báo và việc cần bổ sung

1. Công bố chuỗi phát triển, số biến thể V4–V11, việc phân tích Test V5, và gọi Test hiện tại là **held-out hồi cứu đã bị exposure trong phát triển**, không phải confirmatory independent final Test.
2. Đóng băng toàn bộ pipeline trước một cohort mới: CNN hash, threshold 0.80, RR features/scaling, detector, windowing, quality gate, missing-RR/fallback, matching tolerance và định nghĩa FP/FN/abstention. Offline annotation-RR và detector end-to-end phải báo riêng.
3. Dùng cohort bệnh nhân chưa từng dùng để fit, chọn model/threshold, định hướng kiến trúc hay phân tích lỗi; xác minh patient overlap/duplicate và khác nguồn nếu có. Không chỉ đổi tên hoặc chia lại Test đã xem.
4. Lưu preregistered protocol, commit/tag source, manifest/hash dataset/split, runtime và log thực thi có timestamp; đánh giá một lần sau lock. Tham số không được chọn từ cohort xác nhận.
5. Nếu chưa có cohort mới: có thể báo exploratory retrospective results và giới hạn rõ ràng; không có thủ tục thống kê hay lock bổ sung nào biến lại các Test đã exposure thành Test độc lập. Nested CV mới chỉ hỗ trợ validation nội bộ nếu toàn bộ lựa chọn được lồng đúng, không xóa lịch sử exposure.

**Tóm tắt bốn mức bằng chứng:** direct leakage vào V11 train/calibration: không tìm thấy, index/group checks hỗ trợ không có; indirect Test feedback: có, V5 Test diagnostic → đề xuất V6 → V11; V7/V8 Test ảnh hưởng cụ thể RR/threshold V11: chưa tìm được evidence riêng; toàn bộ lịch sử execution/ý tưởng: không thể xác minh vì source/artifact untracked, thiếu log và preregistration.
