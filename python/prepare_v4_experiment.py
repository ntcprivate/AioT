"""Create an isolated V4 experiment once. Never builds, flashes or opens Serial."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'firmware/esp32_ecg_tinyml_integrated'
NEW = ROOT / 'firmware/esp32_ecg_v4_experiment'
OUT = ROOT / 'results/cnn_v4/esp32_end_to_end'
GOLD = ROOT / 'results/cnn_v4/esp32_golden_test'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if NEW.exists() or OUT.exists():
        raise RuntimeError('Refusing to overwrite existing experiment')
    meta = json.loads((GOLD / 'fixtures.json').read_text())
    assert sha(ROOT / 'models/v4/ecg_cnn_v4_int8.tflite') == meta['model_sha256']
    assert sha(ROOT / 'models/v4/ecg_cnn_v4_best.keras') == meta['source_checkpoint_sha256']
    OUT.mkdir(parents=True)
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in OLD.rglob('*')
              if p.is_file() and not any(s in {'build', 'managed_components', '.git'} for s in p.relative_to(OLD).parts)}
    (OUT / 'original_firmware_hashes.json').write_text(json.dumps(before, indent=2))
    (NEW / 'main').mkdir(parents=True)
    for p in (OLD / 'main').glob('*'):
        if p.is_file(): shutil.copy2(p, NEW / 'main' / p.name)
    shutil.copy2(OLD / 'CMakeLists.txt', NEW / 'CMakeLists.txt')
    # Only the model-dependent golden metadata/assets change; references are reused.
    (NEW / 'main/model').mkdir()
    shutil.copy2(ROOT / 'models/v4/ecg_cnn_v4_int8.tflite', NEW / 'main/model/ecg_cnn_int8.tflite')
    (NEW / 'main/test_data').mkdir()
    shutil.copy2(GOLD / 'firmware/main/assets/v4_inputs.bin', NEW / 'main/test_data/ecg_test_samples_int8.bin')
    (NEW / 'main/assets').mkdir()
    shutil.copy2(GOLD / 'firmware/main/assets/v4_raw.bin', NEW / 'main/assets/v4_raw.bin')
    rows = ['#pragma once', '#include <cstdint>', '#include <cstddef>',
            'constexpr size_t kSampleCount=22,kSamplesPerBeat=256,kModelBytes=8688;',
            'constexpr float kThreshold=0.88f;', 'constexpr int kThresholdCode=98;',
            'constexpr float kInputScale=0.06217966973781586f,kOutputScale=0.00390625f;',
            'constexpr int kInputZero=-8,kOutputZero=-128;',
            f'constexpr char kModelSha[]="{meta["model_sha256"]}";',
            f'constexpr char kSamplesSha[]="{meta["input_sha256"]}";',
            'struct Golden {int dataset_index;const char* record;int label,output;float score;int predicted;};',
            'constexpr Golden kGolden[kSampleCount]={']
    for f in meta['fixtures']:
        rows.append('{%d,"%s",%d,%d,%.9ff,%d},' % (f['validation_index'], f['record'], f['label'],
                    f['reference_code'], f['pvc_probability'], f['reference_prediction']))
    rows += ['};']
    (NEW / 'main/test_data/ecg_test_metadata.h').write_text('\n'.join(rows)+'\n')
    # Keep the exact verified V4 arithmetic adapters, not an inferred rounding choice.
    for name in ['single_round_conv.cpp','single_round_conv.h','single_round_fc.cpp','single_round_fc.h','single_round_math.h']:
        shutil.copy2(GOLD / 'firmware/main' / name, NEW / 'main' / name)
    text = (NEW / 'main/research_shadow.h').read_text()
    text = text.replace('#include "signal.h"', '#include "signal.h"\n#include "test_data/ecg_test_metadata.h"')
    text = text.replace('score>=0.52f', 'score>=kThreshold')
    (NEW / 'main/research_shadow.h').write_text(text)
    p = NEW / 'main/telemetry.cpp'; text=p.read_text()
    text=text.replace('#if CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST\nconstexpr bool', '#if V4_REPLAY\nconstexpr bool kSynthetic=false;\nconstexpr const char* kSource="LABELED_REPLAY";\n#elif CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST\nconstexpr bool', 1)
    text=text.replace('\\"threshold\\":0.52', '\\"threshold\\":0.88').replace('s.model_ready?"READY":"DISABLED"','s.model_ready?"V4_INT8_READY":"V4_DISABLED"')
    p.write_text(text)
    p=NEW / 'main/pipeline.cpp';text=p.read_text().replace('\\"source\\":\\"ADC_CNN\\"','\\"source\\":\\"V4_EXPERIMENT_CNN\\"')
    # Durable per-beat log emitted by the worker, never the ADC task.
    needle='            portEXIT_CRITICAL(&lock);\n            vTaskDelay(1);'
    addition='''            portEXIT_CRITICAL(&lock);
            console_lock();
            printf("V4_BEAT r_index=%lld r_us=%lld window_end_us=%lld code=%d p_pvc=%.9f predicted=%d rejected=%d reason=%s prep_us=%lld invoke_us=%lld result_us=%lld e2e_us=%lld generation=%lu\\n",
                (long long)ai_window.r_sample,(long long)ai_window.r_us,(long long)ai_window.end_us,code,score,
                (!reject && still_safe)?int(code>=kThresholdCode):-1,int(reject || !still_safe),reject?reject:(!still_safe?"SIGNAL_CHANGED":"NONE"),
                (long long)prep,(long long)latency,(long long)end,(long long)(end-ai_window.r_us),(unsigned long)ai_window.generation);
            console_unlock();
            vTaskDelay(1);'''
    assert needle in text;text=text.replace(needle,addition,1)
    text=text.replace('            if(issue) {\n                portENTER_CRITICAL', '            if(issue) {\n                console_lock();printf("V4_DETECTOR_EVENT block=%lu offset=%d reason=%s\\n",(unsigned long)block.id,i,issue);console_unlock();\n                portENTER_CRITICAL',1)
    p.write_text(text)
    print('Created isolated source; original hashes saved. Remaining new files are authored separately.')

if __name__=='__main__': main()
