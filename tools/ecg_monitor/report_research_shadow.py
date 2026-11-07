"""Summarize actual saved host/replay/board evidence without promoting PENDING."""
import json
from run_ai_test_only_bench import FW,ROOT,sha
from summarize_ai_test_only import read_log,timestamps
OUT=FW/'debug/research_shadow'

def main():
    hw=json.loads((OUT/'hardware_results.json').read_text());gui=json.loads((OUT/'gui_board_results.json').read_text(encoding='utf-8'))
    replay=json.loads((OUT/'replay_results.json').read_text());hostlog=read_log(OUT/'host_tests_final.log')
    assert 'Ran 82 tests' in hostlog and hostlog.rstrip().endswith('OK')
    before=json.loads((OUT/'before_sha256.json').read_text());unchanged=[];changed=[]
    for relative,digest in before.items():(unchanged if sha(ROOT/relative)==digest else changed).append(relative)
    for relative in before:
        if any(x in relative for x in ['main\\signal.','main\\preprocessing.h','main\\system_state.h','main\\main.cpp','main\\model.','main\\model\\','main\\test_data\\','single_round']):assert relative in unchanged,relative
    builds={}
    for b in ['build_research_shadow','build','build_synthetic_telemetry_test','build_ai_test_only_adc','build_ai_test_only_synthetic']:
        folder=FW/b;config=(folder/'config/sdkconfig.h').read_text();image=folder/'esp32_ecg_tinyml_integrated.bin'
        log=read_log(OUT/f'final_{b}.log');assert 'binary size' in log or 'no work to do' in log.lower(),b
        builds[b]=dict(status='PASS',bytes=image.stat().st_size,app_sha256=sha(image),elf_sha256=sha(folder/'esp32_ecg_tinyml_integrated.elf'),
            research='#define CONFIG_ECG_RESEARCH_SHADOW 1' in config,official_live='#define CONFIG_ECG_ENABLE_EXPERIMENTAL_LIVE 1' in config)
        assert not builds[b]['official_live'];assert builds[b]['research']==(b=='build_research_shadow')
    assert builds['build_research_shadow']['app_sha256']==hw['app_sha256'],'Board/build identity changed'
    hw['timestamp_statistics']=timestamps(OUT/'hardware.bin')
    last=[float(r['inference_ms']) for r in hw['golden']]
    latency=dict(scope='Last reported measured pass for each of12 golden cases, not a600-pass aggregate or ADC-shadow latency',samples=len(last),min_ms=min(last),mean_ms=sum(last)/len(last),max_ms=max(last))
    first=json.loads((OUT/'attempt1/hardware_results.json').read_text());second=json.loads((OUT/'attempt2/hardware_results.json').read_text())
    status='SOFTWARE_COMPLETE_VALID_ADC_DEMO_PENDING' if hw['classified']==0 else 'IMPLEMENTED_RESEARCH_ONLY'
    result=dict(date_context='2026-11-07 Asia/Saigon',status=status,official_ai_live='LOCKED',builds=builds,
        host=dict(tests=82,status='PASS',source='host_tests_final.log',cpp_engine='Production Engine+signal.cpp compiled with frozen config; reference FIFO byte/index parity, overflow, wrap, invalid/stale and no-peak controls'),
        replay=replay,hardware=hw,gui_actual_uart=gui,golden_last_pass_latency=latency,
        protected_unchanged=unchanged,modified_baseline_files=changed,
        new_files=['main/research_shadow.h','tests/research_shadow_test.cpp','tests/research_shadow_replay.cpp','tools/ecg_monitor/ecg_monitor/research.py','tools/ecg_monitor/tests/test_research_shadow.py','tools/ecg_monitor/run_research_shadow_bench.py','tools/ecg_monitor/gui_research_board_smoke.py','tools/ecg_monitor/verify_shadow_replay.py','tools/ecg_monitor/report_research_shadow.py','debug/research_shadow/sdkconfig.research'],
        fixes=dict(initial_hardware_status=first['status'],initial_tx_dropped=first['telemetry']['last_firmware_counters']['tx_dropped'],initial_missing=first['telemetry']['missing_samples'],
            after_tx_priority_fix_status=second['status'],after_tx_priority_fix_tx_dropped=second['telemetry']['last_firmware_counters']['tx_dropped'],
            reason='Gaps clustered during high-priority model golden load; fixed by TXpriority5 in Shadow only versus AIpriority4. Fixed queue6/baud115200/ADC250 unchanged',
            additional_safety='Generation check after preprocessing before Invoke, post-Invoke cancellation, local GUI epoch prevents previous result returning after reconnect'),
        pending=['Valid analog ECG-simulator input through AD8232/quality/detector/window/CNN to GUI NORMAL/PVC on physical ESP32','Shadow queue load/latency with valid analog beats and hardware in-flight lead-off transition','External electrical observation of LED/buzzer; firmware status and unchanged FSM do not replace measurement','Long-duration Shadow hardware run and independent acceptance; record121 weakness remains'],
        reused_evidence=dict(fc14_board='Prior8/8 hardware EXACT, unchanged kernels/model; current host regression reruns all16 operators for8 inputs',parity='Preserved9425/9425 and33586/33586 source/hash evidence; no full-corpus rerun or Test-set tuning'),
        scope='Research display only. Physical ADC invalid, not forced to NORMAL/PVC. No training, threshold/weights change or AI-live unlock.')
    (FW/'debug/research_shadow_results.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    f=hw['telemetry']['last_firmware_counters'];t=hw['timestamp_statistics']
    lines=['# Research Shadow Mode', '', 'Ngày 07/11/2026 (Asia/Saigon). **AI-live chính thức vẫn LOCKED.**', '',
        '## Kết luận đúng phạm vi', '',
        '**Đã hoàn thiện đường xử lý và GUI nghiên cứu; chưa chứng minh N/PVC từ ADC hợp lệ trên board hiện tại.** Host replay qua C++ thật + CNN native tạo NORMAL/PVC và khớp TensorFlow. ESP32 chạy golden đúng, nhưng AD8232 hiện LEADS_OFF/chạm rail nên Shadow giữ UNKNOWN/INVALID, không gọi CNN trên ADC. Đây là PENDING nguồn mô phỏng analog hợp lệ, không ép PASS bằng bỏ gate.', '',
        '## Thiết kế và file', '',
        '- `main/Kconfig.projbuild`: `ECG_RESEARCH_SHADOW` mặc định OFF; chỉ bản riêng bật. Loại trừ official-live, TEST_ONLY và Synthetic. `debug/research_shadow/sdkconfig.research` / `build_research_shadow` độc lập.',
        '- `main/research_shadow.h`: detector2B và FIFO2A nguyên trạng; thêm queue4 cửa sổ sao chép bất biến trong RAM tĩnh, một model worker sở hữu. Không tạo task theo beat. Metadata R sample/timestamp được đổi về chỉ số ADC thực sau startup/reset.',
        '- `main/pipeline.cpp/.h`: quality/recovery gate hiện tại → detector/window → kiểm tra tuổi → preprocessing nguyên trạng → loại quantization clipping → kiểm tra generation sát Invoke → CNN → kiểm tra lại generation. Queue block2 không chờ ADC; overflow có counters/reason và fail closed. Không gọi publish/FSM cảnh báo chính thức từ Shadow.',
        '- `main/telemetry.cpp`: thêm object `research` vào status ECG1 v2/CRC32 hiện tại; official classification=UNKNOWN, model=LOCKED, p_pvc=null không đổi. Nhãn nghiên cứu `mode=RESEARCH_SHADOW`, `source=ADC_CNN`, `experimental=true`. Buffer JSON/frame lớn hơn nằm tĩnh, riêng task TX. Shadow TX ưu tiên5, AI4; các cấu hình thường giữ TX2. Không đổi queue6/baud115200/GPTimer250Hz.',
        '- `tools/ecg_monitor/ecg_monitor/research.py`, `protocol.py`, `session.py`, `app.py`: vùng **RESEARCH AI — EXPERIMENTAL** riêng, xác suất/timestamp/age/latency/counters/reason; main AI vẫn LOCKED. Result TTL1500ms; Stop/Disconnect/reboot/đổi source xóa trạng thái. Sau Reconnect phải chờ result mới hơn epoch kết nối. Raw flags lead-off/clip/gap chặn ngay tại GUI; invalid cũ không thể được result cửa sổ chồng lên ghi đè.',
        '- `tests/research_shadow_test.cpp`, `tests/research_shadow_replay.cpp` và `tools/ecg_monitor/tests/test_research_shadow.py`: regression C++/parser/GUI. Các tool `verify_shadow_replay.py`, `run_research_shadow_bench.py`, `gui_research_board_smoke.py`, `report_research_shadow.py` tái lập bằng chứng.',
        '', 'Giữ nguyên model/weights, preprocessing, threshold0,52, detector/FIFO, main lấy mẫu/GPIO và `system_state.h`. SHA bảo toàn trong JSON. Không train/tuning trên Validation/Test. Các biểu đồ/chỉ số ADC/TX/RX/CRC còn trong monitor; kéo panel phải để xem thêm. CSV classification vẫn là kênh chính thức UNKNOWN; raw capture giữ đầy đủ research object.',
        '', '## HOST / REPLAY', '',
        '- 82 unittest PASS, gồm GUI/telemetry/FC14, detector/FIFO và14 test Shadow. C++ mới kiểm tra copy bất biến, nhiều cửa sổ/ring wrap/index sau reset, queue đầy, stale, leads/clip/gap/noise, no R; đối chiếu byte cửa sổ với detector nguyên trạng. GUI kiểm tra xác suất từ golden thật, Stop/Disconnect/Reconnect và kết quả cũ.',
        f'- Frozen Train record208, 60giây/15.000 mẫu: {replay["windows"]} cửa sổ, native/TF {replay["native_tf_exact"]}/{replay["windows"]} EXACT; dự đoán N={replay["predicted_N"]}, PVC={replay["predicted_PVC"]}; queue high={replay["queue_high"]}, drops={replay["queue_drops"]}. Rounding annotation `(sample*25+18)//36`, matching greedy ±12 mẫu như cũ; không chọn lại tham số.',
        '- Matched N/V confusion rows N,V: `[[61,0],[1,27]]`; 1 PVC→NORMAL là lỗi CNN trong smoke replay. Trước CNN bỏ5 N/V (3N,2V); 12 reference khác nhãn N/V không đổi thành Normal. Đây là dữ liệu Train đã dùng, không phải đánh giá accuracy độc lập.',
        '- FC14: regression host đối chiếu đủ16 operator/8 input hiện tại; bằng chứng board8/8 và parity9.425/9.425,33.586/33.586 trước đó tái sử dụng với source/model SHA bảo toàn, không gọi đó là chạy lại toàn corpus.',
        '', '## Build và firmware đã flash', '', '| Cấu hình | Build | Bytes | Shadow | Official-live |', '|---|---|---:|---|---|']
    for b,v in builds.items():lines.append(f'| {b} | {v["status"]} | {v["bytes"]} | {v["research"]} | LOCKED |')
    lines += ['', f'Board hiện giữ **build_research_shadow**. App SHA256 `{hw["app_sha256"]}`, ELF SHA256 `{hw["elf_sha256"]}`. ESP-IDF5.4.4, ESP32-D0WD-V3 rev3.1, 240MHz; COM3 CP210x; MAC b0:3f:d3:51:8b:ec. Model SHA `{sha(FW/"main/model/ecg_cnn_int8.tflite")}`.',
        '', 'Đã dùng xác nhận bench không có người kết nối trong phiên. Trước flash lần đầu, verify MD5 khớp firmware đã khôi phục ở nhiệm vụ trước; mỗi lần sau verify đúng image thử vừa lưu. Backup byte-exact vùng0–0x70000 vẫn tại `debug/esp32_ai_test_only/pre_test_touched_flash.bin`, đủ vùng ghi; ngoài vùng không bị chạm. ADC/Synthetic và các cấu hình cũ vẫn còn, Shadow OFF mặc định.',
        '', '## ESP32 thật / UART / GUI', '', '| Quan sát bản cuối | Kết quả |', '|---|---:|',
        f'| Capture bench | {hw["capture_seconds"]} giây |',
        '| CNN golden | 12/12 EXACT, cold/warm +30 measured stable |',
        f'| Last-pass latency được log của12 golden | min {latency["min_ms"]:.3f}, mean {latency["mean_ms"]:.3f}, max {latency["max_ms"]:.3f} ms |',
        f'| ADC Hz (buffer cuối / toàn capture) | {f["acq_hz"]} / {t["overall_hz"]:.6f} |',
        f'| Mẫu UART hợp lệ | {t["samples"]} |',
        f'| CRC / missing samples / TX drops | {hw["telemetry"]["crc_failures"]} / {hw["telemetry"]["missing_samples"]} / {f["tx_dropped"]} |',
        f'| ADC errors / missed slots / late | {f["adc_errors"]} / {f["missed_est"]} / {f["late"]} |',
        f'| UART write / timeout / format errors | {f["uart_write_errors"]} / {f["uart_tx_timeouts"]} / {f["format_errors"]} |',
        f'| Process-block / inference queue drops | {hw["block_drops"]} / {hw["queue_drops"]} |',
        f'| Heap internal free / minimum since boot | {hw["last_heap"]} / {hw["min_heap"]} bytes |',
        f'| AI task minimum stack free | {hw["minimum_stack_free"]} bytes |',
        f'| ADC Shadow CNN calls / classified | {hw["shadow_inference_calls"]} / {hw["classified"]} |',
        f'| Qt GUI đọc COM thật | {gui["status"]}, {gui["sample_count"]} mẫu, CRC={gui["crc"]}, missing={gui["missing"]} |',
        '', 'Các số latency trên là12 last-pass được log, không phải600-pass aggregate; latency ADC Shadow chưa đo vì bị gate. Trong capture có tải CNN golden thật, nhưng chưa có tải detector+inference với analog ECG hợp lệ. Không tuyên bố không có jitter: late và phân bố dt đầy đủ trong JSON. Heap minimum tính từ boot; stack là AI worker, không phải mọi task.',
        '', f'Đầu vào thật: {t["lead_off_samples"]}/{t["samples"]} mẫu lead-off; {t["rail_samples"]} mẫu chạm0/4095. GUI thật hiển thị RESEARCH_SHADOW ACTIVE, UNKNOWN/INVALID, LEADS_OFF, p=--, official LOCKED. Không ép gọi CNN hay hiển thị N/PVC trên những mẫu này. Buzzer flag luôn OFF; FSM và hàm pattern/GPIO không đổi. Chưa đo điện bên ngoài để khẳng định trạng thái LED/buzzer vật lý dưới prediction hợp lệ.',
        '', 'Golden12 vẫn có3 lỗi so nhãn thật (golden1 N→PVC, golden2 V→N, golden4 N→PVC), output khớp TensorFlow nên parity PASS. Không đổi reference để che lỗi. Kết quả Golden không đi vào panel prediction nghiên cứu ADC hoặc cảnh báo.',
        '', 'Lỗi được phát hiện trong lần thử đầu: 16 TX drops/512 mẫu thiếu, tập trung khi CNN golden tải cao; ADC missed=0. Tăng TX priority riêng Shadow lên5 (cao hơn AI4), không tăng queue/baud hay giảm lấy mẫu. Lượt120giây sau sửa và bản cuối90giây đều CRC/missing/drop=0. Giữ nguyên capture FAIL và image ở `debug/research_shadow/attempt1/`, lượt sau ở `attempt2/`; không sửa log.',
        '', '## PASS / PENDING', '',
        '- PASS: code/build, host safety/parser/GUI, replay actual C++/TF, current board golden, UART/ADC dưới golden load, invalid-input ngăn Shadow inference, official live LOCKED.',
        '- PENDING: demo **AD8232 analog hợp lệ → R/window → CNN ESP32 → NORMAL/PVC trong GUI**; đo queue/latency dưới beat thật từ simulator, lead-off trong lúc Invoke, stress dài và đo điện LED/buzzer. Hiện không có nguồn analog vượt quality gate; không tạo dữ liệu thay thế để kết luận PASS.',
        '- Detector record121 vẫn FAIL PPV theo báo cáo2B. Giới hạn accuracy/CNN và end-to-end cũ không thay đổi; chưa đủ cơ sở nghiệm thu chẩn đoán hay mở AI-live.',
        '', '## Mở ECG Monitor', '',
        'Mở `tools/ecg_monitor/Start_ECG_Monitor.bat` → chọn **HARDWARE MONITOR — USB Serial** → COM3 → **Connect** → **Start Monitoring**. Khu vực RESEARCH AI nằm đầu panel phải; không chọn VALIDATED AI TEST (vẫn LOCKED). Với trạng thái phần cứng hiện tại, UNKNOWN / INVALID / LEADS_OFF là đúng. Chỉ khi nguồn ECG mô phỏng phù hợp AD8232 vượt các gate và có beat mới, panel mới hiển thị NORMAL/PVC do CNN; không cần mở khóa official AI-live.',
        '', 'Artifact: `debug/research_shadow_results.json`; capture `debug/research_shadow/hardware.bin`, `gui_board_results.json`, ảnh `gui_actual_board.png`; replay `train208.*`, `replay_results.json`; build/test logs trong cùng thư mục. Dừng tại báo cáo, không train hoặc mở rộng nghiệm thu.']
    (FW/'docs/research_shadow_mode.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Saved report:',status,'board',hw['status'],'GUI',gui['status'])
if __name__=='__main__':main()
