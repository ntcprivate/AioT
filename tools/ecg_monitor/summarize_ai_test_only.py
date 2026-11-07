"""Build the final report from saved measurements, never fabricated hardware data."""
import json, re
from datetime import datetime,timezone
from pathlib import Path
from ecg_monitor.protocol import StreamParser
from run_ai_test_only_bench import ROOT,FW,OUT,sha

def read_log(path):
    data=Path(path).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig',errors='replace')

def timestamps(path):
    parser=StreamParser();times=[];leads=0;clipped=0
    for packet in parser.feed(Path(path).read_bytes()):
        if packet['type']=='samples':
            for t,raw,flags in packet['samples']:
                times.append(t);leads+=bool(flags&3);clipped+=raw in (0,4095)
    dt=sorted(b-a for a,b in zip(times,times[1:]));n=len(dt)
    return dict(samples=len(times),mean_interval_us=sum(dt)/n if n else None,min_interval_us=min(dt) if n else None,
        max_interval_us=max(dt) if n else None,p95_interval_us=dt[(95*n+99)//100-1] if n else None,
        overall_hz=(len(times)-1)*1e6/(times[-1]-times[0]) if n else None,lead_off_samples=leads,rail_samples=clipped)

def main():
    hardware=json.loads((OUT/'hardware_results.json').read_text());fixtures=json.loads((OUT/'fixture_manifest.json').read_text())
    before=json.loads((OUT/'before/sha256.json').read_text());unchanged=[];changed=[]
    for relative,digest in before.items():
        (unchanged if sha(ROOT/relative)==digest else changed).append(relative)
    builds={}
    for key,folder in [('normal_adc','build'),('normal_synthetic','build_synthetic_telemetry_test'),('test_adc','build_ai_test_only_adc'),('test_synthetic','build_ai_test_only_synthetic')]:
        p=FW/folder;cfg=(p/'config/sdkconfig.h').read_text();image=p/'esp32_ecg_tinyml_integrated.bin'
        builds[key]=dict(image_bytes=image.stat().st_size,app_sha256=sha(image),elf_sha256=sha(p/'esp32_ecg_tinyml_integrated.elf'),test_only='#define CONFIG_ECG_AI_TEST_ONLY 1' in cfg,
            live_enabled='#define CONFIG_ECG_ENABLE_EXPERIMENTAL_LIVE 1' in cfg,synthetic='#define CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST 1' in cfg)
        assert not builds[key]['live_enabled'];assert builds[key]['test_only']==key.startswith('test_')
    host=read_log(OUT/'host_tests.log');assert re.search(r'Ran 68 tests',host) and host.rstrip().endswith('OK')
    finaltests=read_log(OUT/'review_tests_final.log');assert 'Ran 10 tests' in finaltests and finaltests.rstrip().endswith('OK')
    for variant,row in hardware['runs'].items():row['timestamp_statistics']=timestamps(OUT/f'hardware_{variant}.bin')
    if (OUT/'restored_firmware.bin').exists():hardware['restoration']['timestamp_statistics']=timestamps(OUT/'restored_firmware.bin')
    restored=(OUT/'restored_firmware.bin').read_bytes()
    rt=hardware['restoration']['telemetry']
    hardware['restoration']['boot_checks']=dict(test_only_absent=b'ECG_AI_TEST_BEGIN ' not in restored,
        golden_passed=b'ECG_GOLDEN_DONE samples=12 failed=0 status=PASSED' in restored,
        hardware_source=rt['last_firmware_counters']['source']=='HARDWARE')
    assert all(hardware['restoration']['boot_checks'].values())
    assert rt['crc_failures']==rt['missing_samples']==0 and rt['valid_samples']>512
    wrong=[c for c in fixtures['cases'] if c['label']>=0 and int((c['code']+128)/256>=.52)!=c['label']]
    result=dict(created_utc=datetime.now(timezone.utc).isoformat(),scope='TEST_ONLY reference parity and hardware load; not live ECG accuracy',hardware=hardware,builds=builds,
        host=dict(regression_tests=68,status='PASS',review_tests_after_runner_changes=10,fixture_preprocessing_exact=True,tensorflow_reference_cases=20),
        protected_unchanged=unchanged,modified_baseline_files=changed,fixture_truth_errors=wrong,ai_live='LOCKED',
        limits=['Reference fixtures selected from already-used Validation, not an independent test','16 N/V fixtures include 4 known classification errors; 4 OTHER fixtures have no N/V truth','Short bench load runs do not prove long-term reliability or medical accuracy','Normal Synthetic configuration built but not flashed separately','CPU utilization not instrumented; Invoke latency includes scheduling/interrupt effects','Prior 157664-sample capture is prior evidence, not counted as this run'],
        pending=['Independent acceptance evaluation with pre-agreed detector/classification criteria','Record121 detector PPV weakness','End-to-end PVC recall87.70/F178.93 remain prior limitations','Physical signal-quality/R-peak verification before any live AI proposal'])
    target=FW/'debug/esp32_ai_test_only_results.json';target.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    lines=['# ESP32 AI TEST_ONLY — kết quả bench','',f'Ngày UTC: {result["created_utc"]}. ESP-IDF v5.4.4, ESP32-D0WD-V3 rev3.1, 240 MHz; COM3 CP210x; MAC b0:3f:d3:51:8b:ec.',
        '', 'Người dùng đã xác nhận bàn thử không có người kết nối và cho phép flash/reset. AI-live vẫn **LOCKED**. Không kích hoạt cảnh báo PVC bằng dữ liệu tham chiếu.',
        '', '## Thay đổi', '',
        '- `main/ai_test_only.cpp/.h`, `main/test_only/*`: 12 golden cũ + 8 input FC14 duy nhất; 3 warm-up + 30 lần đo/ca. Kiểm tra byte input sau preprocessing và output code chính xác; không sửa reference.',
        '- `main/Kconfig.projbuild`, `main/CMakeLists.txt`: TEST_ONLY mặc định OFF, fixture chỉ nhúng khi bật. Hai sdkconfig/build TEST_ONLY riêng trong debug; cấu hình thường giữ TEST_ONLY OFF.',
        '- `main/model.cpp/.h`: callback đo golden và đọc arena; log rõ cả hai đường FC single rounding đã có từ 2B. `main/pipeline.cpp`: chạy bài thử trong task AI hiện hữu, giữ khóa live.',
        '- `main/telemetry.cpp/.h`: getter chỉ đọc atomic/clock snapshot; không đổi UART v2, ADC, queue, GPIO, detector, preprocessing hoặc FSM. CMake gốc chỉ sửa mô tả kernel cho đúng code đã có.',
        '- `tools/ecg_monitor/generate_ai_test_only_fixtures.py`, `run_ai_test_only_bench.py`, `summarize_ai_test_only.py`, `tests/test_ai_test_only.py`: fixture, flash/capture/restore có timeout và kiểm chứng log. SDK config sinh lại chỉ thêm tùy chọn TEST_ONLY mặc định OFF.',
        '', '## Lỗi tìm thấy và sửa', '',
        'Lượt đầu: cả 20 ca output EXACT nhưng stress FAIL. Burst báo cáo case 0–11 làm task TX ưu tiên thấp không tiêu thụ kịp FIFO 6 gói: ADC rơi 4 gói/128 mẫu, Synthetic rơi 5 gói/160 mẫu. Gaps đầu tiên xuất hiện sau case 11 trong cả hai log; ADC missed_est=0. Đây là mất dữ liệu telemetry, không phải mất nhịp timer. Bằng chứng giữ nguyên ở `debug/esp32_ai_test_only/attempt1/` và `first_attempt_drop_evidence.json`.',
        '', 'Sửa riêng TEST_ONLY: nhường task 300 ms sau mỗi dòng CASE, ngoài khoảng đo. Không tăng queue, không giảm lấy mẫu, không dừng telemetry. Kết quả lượt lại bên dưới kiểm chứng tác động của pacing.',
        '', 'Sao lưu toàn flash ở baud cao bị timeout lặp tại 221.184 byte; vùng 0x30000 cũng dừng sau 24.576 byte. Đọc vùng nhỏ ở 115200 thành công, mỗi vùng được esptool xác minh MD5. Chưa đủ bằng chứng quy nguyên nhân vật lý cho UART/flash. Đã sao lưu chính xác vùng 0–0x70000, bao phủ mọi sector được hai image ghi; phần còn lại không bị ghi.',
        '', '## HOST và build', '',
        '68 regression tests PASS; 10 test kiểm chứng log chạy lại PASS. Bao gồm dữ liệu thiếu ký tự, thiếu DONE/case, duplicate, sai code/SHA và lỗi telemetry giả lập: đều bị từ chối. 20 fixture preprocessing và TensorFlow EXACT; bài FC14 host kiểm tra đủ 16 operator/8 input. Các số parity 9.425/9.425 và 33.586/33.586 là bằng chứng đã lưu từ 2B, không chạy lại toàn corpus trong nhiệm vụ này.',
        '', '| Build | Bytes | TEST_ONLY | Synthetic | AI-live |','|---|---:|---|---|---|']
    for key,v in builds.items():lines.append(f'| {key} | {v["image_bytes"]} | {v["test_only"]} | {v["synthetic"]} | LOCKED |')
    lines+=['','Bốn cấu hình build thành công; SHA image/ELF trong JSON. Hai bản TEST_ONLY đã flash và đối chiếu SHA ELF nhận từ board. Bản normal ADC/Synthetic mới chỉ build hồi quy, không flash riêng. Firmware gốc trước thử được khôi phục và đo lại bên dưới.',
        '', '## ESP32 HARDWARE — lượt sau pacing', '', '| Phép đo | ADC thật + reference | Synthetic + reference |','|---|---:|---:|']
    a=hardware['runs']['adc'];b=hardware['runs']['synthetic']
    def val(row,marker,key):return row['markers'][marker][0].get(key,'N/A')
    def counts(row):
        cases=row['markers']['CASE']
        return f'{sum(x.get("status")=="PASS" for x in cases[:12])}/12 + {sum(x.get("status")=="PASS" for x in cases[12:])}/8 EXACT'
    rows=[('Trạng thái',a['status'],b['status']),('Golden / FC14',counts(a),counts(b))]
    for label,m,k in [('Inference mean / µs','PERF','inf_mean_us'),('Inference p95 / µs','PERF','inf_p95_us'),('Inference max / µs','PERF','inf_max_us'),('Preprocessing mean / µs','PERF','prep_mean_us'),('Preprocessing p95 / µs','PERF','prep_p95_us'),('Preprocessing max / µs','PERF','prep_max_us'),('Arena used / bytes','PERF','arena_used'),('Heap internal free / bytes','PERF','heap_internal_free'),('Heap internal minimum since boot / bytes','PERF','heap_internal_min_boot'),('Heap largest free block / bytes','PERF','heap_internal_largest'),('AI stack minimum free / bytes','PERF','stack_free_bytes'),('ADC attempts trong bài thử','STRESS','adc_attempts_delta'),('Acquisition Hz (buffer cuối)','STRESS','acq_hz'),('ADC errors','STRESS','adc_errors_delta'),('Missed samples','STRESS','missed_delta'),('Late counter','STRESS','late_delta'),('TX queue drops','STRESS','queue_drops_delta'),('Thời gian stress / µs','STRESS','duration_us')]:rows.append((label,val(a,m,k),val(b,m,k)))
    for label,k in [('CRC lỗi','crc_failures'),('Mẫu thiếu trên host','missing_samples'),('Gói thiếu','packet_gaps'),('Synthetic pattern lỗi','synthetic_mismatches')]:rows.append((label,a['telemetry'][k],b['telemetry'][k]))
    for label,k in [('Mẫu nhận trên host','samples'),('Hz từ timestamp toàn capture','overall_hz'),('dt nhỏ nhất / µs','min_interval_us'),('dt lớn nhất / µs','max_interval_us'),('dt p95 / µs','p95_interval_us')]:rows.append((label,a['timestamp_statistics'][k],b['timestamp_statistics'][k]))
    rows.append(('Khoảng dt lệch >500 µs',a['telemetry']['rx_timing_violations'],b['telemetry']['rx_timing_violations']))
    lines += [f'| {label} | {x} | {y} |' for label,x,y in rows]
    lines += ['', '600 inference và 600 preprocessing được đo mỗi cấu hình; 60 warm-up kiểm tra exact nhưng không đưa vào latency. Preprocessing = z-score + quantization, không gồm copy fixture. Thời gian Invoke gồm ảnh hưởng lịch task/ngắt; chưa đo CPU utilization. Arena cấp 65.536 byte, used theo TFLM. Stack watermark tính byte theo ESP-IDF; heap minimum tính từ boot. Late là trễ lịch lấy mẫu theo code hiện hữu, khác missed; không tuyên bố không có jitter.',
        '', '## Từng ca trên board ADC', '', '| ID | Record | Nhãn | Code TF / ESP32 | P(PVC) | Dự đoán | So nhãn thật | Exact |', '|---|---|---|---|---:|---|---|---|']
    for r in a['markers']['CASE']:
        truth={'1':'đúng','0':'sai đã có ở reference','-1':'OTHER, không chấm N/V'}[r['truth_match']]
        lines.append(f'| {r["id"]} | {r["record"]} | {r["true_label"]} | {r["reference_code"]} / {r["code"]} | {r["p_pvc"]} | {r["predicted"]} | {truth} | {r["status"]} |')
    lines += ['', '**Exact parity không phải classification accuracy.** 4/16 ca N/V vẫn sai nhãn (golden1, golden2, golden4, fc14_233_20069), đúng như reference TensorFlow; 4 ca OTHER không có nhãn N/V. Đây là bộ fixture chọn để debug, không dùng tỷ lệ này ước lượng accuracy. Không train/tuning hay dùng Test độc lập.',
        '', '## Khôi phục và bảo toàn', '']
    restore=hardware['restoration'];lines.append(f'Khôi phục firmware trước thử: **{restore["status"]}**. Ghi lại đúng vùng backup và được esptool kiểm tra MD5; vùng ngoài 0x70000 không bị chạm. Không để TEST_ONLY lưu vĩnh viễn trên board. Manifest/hash/log nằm trong `debug/esp32_ai_test_only/`.')
    if 'telemetry' in restore:
        t=restore['telemetry'];lines.append(f'Capture sau khôi phục: {t["valid_samples"]} mẫu, CRC={t["crc_failures"]}, missing={t["missing_samples"]}, source=HARDWARE; golden 12/12 PASS, không có marker TEST_ONLY. Đây là byte firmware thực tế trước thử, không phải binary mới vừa build.')
        timing=restore['timestamp_statistics'];lines.append(f'Toàn bộ {timing["lead_off_samples"]}/{timing["samples"]} mẫu sau khôi phục có lead-off; {timing["rail_samples"]} mẫu chạm 0/4095. Firmware báo SIGNAL_INVALID/LEADS_OFF. Không dùng những mẫu này để kết luận NORMAL/PVC; CNN chỉ chạy fixture tham chiếu trong bài thử.')
    lines += ['', f'Model SHA-256: `{fixtures["model_sha256"]}`. Golden gốc SHA-256: `{fixtures["original_golden_sha256"]}`. Các file model, golden, preprocessing, signal detector, main lấy mẫu và state safety được xác minh hash không đổi; danh sách đầy đủ trong JSON.',
        '', '## Kết luận và PENDING', '',
        'Parity INT8 và khả năng chạy bài reference dưới tải được đánh giá bằng log board đính kèm. Không có kết luận AI-live đủ điều kiện. Record 121 vẫn có điểm yếu PPV; kết quả end-to-end cũ PVC recall 87,70%, F1 78,93% chưa thay đổi. Cần tiêu chí nghiệm thu được thống nhất trước đánh giá độc lập, kiểm chứng signal-quality/R-peak trên nguồn mô phỏng và đo tải dài hạn. Chưa đo CPU utilization độc lập. Không có thử nghiệm trên người; AI-live giữ LOCKED.',
        '', 'Dữ liệu: `debug/esp32_ai_test_only_results.json`; log raw/current tại `debug/esp32_ai_test_only/hardware_adc.bin`, `hardware_synthetic.bin`, `restored_firmware.bin`. Lượt FAIL giữ nguyên dưới `attempt1/`.']
    (FW/'docs/esp32_ai_test_only.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved report and results:',[(k,v['status']) for k,v in hardware['runs'].items()],'restore',restore['status'])

if __name__=='__main__':main()
