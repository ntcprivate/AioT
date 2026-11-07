"""Resume finalizer: preserves previous evidence; reports measured failures without retuning."""
import csv, difflib, hashlib, json
from pathlib import Path
import numpy as np
from audit_r_peaks import assignment,rows_from
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';BASE=FW/'debug/r_peak_phase2b';OUT=BASE/'int8_fixed_checks';FIXED=BASE/'fixed_validation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def readlog(p):
    b=Path(p).read_bytes();return b.decode('utf-16' if b.startswith(b'\xff\xfe') else 'utf-16-le' if b'\0' in b else 'utf-8-sig')
def pct(x):return f'{100*x:.4f}%'
def main():
    old=json.loads((BASE/'resume/r_peak_phase2b_results.json').read_text(encoding='utf-8'))
    evaluation=json.loads((FIXED/'evaluation.json').read_text());proof=json.loads((OUT/'result.json').read_text())
    assert evaluation['2b']['detector']==old['2b']['detector']
    assert proof['extended33586']['mismatched_codes']==0 and proof['fixed9425']['mismatched_codes']==0
    assert sha(FIXED/'2b_all_q.bin')==sha(BASE/'2b_all_q.bin')
    assert sha(FIXED/'2b_all_codes.bin')==sha(OUT/'extended33586_codes.bin')
    cases=json.loads((BASE/'int8_diagnosis/operator_comparison.json').read_text());details=json.loads((BASE/'new_window_parity.json').read_text())['details']
    tf=np.fromfile(BASE/'2b_tf_codes.bin',dtype=np.int8);fixed=np.fromfile(OUT/'extended33586_codes.bin',dtype=np.int8)
    q=np.fromfile(BASE/'2b_all_q.bin',dtype=np.int8).reshape(-1,256);lookup={(c['record'],c['center']):c for c in cases};records=[]
    for x in details:
        c=lookup[x['record'],x['center']];assert q[x['index']].tobytes()==(BASE/'int8_diagnosis'/c['id']/'input.bin').read_bytes()
        row=dict(index=x['index'],mode=x['mode'],record=x['record'],center=x['center'],annotation=x['symbol'],native_before=x['native'],tensorflow=int(tf[x['index']]),native_after=int(fixed[x['index']]),
            p_before=(x['native']+128)/256,p_tensorflow=(int(tf[x['index']])+128)/256,p_after=(int(fixed[x['index']])+128)/256,
            absolute_probability_error_before=abs(x['native']-int(tf[x['index']]))/256,absolute_probability_error_after=0,
            class_before='V' if x['native']>=6 else 'N',class_after='V' if fixed[x['index']]>=6 else 'N',decision_changed=bool((x['native']>=6)!=(fixed[x['index']]>=6)),
            preprocessing_identical=True,input_sha256=c['input_sha256'],first_differing_operator_before=14,arithmetic=c['requantization'])
        assert row['native_after']==row['tensorflow'] and not row['decision_changed'];records.append(row)
    with (OUT/'sixteen_case_review.csv').open('w',encoding='utf-8',newline='') as f:
        rows=[{k:v for k,v in r.items() if k!='arithmetic'} for r in records];w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    # Analyse remaining121 errors on unchanged matching, without choosing new parameters.
    z=np.load(FW/'debug/r_peak_audit/121_detections.npz');events=rows_from((FIXED/'2b_121_events.csv').read_text());peaks=np.array([int(r[1]) for r in events if r[0]=='peak'])
    matches,fp=assignment(z['reference'],peaks);errors=[]
    for kind,values in [('FP',peaks[fp]),('FN',z['reference'][matches<0])]:
        for sample in values:
            j=int(np.argmin(abs(z['reference']-sample)));errors.append(dict(kind=kind,sample=int(sample),seconds=float(sample/250),nearest_annotation_sample=int(z['reference'][j]),nearest_annotation=str(z['symbols'][j]),delta_ms=int(sample-z['reference'][j])*4,nearest_reference_missed=bool(matches[j]<0)))
    (OUT/'record121_errors.json').write_text(json.dumps(errors,indent=2))
    d=old.copy();d.update(evaluation)
    d['resume']=dict(preserved_source_files=json.loads((BASE/'resume/source_inventory.json').read_text()),source_count_at_resume=11,
        correction='Curvature trial was rejected on Train; active detector is magnitude+confirmation, no new parameter selection in resume',
        pre_fix_reports='debug/r_peak_phase2b/resume',no_detector_retuning=True)
    d['int8_resolution']=dict(status='PASS_EXACT_AFTER_SCOPED_FIX',cases=records,unique_inputs=8,
        cause='Op14 per-tensor FC bypassed scoped adapter and used double rounding; inputs/op0..13 identical. Int32 accumulators fit, no saturation. Single vs double arithmetic reproduces all8 FC differences.',
        specification='GenericINT8 specification permits backend numerical variation; double rounding is not intrinsically invalid. It violated this project CPU-builtin EXACT contract; adapter now handles both per-channel and per-tensor INT8 FC.',
        spec_source='https://github.com/tensorflow/tensorflow/blob/master/tensorflow/lite/g3doc/performance/quantization_spec.md',
        maximum_final_lsb_before=4,maximum_probability_error_before=4/256,decision_changes_before_or_after=0,final_verification=proof)
    d['expanded_parity_before_fix']=old['expanded_parity'];d['expanded_parity']=proof['extended33586'];d['fixed_corpus_parity']=proof['fixed9425'];d['golden_verification']=dict(samples=12,repeats=33,status='PASS_EXACT')
    snapshot=json.loads((FW/'debug/r_peak_phase2b_before/sha256.json').read_text());allowed={str((FW/p).relative_to(ROOT)) for p in ('main/signal.h','main/signal.cpp','main/single_round_fc.cpp')}
    d['protected_checks']={p:sha(ROOT/p)==h for p,h in snapshot.items() if p not in allowed};assert all(d['protected_checks'].values())
    before=(FW/'debug/r_peak_phase2b_before/main/signal.cpp').read_text();after=(FW/'main/signal.cpp').read_text();extract=lambda s:s[s.index('void BeatWindowBuffer::reset()'):s.index('void BeatDetector::reset_state()')]
    assert extract(before)==extract(after);d['fifo_source_unchanged']=True
    d['record121_remaining']=dict(tp=1845,fp=20,fn=18,sensitivity=1845/1863,ppv=1845/1865,status='FAIL_PPV_BELOW_99_PERCENT',
        paired_false_detections=sum(r['kind']=='FP' and r['nearest_reference_missed'] for r in errors),
        limits='Nearest-annotation pairing is descriptive; no clinical P/T labeling inferred without review; all38 errors retained for diagnosis')
    d['record121_remaining']['branch_probe']=json.loads((OUT/'record121_branch_summary.json').read_text())
    d['builds']={}
    for mode,build,log in [('hardware','build','build_hardware.log'),('synthetic','build_synthetic_telemetry_test','build_synthetic.log')]:
        desc=json.loads((FW/build/'project_description.json').read_text());assert desc['git_revision']=='v5.4.4' and 'binary size' in readlog(OUT/log)
        p=FW/build/'esp32_ecg_tinyml_integrated.bin';d['builds'][mode]=dict(status='PASS',idf='v5.4.4',bytes=p.stat().st_size,sha256=sha(p),log=str((OUT/log).relative_to(FW)))
    assert 'Ran 58 tests' in readlog(ROOT/'tools/ecg_monitor/reports/r_peak_phase2b_final_tests.log') and '\nOK' in readlog(ROOT/'tools/ecg_monitor/reports/r_peak_phase2b_final_tests.log')
    assert 'Ran 14 tests' in readlog(OUT/'trace_tests.log') and '\nOK' in readlog(OUT/'trace_tests.log')
    d['regression']=dict(python_tests=58,trace_tests=14,cpp='PASS',actual_operator_traces='8 inputs x16 operators EXACT after fix',log='tools/ecg_monitor/reports/r_peak_phase2b_final_tests.log')
    d['status']='PHASE2B_COMPLETE_PARITY_FIXED_DETECTOR121_FAIL_AI_LIVE_LOCKED'
    d['acceptance']=dict(detector='FAIL_RECORD121_PPV',golden='PASS_12x33',preprocessing_and_fixed_parity='PASS_9425',extended_parity='PASS_33586',
        classification='MEASURED_NOT_APPROVED; no predeclared independent acceptance target',regression='PASS',builds='PASS_BOTH_IDF5.4.4',hardware='PENDING',ai_live='LOCKED')
    files=set(old['source_sha256'])|{str((FW/'main/single_round_fc.cpp').relative_to(ROOT))}|{str(p.relative_to(ROOT)) for p in [Path(__file__),ROOT/'tools/ecg_monitor/diagnose_phase2b_int8.py',ROOT/'tools/ecg_monitor/verify_phase2b_int8_fix.py',ROOT/'tools/ecg_monitor/tests/test_phase2b_int8_fix.py',FW/'tests/record121_diagnostic.cpp']}
    d['source_sha256']={p:sha(ROOT/p) for p in sorted(files)}
    patch=''.join(difflib.unified_diff((FW/'debug/r_peak_phase2b_before/main/single_round_fc.cpp').read_text().splitlines(True),(FW/'main/single_round_fc.cpp').read_text().splitlines(True),fromfile='before/single_round_fc.cpp',tofile='after/single_round_fc.cpp'))
    (OUT/'fc_fix.patch').write_text(patch)
    # Algorithmic ready latency is inherited: kernel fix does not alter detection/events.
    e=d['2b']['end_to_end']['safe_mirror'];cm=e['conditional_confusion_rows_N_V'];a=d['2a']['detector'];b=d['2b']['detector']
    table='\n'.join(f"|{r['record']}|{next(v for v in d['2a']['per_record'] if v['record']==r['record'])['tp']}/{next(v for v in d['2a']['per_record'] if v['record']==r['record'])['fp']}/{next(v for v in d['2a']['per_record'] if v['record']==r['record'])['fn']}|{r['tp']}/{r['fp']}/{r['fn']}|{pct(r['sensitivity'])}|{pct(r['ppv'])}|{'PASS' if d['2b']['record_pass'][r['record']] else 'FAIL'}|" for r in d['2b']['per_record'])
    pairs=[]
    for c in cases:
        rows=[r for r in records if r['record']==c['record'] and r['center']==c['center']];x=rows[0]
        pairs.append(f"|{c['record']}|{c['center']}|{' / '.join(str(r['index']) for r in rows)}|{x['native_before']}→{x['native_after']}|{x['p_before']:.8f}→{x['p_after']:.8f}|{x['class_after']} / không đổi|")
    metric='\n'.join(f"|{label}|{pct(e['conditional_metrics'][label]['precision'])}|{pct(e['conditional_metrics'][label]['recall'])}|{pct(e['conditional_metrics'][label]['f1'])}|{pct(e['end_to_end_metrics_with_misses_and_unmatched'][label]['recall'])}|{pct(e['end_to_end_metrics_with_misses_and_unmatched'][label]['f1'])}|" for label in ('N','V'))
    report=f'''# Kết quả cuối Giai đoạn2B — tiếp tục và chốt phần đang dở

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
{chr(10).join(pairs)}

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
{table}

16838 reference: TP{a['tp']}→{b['tp']},FP{a['fp']}→{b['fp']},FN{a['fn']}→{b['fn']};
sensitivity{pct(a['sensitivity'])}→{pct(b['sensitivity'])},
PPV{pct(a['ppv'])}→{pct(b['ppv'])}. Detector tìm16811 peaks,16766 match,72 miss.
121 còn20FP/18FN,PPV98,9276%<99%; sensitivity99,0338% đã đạt. Giữ toàn bộ38 lỗi
và nearest-annotation delta ở `int8_fixed_checks/record121_errors.json`;
{d['record121_remaining']['paired_false_detections']} FP đứng trước reference bị miss (64..420ms). Probe chỉ đọc state của
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
**{e['windows']} cửa sổ formed, {e['quantization_abstained']} không hợp lệ do clipping,
{e['classified']} cửa sổ qua CNN**. Trong đó matchedN/V={sum(map(sum,cm))},
matched loại khác={sum(e['matched_other_annotation'].values())}, unmatched={sum(e['unmatched_predictions'].values())}.
L/R/A/F/... liệt kê riêng trong JSON, **không tự gán thành N**.

Confusion matrix matchedN/V hợp lệ (hàng=true, cột=prediction):

| |Pred N|Pred V|
|---|---:|---:|
|True N|{cm[0][0]}|{cm[0][1]}|
|True V|{cm[1][0]}|{cm[1][1]}|

{cm[0][1]} NORMAL→PVC, {cm[1][0]} PVC→NORMAL. Miss trước CNN gồm detection/gate/
recovery/clipping: **{e['missed_before_CNN_NV']['N']}N +{e['missed_before_CNN_NV']['V']}V**.
Thêm **{e['unmatched_predictions'].get('V',0)} cảnh báoPVC từ đỉnh không khớp annotation**;
{e['unmatched_predictions'].get('N',0)} unmatched choN. Các số này tách khỏi lỗi phân loại nhịp đã match.

|Lớp|Precision matched|Recall matched|F1 matched|Recall toàn reference N/V|F1 gồm miss/unmatched|
|---|---:|---:|---:|---:|---:|
{metric}

Metric cột cuối cộng miss trước CNN vàoFN và unmatched prediction vàoFP;
precisionPVC theo cách này={pct(e['end_to_end_metrics_with_misses_and_unmatched']['V']['precision'])}.
Matched các nhãn ngoài N/V vẫn ngoài phạm vi binary — đây không phải precision
lâm sàng trên mọi loại nhịp. Parity là đồng nhất tính toán, **không phải accuracy**.
Detector tốt hơn vẫn để CNN nhầm lớp đáng kể; không có ngưỡng nghiệm thu
classification độc lập đã định trước, nên không tự tạo tiêu chíPASS.

Center→window-ready508ms (giữ128trước/128từcenter); host native batch trung bình
{d['2b']['host_batch_ms_per_window_including_process_io']:.4f}ms/window gồm process/I/O, **không phải Invoke/WCET ESP32**.
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
Binary ADC={d['builds']['hardware']['bytes']}byte;Synthetic={d['builds']['synthetic']['bytes']}byte,
SHA trong JSON; log mới ở `int8_fixed_checks/build_*.log`.

Giữ11 source đang dở, thêm sửa kernel1file có bằng chứng và công cụ chẩn đoán/
regression; {len(d['protected_checks'])} file còn lại khớp SHA gồm model/golden/preprocessing,
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
'''
    (FW/'docs/r_peak_detector_phase2b.md').write_text(report,encoding='utf-8');d['report']='docs/r_peak_detector_phase2b.md'
    (FW/'debug/r_peak_phase2b_results.json').write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
    (OUT/'resume_complete.json').write_text(json.dumps(dict(status=d['status'],protected=len(d['protected_checks']),source_count_at_resume=11),indent=2))
    print(json.dumps(dict(status=d['status'],detector=d['2b']['detector'],parity=proof['extended33586'],record121=d['record121_remaining'],protected=len(d['protected_checks'])),indent=2))
if __name__=='__main__':main()
