"""Read-only binary/config checks; writes a new preparation manifest, never flashes."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[4]
project=root/'firmware/esp32_ecg_v4_experiment'
build=project/'build_adc_MITBIH_100'
cache=(build/'CMakeCache.txt').read_text()
assert 'ECG_EXPERIMENT_MODE:STRING=ADC' in cache
commands=json.loads((build/'compile_commands.json').read_text())
main=[x for x in commands if '/main/' in x['file'].replace('\\','/')]
names=[Path(x['file']).name for x in main]
assert 'main.cpp' in names and not {'benchmark.cpp','replay_main.cpp'} & set(names)
assert all('V4_REPLAY=0' in x['command'] for x in main)
tflm=[x for x in commands if 'esp-tflite-micro' in x['file']]
assert tflm and not any('-DESP_NN ' in x['command'] or '-DESP_NN=' in x['command'] for x in tflm)
sdk=(project/'sdkconfig').read_text()
assert 'CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ=160\n' in sdk
assert '# CONFIG_ECG_SYNTHETIC_TELEMETRY_TEST is not set' in sdk
expected='a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e'
model=root/'models/v4/ecg_cnn_v4_int8.tflite'
assert hashlib.sha256(model.read_bytes()).hexdigest()==expected
assert model.read_bytes()==(project/'main/model/ecg_cnn_int8.tflite').read_bytes()
app=build/'esp32_ecg_v4_experiment.bin'
assert model.read_bytes() in app.read_bytes()
files=[model,app,build/'bootloader/bootloader.bin',build/'partition_table/partition-table.bin',
       build/'flasher_args.json',project/'sdkconfig',build/'CMakeCache.txt',build/'compile_commands.json',
       project/'main/preprocessing.h',project/'main/signal.cpp',project/'main/test_data/ecg_test_metadata.h']
manifest=dict(status='BUILD_ARTIFACT_CHECKS_PASS_NOT_HARDWARE_PASS',mode='ADC',cpu_MHz=160,
              threshold=.88,output_code_min=98,reference_kernels=True,flash=False,
              hardware_confirmation_complete=False,files=[dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,
              sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
target=Path(__file__).with_name('adc_build_manifest.json')
with target.open('x') as f: json.dump(manifest,f,indent=2)
print(target)
