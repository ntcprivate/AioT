"""Finalize2B reports from existing runs, with strict failure reporting and SHA guards."""
from collections import Counter
import difflib,hashlib,json,re,statistics
from pathlib import Path
import numpy as np
from audit_r_peaks import assignment,rows_from
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/r_peak_phase2b';BEFORE=FW/'debug/r_peak_phase2b_before'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text(p):
    b=Path(p).read_bytes();return b.decode('utf-16' if b.startswith(b'\xff\xfe') else 'utf-16-le' if b'\0' in b else 'utf-8-sig')
def pct(x):return f'{100*x:.4f}%'
def main():
    if (OUT/'int8_fixed_checks/result.json').exists():
        from complete_r_peak_phase2b import main as complete
        return complete()
    d=json.loads((OUT/'evaluation.json').read_text());snapshot=json.loads((BEFORE/'sha256.json').read_text())
    changed=[p for p,h in snapshot.items() if sha(ROOT/p)!=h]
    assert set(changed)=={str((FW/f'main/signal.{x}').relative_to(ROOT)) for x in ('h','cpp')},changed
    d['protected_checks']={p:sha(ROOT/p)==h for p,h in snapshot.items() if p not in changed};assert all(d['protected_checks'].values())
    before=(BEFORE/'main/signal.cpp').read_text();after=(FW/'main/signal.cpp').read_text()
    fifo=lambda s:s[s.index('void BeatWindowBuffer::reset()'):s.index('void BeatDetector::reset_state()')]
    assert fifo(before)==fifo(after);d['fifo_source_unchanged']=True
    patch=[]
    for name in changed:
        rel=(ROOT/name).relative_to(FW);patch.extend(difflib.unified_diff((BEFORE/rel).read_text().splitlines(True),(ROOT/name).read_text().splitlines(True),fromfile='2a/'+str(rel),tofile='2b/'+str(rel)))
    (OUT/'source_diff.patch').write_text(''.join(patch))
    d['development']=dict(curvature_rejected=json.loads((OUT/'development_results.json').read_text()),confirmation=json.loads((OUT/'confirmation_development.json').read_text()),replacement=json.loads((OUT/'replacement_development.json').read_text()),
        disclaimer='Parameters selected on Train105/106/114/119/208/219 only; algorithm development also inspected reused Validation errors. This is not an independent final evaluation.')
    d['fixed_corpus_parity']=json.loads((OUT/'parity/result.json').read_text())
    d['expanded_parity']=json.loads((OUT/'new_window_parity.json').read_text())
    assert 'Ran 55 tests' in text(ROOT/'tools/ecg_monitor/reports/r_peak_phase2b_tests.log') and '\nOK' in text(ROOT/'tools/ecg_monitor/reports/r_peak_phase2b_tests.log')
    assert 'Ran 14 tests' in text(OUT/'trace_tests.log') and '\nOK' in text(OUT/'trace_tests.log')
    d['regression']=dict(python_tests=55,trace_python_tests=14,status='PASS',cpp='system/signal/lead_off/trace_codec/telemetry_wire/phase2B_detector/current_FIFO+frozen2A_FIFO/requantization20000',
        note='Historical2A tests remain frozen. New copy retains exact FIFO full/duplicate/order/gap tests; expected occupancy1..2 accounts for deferred enqueue, safety-reset fixture occurs after confirmation.')
    sizes=re.findall(r'\b([0-9a-fA-F]{8})\s+B\s+phase2a_detector_size',text(OUT/'esp32_size.log'));assert len(sizes)==2
    cpu=json.loads((OUT/'cpu_host.json').read_text())
    d['resources']=dict(esp32_detector_bytes_2a=int(sizes[0],16),esp32_detector_bytes_2b=int(sizes[1],16),fifo_bytes=6336,
        cpu_host=cpu,cpu_median_ns_per_sample={k:statistics.median(r['host_ns_per_sample'] for r in v) for k,v in cpu.items()},
        realtime_allocations=0,board_cpu_heap_stack_wcet='PENDING HARDWARE VALIDATION')
    d['builds']={}
    for mode,build,log in [('hardware','build','build_hardware.log'),('synthetic','build_synthetic_telemetry_test','build_synthetic.log')]:
        desc=json.loads((FW/build/'project_description.json').read_text());assert desc['git_revision']=='v5.4.4' and 'binary size' in text(OUT/log)
        p=FW/build/'esp32_ecg_tinyml_integrated.bin';d['builds'][mode]=dict(status='PASS',idf='v5.4.4',bytes=p.stat().st_size,sha256=sha(p),log=str((OUT/log).relative_to(FW)))
    for stage in ('2a','2b'):
        tp=Counter();fn=Counter()
        for r in d[stage]['per_record']:tp.update(r['matched_by_annotation']);fn.update(r['missed_by_annotation'])
        d[stage]['detector_by_annotation']={label:dict(tp=tp[label],fn=fn[label],sensitivity=tp[label]/(tp[label]+fn[label])) for label in sorted(tp.keys()|fn.keys())}
        latencies=[]
        for rid in d['records']:
            z=np.load(FW/f'debug/r_peak_audit/{rid}_detections.npz');rows=rows_from((OUT/f'{stage}_{rid}_events.csv').read_text());em=[r for r in rows if r[0]=='safe_peak']
            centers=np.array([int(r[1]) for r in em]);arrivals=np.array([int(r[2]) for r in em]);m,_=assignment(z['reference'],centers)
            for j,k in enumerate(m):
                if k>=0 and z['symbols'][j] in ('N','V'):latencies.append(int(arrivals[k]-z['reference'][j])*4)
        d[stage]['reference_NV_to_window_ready_ms']=dict(minimum=min(latencies),median=float(np.median(latencies)),p95=float(np.percentile(latencies,95)),maximum=max(latencies))
    d['status']='PHASE2B_COMPLETE_DETECTOR_AND_EXPANDED_PARITY_NOT_ACCEPTED_AI_LIVE_LOCKED'
    d['acceptance']=dict(detector='FAIL_RECORD121_PPV',fixed_golden_parity='PASS',expanded_exact_parity='FAIL_16_OF33586',
        classification='MEASURED_NO_PREDECLARED_ACCEPTANCE_THRESHOLD; not approved for live use',safety_host_tests='PASS',hardware='PENDING',ai_live='LOCKED')
    tools=[FW/'main/signal.h',FW/'main/signal.cpp',FW/'tests/detector_phase2b_replay.cpp',FW/'tests/detector_phase2b_test.cpp',FW/'tests/beat_window_phase2b_test.cpp']+[ROOT/'tools/ecg_monitor'/p for p in ('develop_r_peak_phase2b.py','develop_r_peak_phase2b_confirmation.py','develop_r_peak_phase2b_ratio.py','evaluate_r_peak_phase2b.py','report_r_peak_phase2b.py','tests/test_phase2b_detector.py')]
    d['source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in tools}
    a=d['2a']['detector'];b=d['2b']['detector'];e=d['2b']['end_to_end']['safe_mirror'];cm=e['conditional_confusion_rows_N_V'];old_e=d['2a']['end_to_end']['safe_mirror']
    table='\n'.join(f"| {r['record']} | {next(v for v in d['2a']['per_record'] if v['record']==r['record'])['tp']}/{next(v for v in d['2a']['per_record'] if v['record']==r['record'])['fp']}/{next(v for v in d['2a']['per_record'] if v['record']==r['record'])['fn']} | {r['tp']}/{r['fp']}/{r['fn']} | {pct(r['sensitivity'])} | {pct(r['ppv'])} | {'PASS' if d['2b']['record_pass'][r['record']] else 'FAIL'} |" for r in d['2b']['per_record'])
    metrics='\n'.join(f"| {label} | {pct(e['conditional_metrics'][label]['precision'])} | {pct(e['conditional_metrics'][label]['recall'])} | {pct(e['conditional_metrics'][label]['f1'])} | {pct(e['end_to_end_metrics_with_misses_and_unmatched'][label]['precision'])} | {pct(e['end_to_end_metrics_with_misses_and_unmatched'][label]['recall'])} | {pct(e['end_to_end_metrics_with_misses_and_unmatched'][label]['f1'])} |" for label in ('N','V'))
    report=f'''# Giai đoạn2B — R-peak và AI end-to-end

**Chưa đạt nghiệm thu; AI-live LOCKED.** Detector cải thiện nhưng record121 chưa
đạt PPV. Golden/corpus cũ PASS; parity mở rộng phát hiện16 output code khác.
Không mở COM3/flash/train; không thay model/weights/golden/CNN threshold0,52,
preprocessing,telemetryv2,GUI,GPIO,signal-quality/FSM hoặc khóa live.

## Thay đổi và cách chọn

Chỉ source firmware `main/signal.h/.cpp`: giữ nguyên toàn bộ code `BeatWindowBuffer`
2A (so sánh byte đoạn hàm), FIFO4/ring512/raw256/index128 không đổi.
Baseline detection EMA0,01→0,025 để bám baseline drift nhanh hơn; envelope0,01,
floor30, multiplier2,5, refractory75 và warm-up500 giữ nguyên.
Thêm xác nhận hữu hạn50sample=200ms: giữ local maximum đầu, chỉ thay khi đỉnh sau
mạnh hơn1,5lần trong khoảng đó. Tránh P/đỉnh giả yếu khóa refractory trước QRS,
đồng thời không trượt sang lobe muộn chỉ cao hơn một ít. Enqueue sau xác nhận;
cửa sổ vẫn trả ởcenter+127, không thêm200ms lên độ trễ508ms vốn có.
No-peak vẫn phát issue an toàn một lần, nhưng không reset nội bộ/khởi động lại
500sample chỉ do thiếu đỉnh; **worker invalid/recovery vẫn giữ nguyên và có thể
reset từ ngoài**. ADC ngoài range hoặc timestamp gap bị reject ngay.

Tham số chọn trên6 **Train** record105,106,114,119,208,219 (không dùng Test).
Đã loại thử nghiệm curvature vì FP/FN rất xấu trên Train; giữ nguyên fiducial
magnitude. So sánh3 cấu hình confirmation, rồi3 tỷ lệ replacement trên Train;
chọn macro-F1, tie theo sensitivity. Các plan/results ở `debug/r_peak_phase2b/`.
Đã nhìn Validation trong quá trình phát triển (bản giữ mạnh nhất làm xấu214,
cho thấy rủi ro dời sang lobe muộn), nhưng **không chọn tham số bằng score
Validation**. Validation dùng lại nên kết quả vẫn khám phá, không đánh giá độc lập.
Không dùng XQRS hay lọc waveform đưa vào CNN. Không sửa tham số tiếp để cứu121.

## Detector: cùng7 record/annotation/matching ±12sample=48ms

Baseline2A được biên dịch lại từ snapshot và khớp từng score trước so sánh.
Cùng MLII, resample25/36, round-half-up, ADC bench2048+200counts/mV, BEATS cũ,
giữ startup/end FN và toàn bộ record. Không đổi tolerance/criteria/split.

| Record | TP/FP/FN 2A | TP/FP/FN 2B | Sensitivity2B | PPV2B | Tiêu chí cũ |
|---|---:|---:|---:|---:|---|
{table}

Tổng16838 reference: TP{a['tp']}→{b['tp']}, FP{a['fp']}→{b['fp']}, FN{a['fn']}→{b['fn']};
sensitivity{pct(a['sensitivity'])}→{pct(b['sensitivity'])}; PPV{pct(a['ppv'])}→{pct(b['ppv'])}.
N: {pct(d['2a']['detector_by_annotation']['N']['sensitivity'])}→{pct(d['2b']['detector_by_annotation']['N']['sensitivity'])};
V: {pct(d['2a']['detector_by_annotation']['V']['sensitivity'])}→{pct(d['2b']['detector_by_annotation']['V']['sensitivity'])}.
Record118 và210 đã đạt;121 còn20FP/18FN, PPV98,9276%<99% nên **FAIL**.
FN theo annotation:37N,21V,8R,4L,1a,1F. Không có ambiguity reset, queue full,
duplicate/out-of-order; pending cuối2 cửa sổ chưa đủ tương lai, không padding.
Flat và pure50Hz30s đều0 peaks/0 safe windows; thiếu QRS vẫn báo issue, không
được diễn giải thành NORMAL. Gate rail/flat/noise/timing/lead-off không bị nới.

## End-to-end offline: R → raw256 → C++ preprocessing → native INT8 → threshold0,52

Harness xuất **window thực từ class C++**, assert từng raw sample/timestamp/thứ
tự; không cắt lại theo annotation để làm đẹp CNN. Native kernels và chuẩn hóa
thật được chạy, int8 input so với Python byte-for-byte. Cả2A/2B dùng cùng harness.
Primary report dưới đây dùng **safe host mirror**: block-quality/recovery2block,
reset khi issue, abstain khi quantization clipping rồi reset/recover. Đây là
offline chain, không phải chứng nhận worker/generation/FSM/RTOS hay thiết bị.
Clipping được preflight trong harness để không chạy CNN cho window sẽ bị loại;
firmware thật hiện Invoke trước rồi loại score — chính sách output tương đương,
nhưng không giả là cùng số lần Invoke hay cùng latency.

16838 reference mọi loại; mục tiêu binary có11167N+1301V=12468. Có
**{e['windows']} window formed**,2 window clipping bị loại; **{e['classified']} window
thực đưa qua CNN trong safe mirror**. Trong đó124? **không dùng tổng window làm
denominator accuracy**: matched N/V={sum(sum(row) for row in cm)}, matched loại khác
={sum(e['matched_other_annotation'].values())}, unmatched predictions={sum(e['unmatched_predictions'].values())}.
Loại khác (L/R/A/F/...) được liệt kê trong JSON, **không tự gán thành N**.
Miss trước CNN: **{e['missed_before_CNN_NV']['N']}N +{e['missed_before_CNN_NV']['V']}V**,
bao gồm detection/gate/clipping/recovery; không ẩn các nhịp đó.

Confusion matrix **chỉ matched N/V đủ điều kiện** (row=true, column=predicted):

| | Pred N | Pred V |
|---|---:|---:|
| True N | {cm[0][0]} | {cm[0][1]} |
| True V | {cm[1][0]} | {cm[1][1]} |

False classification matched N/V={e['false_classification_NV']}:
{cm[0][1]} N→PVC và{cm[1][0]} PVC→N. Accuracy có điều kiện={pct(e['conditional_accuracy'])}.
Unmatched QRS tạo thêm{e['unmatched_predictions'].get('N',0)} dự đoánN và
{e['unmatched_predictions'].get('V',0)} cảnh báoPVC. Những giá trị này tách khỏi
false classification của nhịp có annotation đúng loại.

| Lớp | Precision matched | Recall matched | F1 matched | Precision có unmatched FP | Recall toàn reference N/V | F1 gồm miss/unmatched |
|---|---:|---:|---:|---:|---:|---:|
{metrics}

Metric nghiêm hơn cộng miss trước CNN vào FN, unmatched predictions vào FP;
matched các loại ngoài N/V vẫn **ngoài phạm vi binary**, không phải precision
lâm sàng trên mọi nhịp. 2A→2B strict PVC recall
{pct(old_e['end_to_end_metrics_with_misses_and_unmatched']['V']['recall'])}→{pct(e['end_to_end_metrics_with_misses_and_unmatched']['V']['recall'])},
F1{pct(old_e['end_to_end_metrics_with_misses_and_unmatched']['V']['f1'])}→{pct(e['end_to_end_metrics_with_misses_and_unmatched']['V']['f1'])}.
Detector tốt hơn chưa giải quyết nhầm lớp của CNN; **parity không phải accuracy**.
Chưa có tiêu chí nghiệm thu classification định trước nên không tự tạo ngưỡng
PASS mới; số precision/recall hiện tại không đủ để đề xuất bật live.

Latency: center→window-ready508ms; annotationN/V→ready median
{d['2b']['reference_NV_to_window_ready_ms']['median']:g}ms, p95
{d['2b']['reference_NV_to_window_ready_ms']['p95']:g}ms trên replay250Hz. Native host
batch trung bình{d['2b']['host_batch_ms_per_window_including_process_io']:.4f}ms/window
**bao gồm process/I/O**, không phải Invoke/WCET ESP32 và không cộng hai clock
để giả latency board. Scheduler/inference/queue delay trên ESP32: PENDING.

## Regression, tài nguyên và giới hạn mới

- Golden host **12/12 EXACT**,33 lần/mẫu; corpus cố định **9425/9425 parity**,
  0 preprocessing byte/0 output code khác. Source model/kernel/preprocessing giữ SHA.
- Mở rộng so TensorFlow trên **33586 window mới** (candidate+safe, có cửa sổ trùng
  giữa hai đường): **16 code khác,8 record/center duy nhất, tối đa4LSB**,0 quyết
  định khác tại0,52. Có cảN/V vàL/R, không chỉ nhãn ngoài binary.
  **FAIL exact parity**, không nới tolerance. Preprocessing input đã khớp;
  khác biệt nằm sau input quantized trong native CNN/reference, chưa xác định
  operator đầu tiên. Không sửa kernel/golden/weights trong nhiệm vụ detector.
  Chi tiết ở `new_window_parity.json`; classification matrix trên dùng native.
- **55 Python +14 operator-trace tests PASS**, C++ signal/safety/lead-off/UART
  codec/confirmation/no-peak/invalid ADC/timing/FIFO/wrap/full/reset PASS.
  Test2A cũ giữ nguyên và chạy frozen; bản current copy vẫn kiểm FIFO4/full/order,
  chỉ đổi expectation occupancy1..2 do enqueue muộn và thời điểm reset fixture
  sau xác nhận. Đây không phải nới tiêu chí score detector.
- Cả2 build **ESP-IDF5.4.4 PASS**: hardware{d['builds']['hardware']['bytes']}byte,
  synthetic{d['builds']['synthetic']['bytes']}byte; log trong debug2B. Không flash.
- Xtensa sizeof detector6448→6496byte (**+48byte**); FIFO6336byte không đổi.
  Host median ns/sample RR400ms
  {d['resources']['cpu_median_ns_per_sample']['2a']:.3f}→{d['resources']['cpu_median_ns_per_sample']['2b']:.3f};
  không allocation/task mới, không chặn ADC. CPU/heap/stack/WCET board PENDING.

## Kết luận và file

Detector: **FAIL121**; exact parity mở rộng: **FAIL**; golden/corpus cũ/regression/
build: **PASS**; hardware: **PENDING**. Chỉ phù hợp thử bench/simulator với live
vẫn khóa khi có yêu cầu riêng; **chưa đủ bằng chứng để tiến tới AI-live hoặc đề
xuất mở khóa**. Cần xử lý FP121, debug operator cho8 input mismatch, xác lập tiêu
chí classification và kiểm thử phần cứng/signal-quality độc lập.

Source chính: `main/signal.h/.cpp`; harness/test mới `tests/detector_phase2b_*.cpp`,
`tests/beat_window_phase2b_test.cpp`; scripts phát triển/đánh giá/báo cáo dưới
`tools/ecg_monitor/*phase2b*.py`. {len(d['protected_checks'])} file bảo vệ khớp SHA;
snapshot2A ở `debug/r_peak_phase2b_before`, diff/log/input/predictions ở
`debug/r_peak_phase2b`. Báo cáo2A/GUI/telemetry cũ không bị ghi đè.
Máy đọc: `debug/r_peak_phase2b_results.json`. Không tạo biểu đồ mới.
'''
    # Avoid an ambiguous placeholder in the counts paragraph.
    report=report.replace('Trong đó124? **không dùng tổng window làm','**Không dùng tổng window làm')
    (FW/'docs/r_peak_detector_phase2b.md').write_text(report,encoding='utf-8')
    d['report']='docs/r_peak_detector_phase2b.md';(FW/'debug/r_peak_phase2b_results.json').write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(status=d['status'],acceptance=d['acceptance'],protected=len(d['protected_checks']),builds=d['builds']),indent=2))
if __name__=='__main__':main()
