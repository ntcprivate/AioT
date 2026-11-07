"""Render a short evidence-based review. No training, tuning, Test inference or firmware changes."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/final_ai_readiness'
def main():
    d=json.loads((OUT/'evidence.json').read_text());before=json.loads((OUT/'before_sha256.json').read_text())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    d['protected_checks']={p:sha(ROOT/p)==h for p,h in before.items()};assert all(d['protected_checks'].values())
    training=json.loads((ROOT/'results/cnn_metrics.json').read_text());conversion=json.loads((ROOT/'results/tinyml_conversion_report.json').read_text())
    assert sha(ROOT/'models/ecg_cnn_best.keras')==conversion['model_sha256']
    assert sha(ROOT/'data/processed/mitbih_nv_250hz.npz')==training['dataset_sha256']
    d['calibration_train_only']['indices_verified_train_only']=True
    import numpy as np
    with np.load(ROOT/'data/processed/mitbih_split_indices.npz') as split:
        assert np.isin(conversion['representative_dataset']['indices'],split['train_indices']).all()
        assert len(set(split['train_indices'])|set(split['validation_indices'])|set(split['test_indices']))==sum(len(split[k]) for k in ('train_indices','validation_indices','test_indices'))
    d['test_readiness']=dict(saved_test_records=d['split']['test']['records'],status='PREVIOUSLY_EXPOSED_NOT_A_NEW_BLIND_TEST',
        evidence=['results/cnn_metrics.json:evaluation','python/06_train_evaluate.py:219-225','results/data_leakage_audit.json:previous_test_exposure'],test_inference_performed_now=False)
    d['proposed_acceptance']=dict(status='DRAFT_REQUIRES_APPROVAL_BEFORE_INDEPENDENT_EVALUATION_NOT_RETROSPECTIVELY_GRADED',
        detector_existing=dict(per_record_sensitivity_min=.99,per_record_ppv_min=.99,p95_timing_max_ms=40,matching_samples=12,flat_50hz_false_peaks=0,queue_duplicate_overflow=0),
        classification_research_draft=dict(pvc_end_to_end_recall_min=.95,pvc_precision_min=.90,pvc_f1_min=.92,normal_end_to_end_recall_min=.99),
        requirements=['Agree N/V-only versus V/non-V/OOD policy first; include unmatched alarms and pre-CNN misses',
            'Freeze model/source/preprocessing/threshold and all exclusions before new independent patient data',
            'Report patient/record/class strata and95% patient-cluster uncertainty; predeclare minimum class counts and N/A behavior',
            'No pass claim on this reused Validation; no clinical performance claim from bench targets'])
    scripts=['final_ai_readiness_review.py','enrich_ai_readiness.py','readiness_float32_probe.py','write_final_ai_readiness_report.py']
    d['review_tool_sha256']={s:sha(ROOT/'tools/ecg_monitor'/s) for s in scripts}
    d['conclusion']=dict(confirmed_code_bug=False,production_code_modified=False,retraining='Recommend a separately authorized center-aware training/data-scope experiment; not performed or guaranteed to succeed',
        current_acceptance='FAIL detector121; classification not approved; no untouched Test established; hardware pending',ai_live='LOCKED')
    (OUT/'evidence.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
    table='\n'.join(f"|{r['record']}|{r['N']}|{r['V']}|{r['N_to_V']}|{r['V_to_N']}|{r['N_to_V_annotation_adc']} / {r['V_to_N_annotation_adc']}|" for r in d['per_record'])
    cf=d['counterfactual'];fl=d['same_window_float32_comparison']
    report=f'''# Rà soát cuối detector và CNN N/PVC — 2026-11-06

**Chưa đủ điều kiện AI-live; giữ LOCKED. Không phát hiện thêm lỗi triển khai
chắc chắn để sửa trong lượt này.** Không đổi firmware/model/threshold0,52,
không train, không chạy Test, không COM3/flash/reset hay GUI/telemetry.
Tái sử dụng trace/prediction2B; chỉ chạy inference chẩn đoán có đối chứng và
phân tích Train liên quan, không chạy lại bộ regression/build không liên quan.

## 1. Detector121:20FP/18FN là điểm yếu có tính hệ thống

Giữ TP1845/FP20/FN18, sensitivity99,0338%, **PPV98,9276%<99%:FAIL**.
Trace có sẵn:8FN không vượt ngưỡng,5 bị refractory chặn,2 warm-up,1 cuối cửa sổ,
2 liên quan confirmation/matching chưa xác định đầy đủ.14FP đứng trước reference
bị miss64..420ms;12 trong số đó cách<300ms. Khoảng xác nhận200ms có thể kết thúc
trước QRS thật rồi refractory300ms chặn nó; threshold/baseline và chọn fiducial
còn yếu. Không tự gọi tất cả là P/T sinh lý hoặc sửa tham số bằng các ca này.

Đối chứng **Train105/106/114/119/208/219**, cùng detector đã đóng băng:106FP,
90 gần một reference bị miss, **61FP đứng trước reference miss trong300ms**.
Mô-típ không riêng121; đây là cơ sở sửa phương pháp trên development riêng,
không phải lý do kéo dài hold/rút refractory để cứu Validation.
FIFO/ring/index/window và kernel đã có evidence2B; không thấy lỗi implementation
mới. Cần thiết kế detection/searchback/confirmation tốt hơn, rồi kiểm tra lại
các ca Train và tiêu chí cũ; chưa thực hiện thay đổi đó.

## 2.428N→PVC và136PVC→N: phần lớn là giới hạn mô hình/context

Các cửa sổ **đã match, hợp lệ** giữ confusion matrix `[[10673,428],[136,1141]]`
(hàng/column N,V). Không gộp miss trước CNN hay unmatched vào564 lỗi này.

|Record|N matched|V matched|N→V|V→N|Lỗi khi đặt center theo annotation: N→V / V→N|
|---|---:|---:|---:|---:|---|
{table}

**401/428 lỗi N→V ở233**. Record118 chỉ1/13 PVC được nhận đúng;214 có57/251
PVC→N,210 có45/187. Con số pooled che khác biệt giữa bệnh nhân/record.

Các phép đối chứng dùng **toàn bộ12378 matched N/V**, không chỉ chọn lỗi:

|Đối chứng|N→V|V→N|Ý nghĩa|
|---|---:|---:|---|
|Cửa sổ detectorADC gốc|428|136|Kết quả đang rà soát|
|ADC,center annotation chuẩn|435|135|15N+20V lỗi được sửa nhưng22N+19V mới sai|
|mV resampled,center annotation|436|134|ADC rounding không giải thích đa số lỗi|
|Float32 Keras,cùng cửa sổ detector|{fl['N']['float32_errors']}|{fl['V']['float32_errors']}|Không thể quy phần lớn lỗi cho INT8|

Mỗi đối chứng annotationADC/mV loại riêng1windowN do clipping (cùng một beat),
không tính nó là lỗiCNN hay đúng; các số lỗi trong bảng chỉ tính window hợp lệ.
Toàn bộ window detector matched ban đầu đều hợp lệ, nên428/136 không thay đổi.

{cf['N']['persistent_at_annotation_center']}/428 N và{cf['V']['persistent_at_annotation_center']}/136 V vẫn sai ở center annotation;
323N và25V sai dù center detector **đã trùng annotation**. Float32 vàINT8 cùng
sai **{fl['N']['both_wrong']} N +{fl['V']['both_wrong']} V**; chỉ5N+8V lỗi riêngINT8 (Float32 cũng có50N+4V lỗi riêng).
24.756 đối chứng annotationADC/mV đã so native vớiTF INT8: **0code khác**.
Preprocessing C++/Python khớp bytes,0NaN/Inf/clipping trong matched safe inputs;
không phát hiện sai nhãn0/1 hoặc off-by-one. Các phép đối chứng là phân tích,
**không phải thay center/preprocessing hoặc lựa chọn mô hình mới**.

Phân nhóm bằng chứng (liên hệ thống kê, không khẳng định nhân quả duy nhất):

- **402/428 N sai chứa PVC lân cận trong window256**. N có PVC lân cận:
 402/807 sai≈49,81%; không có:26/10294≈0,253%. Train chỉ1586/53216N≈2,98%
 có PVC lân cận, matched Validation807/11101≈7,27%: lệch phân phối context rõ.
 `GlobalAveragePooling1D` của CNN849parameter lấy đặc trưng toàn window, không
 có cơ chế buộc chú ý beat tạiindex128. Bằng chứng phù hợp với việc nhận
 **“có PVC trong cửa sổ” thay vì “beat giữa là PVC”**; chưa có attribution can
 thiệp nên không coi đó là giải thích duy nhất. Không phải nhãn center được
 ghi sai, cũng không được xóa các window khó để tăng precision.
- Median peak-to-peak **toàn cửa sổ** N sai762,5count soN đúng372; năng lượng
 ở vùng giữa≈33% so≈86%. PVC lân cận lớn có thể chi phối z-score/context;
 global amplitude đã được z-score loại, nên không kết luận chỉ cần đổi gain.
- V sai có proxy-width44ms soV đúng64ms/Train median72ms; median whole-window
 ptp472 so748count;43/136 có cực tính âm so811/1141 V đúng. Strongest peak
 median ở−368ms thay vì gầncenter: phù hợp beat lân cận che lấp PVC trung tâm.
 Proxy-width là số mẫu trên nửa residual trong±100ms, **không phải đo QRS width
 lâm sàng**; amplitude là ADC bench200count/mV, không hiệu chuẩn AD8232 thật.
- N sai:110score0,52..0,6;293score0,6..0,9;25score≥0,9. V sai:41score<0,1,
 65score0,1..0,4;30score0,4..0,52. Sai cả khi score rất chắc, không chỉ sát
 threshold. Score sigmoid không được chứng minh calibration; class weights
 Train N≈0,546/V≈5,910 cũng làm thay đổi ưu tiên loss, chưa phải xác suất lâm sàng.

**Có nên train lại? Có cơ sở nên mở một nhánh huấn luyện/so sánh riêng**, sau
khi chốt label-scope và kiểm tra dữ liệu: học target ở center, hard negatives N
gầnPVC, PVC hẹp/biên độ thấp, cân đối theo record và kiểm tra calibration bằng
Train/development nội bộ. Không chỉ huấn luyện lại cùng849parameter rồi kỳ vọng
tự hết lỗi; không sửa input256/crop/zero hàng xóm với model hiện tại. Bằng chứng
529/564 lỗi vẫn sai ở center chuẩn và551/564 cùng sai trongFloat32 cho thấy sửa
detector/kernel hoặc chuyểnFloat32 không đủ. **Chưa train hay thay weights**.

## 3. Tách đúng66N/24V trướcCNN và21 cảnh báo từ đỉnh giả

|Nguyên nhân quan sát trướcCNN|N|V|
|---|---:|---:|
|Detector không match|37|21|
|Admission2block +warm-up đầu|8|0|
|Safety reset/recovery/khác lịch sử|17|3|
|Clipping trực tiếp|1|0|
|Block cuối thiếu256|3|0|
|Tổng|66|24|

Không có block đầy đủ bị quality reject trong replay lý tưởng này; không suy
gate vô ích trên hardware. Có2 quantization abstention toàn stream (1N,1 nhãn
khác); no-peak issues ở121/210 và recovery tạo mất thêm window. CSV lưu90 ca;
nhãn recovery tổng hợp chưa tách mọi hiệu ứng history/confirmation, không đếm
chúng thành lỗiCNN. Policy preflight của host chỉ tương đương output policy,
không phải full RTOS/generation/scheduling simulation.

21 cảnh báoPVC unmatched:118=6,121=10,214=3,233=2; không thuộc428N→V.
Thêm **897 dự đoánPVC trên4352 matched beat ngoàiN/V** (763R,111L và23 loại
khác); chưa có policy binary cho chúng nên không tự gọi đúng/sai hoặc relabelN.
Nhưng cũng **không được bỏ qua chúng khi tuyên bố precision trên toàn ECG**.
Quality gate không phát hiện “ngoài class”; hai output hiện tại không tự tạo
UNKNOWN choL/R/A/F. Label-scope/OOD là một blocker trước chạy AI trên stream.

## 4. Split, leakage và khả năng Test độc lập

Saved split:Train58134(53216N/4918V),Validation12459(11159N/1300V),
Test11279(10374N/905V). Index và record không giao;201/202 cùngTrain/cùnggroup.
MIT-BIH có48record/47người,201/202 cùngngười theo
[PhysioNet](https://physionet.org/content/mitdb/1.0.0/). Không suy bệnh nhân độc
lập chỉ từ IDrecord khác; đối chiếu patient-group trước cohort mới. Window
overlap **trong cùng record** không tự gây train/test leakage khi giữ cảrecord
cùngpartition. Normalization từng beat, class weights và600 representative
quantization sample chỉTrain; đã kiểm indices calibration thuộcTrain.

Rủi ro còn lại:split seed127 chọn từ200seed theo count/label của các partition,
nên holdout construction có thông tin nhãn (không phải dùng prediction để chọn).
Validation đã dùng early-stop/model selection,threshold,review và định hướng
detector; không còn đánh giá độc lập dù tham số detector chọn trênTrain.
Record morphology/context, class imbalance, paced/fusion record và tín hiệu
AD8232 thật đều có thể khác; PPV còn phụ thuộc prevalence. Current source/audit
không chứng minh hoàn toàn lịch sử thực thi vì training không lưu executed-codeSHA.

**Không có Test mới chưa từng xem được xác lập trong workspace.** Script6 đã
`predict(X[test])`, `cnn_metrics.json:evaluation` có kết quả, audit6.5 đã ghi nhận
Test exposure. Saved Test gồm107/108/113/117/123/200/222; không đọc signal hay chạy
inference Test trong lượt này. Có thể đánh giá lại bản đóng băng trên Test cũ
với nhãn “đã từng xem”, nhưng không gọi là lần cuối độc lập; không đổi tên/chia
lại các beat đã xem để tạo “Test mới”. Cần cohort/bệnh nhân ngoài quá trình chọn
mô hình/tham số; simulator là bench, không thay đánh giá bệnh nhân độc lập.

## 5. Tiêu chí nghiệm thu cần chốt trước đánh giá mới

- **Giữ tiêu chí detector đã có:** mỗirecord sensitivity≥99%,PPV≥99%,p95≤40ms,
 matching±12sample;0false peaks flat/50Hz,0full/duplicate/order.121 vẫn FAIL.
- **Đề xuất nghiên cứu, chưa được duyệt/chấm:** PVC end-to-end recall≥95%,
 precision≥90%,F1≥92%; N end-to-end recall≥99%. Chốt label-scope trước: N/V-only
 hayV/nonV/OOD; cộng miss trướcCNN vàoFN, unmatched alarms vàoFP và quy định xử
 lý các lớp khác. Đây không phải chuẩn lâm sàng và **không áp ngược để công bố
 PASS/FAIL mới trên Validation đã dùng phân tích**.
- Đóng băng model/kernel/threshold/preprocessing/record exclusions và protocol
 trước cohort độc lập; báo per-record/per-patient/per-class, worst strata,
 95%CI theo patient-cluster; định trước sốpositive tối thiểu và cách báoNA khi
 không có class, không bỏrecord khó. Không chọn lại threshold bằng Test.
- Bench/safety:giữINVALID_LEADS/rail/gap/clipping/queue/generation và kết quả
 stale; không NN classification cho dữ liệu invalid. Xác minh250Hz/latency/
 heap/stack/CPU dưới tải thật, golden/parity target và trace trên Xtensa theo
 binarySHA. Các tiêu chí timing thực và phân loại đầy đủ vẫn PENDING.

## Kết luận và bước tối thiểu

1. **Code:** chưa có bug implementation mới được chứng minh; không sửa firmware.
 Detector121 là heuristic còn yếu, CNNcontext/label-scope là vấn đề thiết kế.
2. **CNN:** nên nghiên cứu huấn luyện lại có mục tiêu trung tâm và dữ liệu đúng
 phạm vi; chưa đủ cơ sở nói retrain tự động thành công, không train trong lượt này.
3. **Chưa đạt:** PPV121; nghiệm thu classification và nonN/V policy; Test mới độc
 lập; hardware/system timing. Golden/parity/build2B tái sử dụng với SHA bảo toàn,
 không chạy lại các test không liên quan.
4. Trước AI trênESP32:chốt scope/criteria; sửa detection và kiểm chứng mô hình
 trong nhánhTrain/development được duyệt; đóng băng rồi đánh giá ngoài đã dùng;
 sau đó bench/simulator/safety dưới yêu cầu riêng. **AI-live vẫn LOCKED**.

Evidence: `debug/final_ai_readiness/evidence.json`, `matched_cases.csv` (từng lỗi
và đúng:record/shape/amplitude/center/score/đối chứng), `pre_cnn_misses.csv`,
`unmatched_pvc_alerts.csv`, `train_false_peaks.csv`. Counterfactual24.756 inputs
native/TF EXACT; Float32 probe chỉpredict, modelSHA không đổi. {len(d['protected_checks'])}file/artefact
bảo vệ khớp SHA. Không đổi model/split/threshold/telemetry/GUI, không mởCOM,
flash/reset hoặc mởlive. Dừng tại báo cáo, không tự chuyển giai đoạn.
'''
    (FW/'docs/final_ai_readiness_review.md').write_text(report,encoding='utf-8')
    print('Wrote final_ai_readiness_review.md; evidence and protection checks PASS; no production changes.')
if __name__=='__main__':main()
