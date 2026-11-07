"""Render the stage-1 audit from measured metrics; no firmware edits or device access."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
FW=ROOT/'firmware/esp32_ecg_tinyml_integrated'
OUT=FW/'debug/r_peak_audit'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def pct(x):return f'{100*x:.4f}%'

def finish(d):
    source_map=[
        dict(file='main/signal.h',line=7,symbol='BeatDetector',role='Streaming state: 512-sample raw/time ring, one pending center, EMA states'),
        dict(file='main/signal.cpp',line=38,symbol='BeatDetector::push',role='Baseline residual, threshold, refractory, pending window, reset'),
        dict(file='main/signal.cpp',line=37,symbol='BeatDetector::reset',role='Resets all state, including warm-up age and baseline'),
        dict(file='main/signal.cpp',line=22,symbol='signal_block_reason',role='Rail, timestamp, minimum PTP and mean-difference gates'),
        dict(file='main/signal.cpp',line=6,symbol='signal_metrics',role='Diagnostic DFT50/variation/baseline metrics; not detector filtering'),
        dict(file='main/pipeline.cpp',line=171,symbol='worker',role='Model/golden, quality/recovery, block continuity, guarded detector invocation'),
        dict(file='main/pipeline.cpp',line=267,symbol='pipeline_observe',role='Immediate lead-off/ADC/timing safety'),
        dict(file='main/pipeline.cpp',line=281,symbol='pipeline_offer',role='Immutable queued block with generation/hash'),
        dict(file='main/model.cpp',line=98,symbol='model_invoke_beat',role='Calls unchanged quantization and CNN'),
        dict(file='main/preprocessing.h',line=12,symbol='ecg_preprocessing::quantize',role='Per-beat z-score then int8 quantization; downstream of detector'),
        dict(file='main/system_state.h',line=4,symbol='kLivePipelineValidated',role='False; independent classification gate remains closed'),
        dict(file='main/Kconfig.projbuild',line=58,symbol='ECG_ADC_RAIL_MARGIN .. ECG_QRS_MIN_COUNTS',role='16 / 20 / 25 / 30, matching tests/sdkconfig.h'),
        dict(file='tests/detector_replay.cpp',line=8,symbol='main',role='Historical native candidate + quality-gated host mirror'),
        dict(file='tests/signal_test.cpp',line=10,symbol='main',role='Synthetic polarity, ring indexing and quality controls'),
        dict(file='tools/ecg_monitor/validate_offline.py',line=22,symbol='score / main',role='Validation selection, resampling, historical greedy ±12 score'),
        dict(file='tools/ecg_monitor/ecg_monitor/offline.py',line=25,symbol='display_filter',role='Causal notch50 + bandpass preview only; not detector/CNN input'),
        dict(file='python/04_extract_beats.py',line=25,symbol='main',role='Record100,25/36 resample, round-half-up annotations, raw256 slice then z-score; not called by live detector'),
        dict(file='python/05_build_dataset.py',line=37,symbol='extract_record',role='MLII, same integer annotation mapping, raw256 slice then z-score; not called by detector replay'),
    ]
    with (OUT/'false_negatives.csv').open(encoding='utf-8',newline='') as file:fn=list(csv.DictReader(file))
    d['source_map']=source_map
    d['fn_by_label_and_evidence']={label:dict(Counter(r['reason'] for r in fn if r['label']==label)) for label in sorted({r['label'] for r in fn})}
    d['findings']=[
        dict(id='PENDING_RESET',evidence='PROVEN_CODE_TRACE_AND_MICROTEST',priority=1,
            description='One pending window conflicts with a second eligible center at 75..126 samples; resets lose both and restart 500-sample warm-up',
            reset_events=sum(r['detector_issues'].get('AMBIGUOUS_CLOSE_PEAKS',0) for r in d['per_record']),
            fn_during_reset_warmup=d['fn_blocking_evidence']['RESET_WARMUP'],
            fn_pending_aborted=d['fn_blocking_evidence']['ACCEPTED_THEN_RESET_BEFORE_WINDOW'],
            fn_at_conflicting_center=d['fn_blocking_evidence']['PENDING_CONFLICT_RESET']),
        dict(id='REFRACTORY_WRONG_PRECEDING_PEAK',evidence='PROVEN_EXAMPLE',priority=2,
            record='115',reference_seconds=46.376,previous_reference_rr_ms=1048,
            preceding_false_emitted_peak_seconds=46.196,blocked_gap_ms=180,
            description='Not simply excessive real heart rate: an unrelated preceding accepted local maximum can suppress the true QRS'),
        dict(id='THRESHOLD',evidence='DESCRIPTIVE_TRACE_NOT_COUNTERFACTUAL',priority=3,
            adaptive_threshold_fn=d['fn_blocking_evidence'].get('BELOW_ADAPTIVE_THRESHOLD',0),
            absolute_floor_fn=d['fn_blocking_evidence'].get('BELOW_ABSOLUTE_FLOOR',0),
            description='Fixed ADC-unit floor and envelope over all magnitudes; no separate noise/QRS estimates or RR searchback'),
        dict(id='GATE',evidence='PROVEN_ON_THIS_HOST_REPLAY',priority=4,
            rejected_full_blocks=sum(sum(v for k,v in r['quality_blocks'].items() if k!='PASS') for r in d['per_record']),
            description='No full block quality rejection here; gated TP 13215 vs candidate13226 reflects replay admission/start/end history, not proof gate is harmless on hardware'),
        dict(id='XQRS_LIMIT',evidence='MEASURED_SAME_INPUT_AND_SCORE',priority=4,
            description='Strong offline baseline but record210 sensitivity and pure50Hz control fail unchanged criteria; not deployment approval'),
    ]
    d['stage2_proposal']=[
        dict(priority=1,change='Decouple QRS center detection from 256-sample window completion; bounded pending-center FIFO; preserve detector history on ordinary close beats',files=['main/signal.h','main/signal.cpp','tests/signal_test.cpp']),
        dict(priority=2,change='Causal QRS-energy detection branch with explicit delay and raw-signal localization; adaptive QRS/noise levels and bounded RR-aware searchback',files=['main/signal.h','main/signal.cpp','tests/detector_replay.cpp']),
        dict(priority=3,change='Review refractory and T/P-wave rejection using failure traces; no CNN or preprocessing changes',files=['main/signal.cpp','tests/signal_test.cpp']),
        dict(priority=4,change='Validate state/generation/quality recovery and scheduling using a host harness; keep safety and AI-live gates',files=['main/pipeline.cpp (only if an interface change is necessary)','tests/new detector pipeline replay tests']),
    ]
    d['required_post_change_tests']=[
        'Exact same seven Validation records, BEATS, MLII,25/36 resample,ADC mapping,±12 matching; no exclusions/tolerance shifts',
        'Per-record sensitivity>=.99,PPV>=.99,p95 timing<=40ms; zero flat/pure50Hz false peaks, as historical criteria',
        'Per-label N/V recall and full FN/FP plots; no claim from aggregate metrics alone',
        'RR sweep, prematurity/bigeminy, polarity, low amplitude, broad QRS, T/P interference, onset/end and ring/block boundary tests',
        'Multiple pending windows complete exactly256 samples; raw morphology and index128 center unchanged',
        'Lead-off/rails/gaps/quality recovery/generation integrity and bounded queues; no relaxed safety thresholds',
        'CNN golden12x33, preprocessing/CNN parity9425, old trace and GUI/telemetry regressions',
        'IDF5.4.4 build, then authorized simulator/board latency,CPU,heap,stack,ADC250Hz continuity; no auto COM/flash',
        'Validation reuse is exploratory; independent final evaluation and patient-aware leakage review before any live approval',
    ]
    test_path=ROOT/'tools/ecg_monitor/reports/r_peak_audit_tests.log'
    raw=test_path.read_bytes();tests=raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-16-le' if b'\0' in raw else 'utf-8-sig')
    match=re.search(r'Ran (\d+) tests',tests);assert match and '\nOK' in tests
    d['stage1_tests']=dict(python_tests=int(match[1]),status='PASS',log=str(test_path.relative_to(ROOT)),
        cpp='Both diagnostic and baseline replay built with -std=c++17 -O2 -Wall -Wextra -Werror; actual production signal.cpp linked',
        compiler=subprocess.run(['g++','--version'],text=True,capture_output=True,check=True).stdout.splitlines()[0],
        firmware_idf_build='NOT_RUN: no production firmware or configuration changes in analysis-only stage',
        cnn_golden_and_parity='NOT_RERUN: previous12/12 and9425/9425 artifacts/model/preprocessing protected by SHA; not a new board result')
    for file in (Path(__file__),ROOT/'tools/ecg_monitor/tests/test_r_peak_audit.py'):
        d['tool_sha256'][str(file.relative_to(ROOT))]=sha(file)
    d['protected_checks']={name:sha(ROOT/name)==digest for name,digest in json.loads((OUT/'before_sha256.json').read_text()).items()}
    assert all(d['protected_checks'].values())
    b=d['baseline'];x=d['xqrs'];g=d['quality_gated'];ca=d['fn_blocking_evidence']
    records='\n'.join(f"| {r['record']} | {r['candidate']['reference_beats']} | {r['candidate']['tp']} | {r['candidate']['fp']} | {r['candidate']['fn']} | {pct(r['candidate']['sensitivity'])} | {pct(r['candidate']['ppv'])} | {r['candidate']['timing_p95_abs_ms']:g} |" for r in d['per_record'])
    symbols='\n'.join(f"| {label} | {v['reference']} | {v['tp']} | {v['fn']} | {pct(v['sensitivity'])} | {d['xqrs_by_annotation'][label]['tp']} | {d['xqrs_by_annotation'][label]['fn']} | {pct(d['xqrs_by_annotation'][label]['sensitivity'])} |" for label,v in sorted(d['by_annotation'].items()))
    comparison='\n'.join(f"| {r['record']} | {r['xqrs']['tp']} | {r['xqrs']['fp']} | {r['xqrs']['fn']} | {pct(r['xqrs']['sensitivity'])} | {pct(r['xqrs']['ppv'])} | {r['xqrs']['timing_p95_abs_ms']:g} | {'PASS' if d['xqrs_record_criteria'][r['record']] else 'FAIL'} |" for r in d['per_record'])
    resets='\n'.join(f"| {r['record']} | {r['detector_issues'].get('AMBIGUOUS_CLOSE_PEAKS',0)} | {r['detector_issues'].get('NO_RELIABLE_R_PEAK',0)} | {r['warmup_seconds']:g} | {r['fn_blocking_evidence'].get('RESET_WARMUP',0)} |" for r in d['per_record'])
    source='\n'.join(f"| `{s['file']}:{s['line']}` | `{s['symbol']}` | {s['role']} |" for s in source_map)
    groups='\n'.join(f"| {name} | {count} | {100*count/b['fn']:.2f}% |" for name,count in ca.items())
    windows='\n'.join(f"| {w['record']} | {w['start_seconds']:g}–{w['end_seconds']:g} | {w['reference_beats']} | {w['fn']} | {w['fn_N']} | {w['fn_V']} |" for w in d['worst_ten_second_windows'][:12])
    figure_links='\n'.join(f"- [{e['record']} / {e['tag']} / {e['start_seconds']:.3f}–{e['end_seconds']:.3f}s](../{e['path']})" for e in d['examples'])
    report=f'''# Kiểm toán R-peak detector — giai đoạn 1, 2026-11-06

Đã tái lập đúng baseline: **{b['reference_beats']} nhịp tham chiếu, TP={b['tp']},
FP={b['fp']}, FN={b['fn']}; sensitivity={pct(b['sensitivity'])}, PPV={pct(b['ppv'])}**.
Điểm yếu chính có bằng chứng là xung đột một cửa sổ đang chờ với QRS đến sớm,
dẫn đến reset và mất thêm 2 giây khởi tạo. Chưa thay detector, CNN, preprocessing,
threshold0,52, quality gate, FSM hay sdkconfig. AI-live vẫn LOCKED; không mở COM/flash.

## 1. Source và quan hệ pipeline

Đường dẫn `main/` và `tests/` tính từ firmware này; `tools/` tính từ workspace.
Các vị trí dưới đây lấy từ source thực tế, không suy đoán tên file.

| File:dòng | Hàm/lớp | Vai trò |
|---|---|---|
{source}

ADC/GPTimer → `pipeline_observe` (lead-off/ADC/rail/gap) và `pipeline_offer`
(copy block256 + hash/generation) → worker kiểm tra continuity/quality/recovery →
**cổng live đang đóng** → nếu sau này được phép, `BeatDetector::push` → cửa sổ
raw256 → `model_invoke_beat` → z-score/quantize → CNN → cổng publish/FSM.
Hiện worker không gọi detector cho ADC-live vì cả cấu hình live OFF và
`kLivePipelineValidated=false`. Kết quả dưới đây đến từ host replay thực sự gọi
class C++, không phải từ phân loại ADC đang chạy.

**RR/BPM:** chưa có bộ ước lượng RR thích nghi hoặc RR searchback trong detector.
`last_center_` chỉ phục vụ refractory và timeout. Firmware phát `rr_ms=null`,
`bpm=null`; GUI hiển thị `-- / --`. RR trong báo cáo này là chênh lệch annotation
offline, không phải một tính năng BPM đã kiểm chứng.

## 2. Detector hiện tại

- Mỗi mẫu lưu vào ring512 kèm timestamp; EMA baseline hệ số0,01; magnitude là
  `abs(raw-baseline)`. EMA envelope của magnitude cũng hệ số0,01.
- Chọn local maximum của magnitude trước đó, khi magnitude vượt
  `max(30 ADC counts, 2.5*envelope hiện tại)`, sau warm-up500 mẫu≈2s.
  Floor30 tương đương khoảng0,15mV trong mapping bench200counts/mV; không phải
  ngưỡng đã hiệu chuẩn theo AD8232 thật. Không có riêng thống kê QRS/noise.
- Refractory75 mẫu=300ms. Không có QRS-band energy, T/P discrimination hoặc
  RR-aware searchback. Lấy trị tuyệt đối hỗ trợ hai cực tính, chưa bảo đảm xác
  định cùng fiducial R cho mọi QRS rộng/đa pha.
- Chỉ có **một `pending_`**. Đợi đến `current >= center+127` để trả slice
  `[center-128,center+128)`: đúng256 mẫu, center ở index128. Như vậy cần508ms từ
  center đến mẫu cuối, dù phần từ center có128 mẫu tính cả center.
- Đỉnh tiếp theo được chấp nhận về refractory ở khoảng75..126 mẫu
  (**300..504ms**) sẽ gặp pending cũ; nhánh ambiguity chạy trước nhánh hoàn tất
  cửa sổ, gọi `reset()` và không trả cả hai beat. Không phải mọi RR ngắn đều
  như vậy: <300ms bị refractory; từ508ms có thể đã hoàn tất cửa sổ trước.
- `reset()` xóa ring, baseline, envelope, center và count; lại mất500 mẫu warm-up.
  `NO_RELIABLE_R_PEAK` cũng reset: sau age>1000 và không có center trong>500 mẫu.
  Không có searchback thay cho reset.
- Timestamp cửa sổ phải có interval2000..6000µs. Replay dùng timestamp lý tưởng
  `index*4000`; chưa đánh giá scheduler ESP32 hay sai số clock trên board.

## 3. Tái lập baseline và tiêu chí cũ

Chỉ dùng record thuộc **Validation** từ `validation_indices` trong
`data/processed/mitbih_split_indices.npz`, tra `record_ids` của dataset cũ:
**115,118,121,210,214,233,234**. Không đánh giá Test, không loại record khó.
Mỗi record đọc đúng MLII theo `sig_name`; trong bảy record này MLII đều index0,
đơn vịmV, fs360. Không tổng quát hóa MLII luôn là kênh0.

Giữ nguyên `resample_poly(signal,25,36)`; ADC bench
`clip(rint(2048+200*signal250),0,4095)` int16; annotation
`floor(sample360*25/36+0.5)`. Dữ liệu input ADC từng record khớp SHA với replay cũ.
BEATS giữ nguyên từ `validate_offline.py`: `{d['matching']['beat_symbols']}`.
Không chỉ lấy N/V khi đánh giá QRS. Nhịp khởi tạo/biên vẫn tính vào FN.

Matching giữ nguyên: duyệt reference theo thứ tự, chọn nearest trong hai hàng
xóm searchsorted chưa dùng, sai số **≤12 mẫu=48ms**, mỗi detection chỉ dùng một
lần; giữ cả quy tắc tie cũ. Không sửa tolerance, không dịch detector theo annotation.
Khớp từng dictionary score candidate và gated với `offline_validation.json` cũ;
harness có trace cho **stdout giống hệt** harness production mới biên dịch.

Tiêu chí cũ: **từng record** sensitivity≥99%, PPV≥99%, p95 sai số tuyệt đối≤40ms;
flat và pure50Hz phải có0 false peaks. Tổng tốt không thay được từng record.

| Record | Reference | TP | FP | FN | Sensitivity | PPV | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
{records}

Tổng detector thuần: {b['tp']+b['fp']} detection, sensitivity{pct(b['sensitivity'])},
PPV{pct(b['ppv'])}. **FAIL**, giữ khóa live. Record233 đóng góp2116/3612 FN≈58,58%.
Quality-gated mirror: TP={g['tp']}, FP={g['fp']}, FN={g['fn']},
sensitivity={pct(g['sensitivity'])}, PPV={pct(g['ppv'])}.

### Theo loại annotation

| Loại | Reference | C++ TP | C++ FN | C++ sensitivity | XQRS TP | XQRS FN | XQRS sensitivity |
|---|---:|---:|---:|---:|---:|---:|---:|
{symbols}

N có nghĩa là đúng annotation **N**, không tự gộp L/R thành N. Detector QRS chưa
phân loại N/V nên FP không có true beat-type để tính PPV riêng theo N/V; chỉ báo
PPV toàn bộ. Không gán nhãn cho FP bằng annotation gần nhất để tạo metric đẹp.
**PVC chỉ phát hiện268/1301=20,5995%**, bất chấp PPV QRS toàn bộ99,3241%.
Không suy độ nhạy PVC toàn hệ thống từ golden CNN hoặc9425 matched windows:
parity chỉ kiểm tra thành phần trên các cửa sổ đã chọn, không bù nhịp bị bỏ sót.

## 4. Bằng chứng nguyên nhân

### 4.1 Pending/reset là ưu tiên đầu

| Record | Ambiguity resets | No-peak resets | Thời gian warm-up s | FN trong reset warm-up |
|---|---:|---:|---:|---:|
{resets}

Tổng795 ambiguity resets và3 no-peak resets; thời gian age<500 cộng cả khởi động
là1610s trên bảy record. Trong2238 FN khi khởi tạo lại, **2229** theo sau ambiguity
và9 theo sau no-peak reset. Trace ghi trực tiếp state của class production.

Phân nhóm mô tả cho toàn bộ3612 FN (có thứ tự ưu tiên; không phải ablation causal):

| Bằng chứng gần annotation | FN | Tỷ lệ trong FN |
|---|---:|---:|
{groups}

785 center đã được nhận nhưng reset trước khi đủ cửa sổ;444 FN tại center gây
xung đột;2238 FN trong warm-up sau reset. Ba nhóm chiếm3467/3612≈95,99%, nhưng
**không có nghĩa sửa pending chắc chắn thu hồi3467 TP**: state/threshold và matching
sẽ thay đổi. Đây là vị trí chặn quan sát được, chưa phải hiệu quả của thuật toán mới.
PVC FN gồm598 warm-up sau reset,402 conflict,22 accepted rồi bị hủy,7 dưới ngưỡng
thích nghi,3 warm-up ban đầu và1 refractory. PVC đến sớm và các nhịp N sau đó đều
bị ảnh hưởng. Không chỉ là vấn đề biên độ hoặc cực tính PVC.

Microtest gọi class nguyên bản: impulse tại600 và700 (RR400ms) gây ambiguity ở701;
cả hai không được emit, count về0 ở702; impulse1000 tiếp tục bị warm-up che;
đến1300 mới trả được beat. Đây là bằng chứng quyết định, không phải kết luận từ ảnh.

### 4.2 Refractory và nhầm local peak

81 FN thuộc nhóm refractory. Không nên chỉ rút ngắn refractory rồi kỳ vọng tốt:
record115 tại **46,376s** có RR annotation trước=1048ms, nhưng detector nhận một
đỉnh sai tại **46,196s**, cách R thật180ms; R thật bị chặn. Biểu đồ cho thấy FP
trước QRS; chưa cần gọi chắc đó là P hay T wave. Bộ chọn magnitude thiếu phân biệt
hình dạng/năng lượng QRS. Có5 reference RR≤300ms trong toàn tập, đều FN; nhiều
trường hợp refractory khác xuất phát từ center trước sai hoặc khác fiducial.

### 4.3 Ngưỡng, biên độ, cực tính, RR

39 FN có local maximum dưới ngưỡng thích nghi khi không bị warm-up ưu tiên che.
Không thấy FN được phân nhóm chỉ do floor30; cực đại residual trong±12 mẫu của
mọi reference đều≥30. Điều này **không chứng minh floor phù hợp phần cứng** hoặc
loại trừ tác động ngưỡng trong nhóm reset. Microtest biên độ29 bị chặn ở cả hai
cực tính; floor là yếu tố phụ thuộc gain ADC cần hiệu chuẩn sau này.

Trị tuyệt đối không có lỗi chỉ nhận QRS dương đơn giản: test impulse± đều qua.
Nhưng dữ liệu QRS âm/PVC có sensitivity thấp (chi tiết `morphology` trong JSON).
Đó là tương quan bị nhiễu bởi RR/reset, chưa chứng minh chỉ cần đảo cực sẽ sửa.
1151 reference có RR trước trong(300,508]ms,995 FN; nhưng các center C++ thực tế
mới quyết định conflict, không được đồng nhất RR annotation với khoảng center.
Không có cơ chế RR adaptation/searchback để phục hồi khi morphology/nhịp đổi.

### 4.4 Resampling, kênh và phase

Quy đổi annotation khớp công thức số nguyên `(sample*25+18)//36`; sai số làm tròn
tối đa≈2ms, nhỏ hơn tolerance48ms. Impulse test xác minh vị trí resample trong1
mẫu so với mapping. Không phát hiện lệch fs hoặc chọn sai kênh trong replay.
`04_extract_beats.py` và `05_build_dataset.py` cũng dùng cùng quy tắc half-up;
không tìm thấy khác biệt rounding với detector replay. Z-score ở các script
dataset và `preprocessing.h` áp dụng sau khi có beat256, không tạo đỉnh QRS.
`resample_poly` mặc định dùng FIR low-pass zero-phase, giữ time origin, không
tự thêm group-delay chưa bù. Biên zero-padding vẫn cần xét ở đầu/cuối.
[Tài liệu SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html).

Detector chỉ dùng EMA baseline trên nhánh detection; causal notch50/bandpass0,5–40
trong `display_filter` **không đưa vào detector hoặc CNN**. Không thể quy baseline
FN cho delay của display filter. EMA/magnitude có thể đổi fiducial ở QRS đa pha;
p95 hiện tại là trên TP đã match, không chứng minh không còn alignment errors.
Chưa phê duyệt thay waveform/CNN preprocessing bằng filtered signal.

### 4.5 Biên buffer và quality gate

Streaming ring giữ state qua256/512 mẫu, không reset mỗi buffer. Test center511,
767,1023 qua biên thành công. Có20 FN warm-up ban đầu và5 FN thiếu phần cuối cửa
sổ; đều giữ trong denominator. Chưa có bằng chứng lỗi off-by-one cắt256 mẫu:
slice center-128..center+127 đúng với preprocessing đã kiểm chứng.

Tất cả **12341 block đầy đủ** qua quality gate, không rail clipping trong bảy
input bench. Vì vậy không có bằng chứng quality gate là nguyên nhân chính của
78,55%. Mirror gated mất14 reference vốn candidate match và lấy lại3 (net−11TP),
do admission/history đầu và phần buffer cuối; không phải14 quality rejects.
Mirror bắt đầu feed sau hai block tốt và không feed trailing block thiếu256.
Đây chưa phải mô phỏng đầy đủ worker/generation/FSM/RTOS. Gate thực còn lead-off,
rail, ADC errors/gap/queue integrity và2 block recovery; **không tắt hay nới gate**.
Power50/baseline metrics là diagnostic, không có thêm power50 gate bí mật ở đây.

## 5. Đoạn bỏ sót và biểu đồ

Tìm theo bin10s cố định không chồng lắp; không chọn lại tolerance hay loại nhãn.
Đây là top của các cửa sổ đã xếp hạng theo FN; CSV giữ top10 từng record.

| Record | Thời gian s | Reference | FN | FN N | FN V |
|---|---|---:|---:|---:|---:|
{windows}

Ví dụ234/860–870s mất20/22 nhịp J dù sóng QRS rõ;233/740–750s mất17/17;
210/1080–1090s mất15/16, gồm8 PVC. Không dùng riêng ví dụ đẹp để chấm score.

Đã tạo19 hình offline. Mỗi hình có ECG MLII gốc360Hz và annotation, input250Hz,
center phát hiện, TP xanh/FN đỏ/FP tím, so sánh XQRS, magnitude/threshold và vùng
warm-up màu cam; đường đỏ đứt là ambiguity reset. TP/FN xác định trên toàn record
trước khi cắt hình, không matching lại theo đoạn. Marker xanh lam là detection
center; TP là annotation được match, hai vị trí có thể lệch≤48ms.

{figure_links}

## 6. XQRS offline cùng đầu vào và cách chấm

WFDB{d['versions']['wfdb']}, `xqrs_detect(...,fs=250,learn=True,verbose=False)`, defaults,
đầu vào **(ADC bench−2048)/200 mV**, tức cùng waveform đã quantize mà C++ nhận.
Không crop startup, correction, dịch peak hay dùng annotation để tune. Thư viện
đã có sẵn, không cài mới. XQRS dùng bandpass5–20Hz, wavelet integration, học
ngưỡng/nhịp và searchback theo RR. Đây là baseline **offline** có `filtfilt`
phi nhân quả, chưa phải thuật toán streaming tương đương trên ESP32.
[Tài liệu chính thức WFDB](https://wfdb.readthedocs.io/en/latest/processing.html#qrs-detectors).

| Record | XQRS TP | FP | FN | Sensitivity | PPV | p95 ms | Tiêu chí record |
|---|---:|---:|---:|---:|---:|---:|---|
{comparison}

Tổng XQRS: **TP={x['tp']}, FP={x['fp']}, FN={x['fn']}, sensitivity={pct(x['sensitivity'])},
PPV={pct(x['ppv'])}**. So với C++: TP tăng3529, FP giảm81, FN giảm3529 trên cùng
đánh giá này; chưa phải kết quả Test hoặc board. N đạt99,9821%, PVC94,7733%.

**XQRS vẫn FAIL toàn bộ tiêu chí cũ**: record210 sensitivity97,9245%<99%; ngoài ra
control pure50Hz30s có1 false peak ở sample7495=29,98s (sát biên cuối). Flat có0.
C++ có0 ở cả hai control. Không bỏ biên để cứu score và chưa kết luận chính xác
nguyên nhân peak XQRS đó; filtfilt/edge/learning là giả thuyết cần tách tiếp.
Kết quả này hỗ trợ dùng XQRS làm oracle so sánh offline, không thay detector ngay
và không dùng aggregate99,51% để mở AI-live.

## 7. Hướng sửa giai đoạn 2 để xem xét

1. **Ưu tiên tách detection khỏi hoàn tất cửa sổ**: FIFO center hữu hạn, mỗi center
   chỉ emit khi đủ128 mẫu từ center; giữ ring/state và xử lý RR ngắn bình thường
   mà không reset toàn detector. Overflow phải có fault rõ; không bỏ kiểm tra gap.
2. Nhánh QRS detection riêng có bandpass nhân quả + derivative/energy/integration
   kiểu Pan–Tompkins, hoặc biến thể wavelet/năng lượng gọn; track signal/noise
   levels, refractory và searchback có giới hạn theo RR. Đo/bù delay trên nhánh
   detection rồi localize lại trên raw ring. Không đưa signal lọc vào CNN.
3. Review P/T rejection, QRS rộng/đa pha/đảo cực và threshold phụ thuộc gain. Không
   hạ floor hoặc rút refractory hàng loạt trước khi đo FP và localization.
4. XQRS là comparator offline, không port nguyên `filtfilt`/SciPy lên ESP32.
   Chọn O(1) cập nhật/mẫu, buffer hữu hạn và báo latency/budget; chưa đo chi phí
   ESP32 nên không cam kết tốc độ/heap của thuật toán đề xuất.

File dự kiến: `main/signal.h/.cpp`, `tests/signal_test.cpp`, harness detector replay
và bài test mới về pending/RR/gap. `main/pipeline.cpp` chỉ xem xét nếu giao diện
center/window thay đổi, luôn giữ quality/generation/FSM. Script Validation giữ
nguyên matching/criteria; thêm report mà không sửa denominator.
Không dự kiến sửa model, golden, CNN threshold hay `preprocessing.h`.

## 8. Kiểm thử sau sửa và kiểm thử giai đoạn 1

Sau sửa phải chạy đúng bộ Validation/criteria cũ; báo per-record, per-label, FN/FP
đầy đủ; flat/50Hz/noisy ECG; RR sweep/premature/bigeminy, low amplitude, inversion,
wide QRS, P/T, startup/reset/buffer boundaries; multiple pending windows đúng256
mẫu và center index128; quality/lead-off/ADC/gap/recovery/generation/queue tests.
Chạy lại golden12×33, parity9425, trace/GUI/telemetry regression, build IDF5.4.4;
sau đó simulator/board với quyền riêng, đo latency/CPU/heap/stack và250Hz continuity.
Không tự chia lại data hoặc xem Test để tune. Validation đã dùng lại nhiều lần:
kết quả cải tiến chỉ khám phá, cần đánh giá độc lập thích hợp trước live approval.

Giai đoạn1: **{d['stage1_tests']['python_tests']} Python tests PASS** (42 cũ +9 audit), hai harness C++
biên dịch `-O2 -Wall -Wextra -Werror`; trace và native event output giống nhau trên
cả7 record. Test mới xác nhận lỗi hiện tại, không dùng nó làm expected behavior
cho detector tương lai. Ba fixture ban đầu tưởng không có timeout đã lộ đúng
`NO_RELIABLE_R_PEAK`; đã tách test timeout và sửa thời lượng/khoảng xung của fixture
để cô lập mỗi nhánh. Log lần thử đó giữ tại
`tools/ecg_monitor/reports/r_peak_audit_initial_fixture_failures.log`; không sửa
source detector hay số score để làm PASS. Log cuối: `reports/r_peak_audit_tests.log`.
Không build/flash firmware ở giai đoạn chỉ phân tích. Golden12/12/parity9425 là
kết quả trước đã bảo vệ SHA, **không tuyên bố vừa chạy lại trên board**.

## 9. File tạo, cách tái lập và giới hạn

- Báo cáo này và `debug/r_peak_detector_audit.json` (source map, metrics, evidence,
  plan/test list, SHA inputs/protected files).
- `debug/r_peak_audit/`: snapshot SHA, ADC bench riêng, binary trace32byte/mẫu,
  events CSV, detections/matches NPZ, `false_negatives.csv`, `worst_windows.csv`,19 PNG,
  hai executable host. Không thay file raw/model/split/báo cáo cũ.
- Công cụ mới: `tools/ecg_monitor/audit_r_peaks.py`, `r_peak_audit_report.py`,
  `tests/test_r_peak_audit.py`; harness `tests/detector_audit_replay.cpp`.
- Bản source firmware, sdkconfig, dataset/split, threshold JSON và báo cáo cũ
  đều khớp SHA snapshot trước giai đoạn1; chi tiết `protected_checks` trong JSON.

Tái lập bằng compiler g++ và môi trường monitor hiện có, không cần train/TensorFlow:

```powershell
Set-Location 'D:\\Code Part Two\\AIoT\\firmware\\esp32_ecg_tinyml_integrated'
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I main -I tests main/signal.cpp tests/detector_replay.cpp -o debug/r_peak_audit/detector_baseline.exe
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I main -I tests main/signal.cpp tests/detector_audit_replay.cpp -o debug/r_peak_audit/detector_audit.exe
Set-Location 'D:\\Code Part Two\\AIoT\\tools\\ecg_monitor'
$env:QT_QPA_PLATFORM='offscreen'
.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
.\\.venv\\Scripts\\python.exe audit_r_peaks.py
```

Chưa đủ dữ liệu: hiệu quả chính xác của FIFO/thuật toán mới; nguồn phân bố FP đầy
đủ theo P/T/noise; AD8232 gain/lead-off/common-mode thực; sai số board/RTOS và
CPU/memory budget; tổng quát hóa sang bệnh nhân độc lập. Morphology và RR có thể
liên quan nhưng không đồng nhất quan hệ nhân quả. **Không sử dụng dữ liệu
INVALID_LEADS để kết luận NORMAL/PVC. Không tự mở AI-live.**
'''
    (FW/'docs/r_peak_detector_audit.md').write_text(report,encoding='utf-8')
    (FW/'debug/r_peak_detector_audit.json').write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
    return d

if __name__=='__main__':
    finish(json.loads((FW/'debug/r_peak_detector_audit.json').read_text(encoding='utf-8')))
