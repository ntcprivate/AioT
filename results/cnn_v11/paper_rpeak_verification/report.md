# Kiểm chứng số liệu R-peak mục 3.6

Kết luận cho claim TP=16772, FP=41, FN=66: **NOT VERIFIED**.
Không tìm thấy final.pdf hoặc r_peak_detector_improvement_report.md trong
workspace qua tìm tên file kể cả hidden/ignored (loại virtualenv/build). Vì vậy
chỉ đối chiếu được claim người dùng cung cấp, chưa đọc trực tiếp mục 3.6 hay
per-record table báo cáo gốc. Không có căn cứ gán nhãn CONSISTENT theo report
khi report chưa có.

## VERIFIED từ ECG/annotation gốc

Replay host g++ -O2, 7 record 115/118/121/210/214/233/234, MLII,
resample_poly 25/36, ADC clip(rint(2048+200*mV),0,4095), int16.
Annotation sample quy đổi integer round-half-up (sample*25+18)//36.
Không loại startup/end misses. Tổng reference beat=16838.
Hash .hea/.dat/.atr và source từng replay lưu trong evaluation.json.

| Source | Matching tolerance | TP | FP | FN | Sensitivity | PPV |
|---|---:|---:|---:|---:|---:|---:|
| Source V11 hiện tại, hold50 | ±12 samples (48 ms) | 16766 | 45 | 72 | 99.5724% | 99.7323% |
| Tái dựng hold58 từ source V11 | ±12 samples (48 ms) | 16770 | 41 | 68 | 99.5962% | 99.7561% |
| Source V11 hiện tại, hold50 | ±38 samples (152 ms) | 16781 | 30 | 57 | 99.6615% | 99.8215% |
| Tái dựng hold58 | ±38 samples (152 ms) | 16785 | 26 | 53 | 99.6852% | 99.8453% |

Bản hold58 **chỉ đổi literal 50→58** trong bản sao offline, không phải source
bài báo đã được xác thực. Kết quả này không chứng minh claim sai, nhưng không
tái lập claim. FP bằng 41 không đủ: TP/FN lệch 2 và số detected peaks là 16811
so với 16813 suy ra từ bài báo. Không tuning để khớp số.

| Record | TP hold58/tol12 | FP | FN |
|---|---:|---:|---:|
| 115 | 1950 | 0 | 3 |
| 118 | 2267 | 12 | 11 |
| 121 | 1848 | 17 | 15 |
| 210 | 2635 | 5 | 15 |
| 214 | 2253 | 4 | 9 |
| 233 | 3068 | 2 | 11 |
| 234 | 2749 | 1 | 4 |

## Phiên bản và matching

Source hiện tại main/signal.cpp:103–118: baseline alpha .025, envelope .01,
threshold max(30,2.5*envelope), refractory75, hold50, replacement >1.5 lần
candidate_strength. Pending FIFO/window giữ nguyên. V11 đã dùng source này
trong host replay, ungated peak stream; không phải complete safety-gated firmware.

tools/ecg_monitor/develop_r_peak_phase2b_confirmation.py và
debug/r_peak_phase2b/confirmation_plan.json lưu hold50, không hold58. Prototype
confirmation ban đầu còn thay peak khi chỉ mạnh hơn (>1.0), khác replacement1.5
trong current source. Vì thiếu source bài báo, chưa thể khẳng định các thông số
khác của phiên bản58 giống current source. Refractory75 được xác minh ở current
source; confirmation58 của bài báo chỉ là claim chưa được xác thực.

Matching lịch sử tools/ecg_monitor/validate_offline.py:24–33 và audit_r_peaks.py
dùng greedy one-to-one ±12 samples; V11 evaluations gần đây dùng ±38. Đây là
khác biệt thực sự quan trọng; không so sánh số liệu giữa hai tolerance mà không
ghi rõ. Replay mới dùng đúng greedy searchsorted hai ứng viên lân cận, không
dịch annotation hoặc chỉnh peak để tăng TP.

BEATS='NLRBAaJSVrFejnE/fQ?'. Mọi symbol trong tập này, kể cả OTHER ngoài N/V,
đều là reference beat. Marker nhịp/rhythm không thuộc BEATS không được tính
R-peak reference. OTHER được match thành TP, không mặc định FP. Mỗi detection
chỉ match tối đa một reference. Detection không match tính FP; reference không
match tính FN. Peak sai thời điểm ngoài tolerance có thể tạo cả FP và FN.
Replay có 0 center trùng chính xác cho cả 7 records, cả hai source.

## Mức độ xác minh và phần còn thiếu

- VERIFIED: các số replay trong bảng, từ dữ liệu gốc và source hash lưu kèm.
- CONSISTENT theo report: chưa thể đánh giá vì thiếu report/PDF gốc. Phép tính
  từ claim cho sensitivity 16772/16838=99.6080% và PPV 16772/16813=99.7561%,
  làm tròn đúng 99.61%/99.76%; đây chỉ là nhất quán số học.
- NOT VERIFIED: claim exact16772/41/66, phiên bản detector bài báo hold58 và
  matching cụ thể của bài báo.

Cần cung cấp final.pdf, báo cáo gốc và frozen source/config hoặc binary có hash
kèm command/runtime và per-record detections của thí nghiệm bài báo để giải
quyết chênh lệch. Không có CNN training, Final Test, tuning hoặc sửa firmware.
