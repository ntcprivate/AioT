"""Actual TFLM interpreter/kernels on host, original model/golden, two modes.

esp_timer stub provides time only; no operator or quantization implementation
is replaced. Host interpreter preserves tensors for inspection, not firmware.
"""
import concurrent.futures
import json
from pathlib import Path
import subprocess
PROJECT=Path(__file__).resolve().parent.parent
COMPONENT=PROJECT/'managed_components/espressif__esp-tflite-micro'
MICRO=COMPONENT/'tensorflow/lite/micro'
core=['debug_log','flatbuffer_conversions','flatbuffer_utils','memory_helpers','micro_allocation_info','micro_allocator',
      'micro_common','micro_context','micro_interpreter_context','micro_interpreter_graph','micro_interpreter',
      'micro_log','micro_op_resolver','micro_profiler','micro_resource_variable','micro_time','micro_utils',
      'recording_micro_allocator','system_setup']
sources=[MICRO/(n+'.cc') for n in core]
sources+=list((MICRO/'arena_allocator').glob('*.cc'))+list((MICRO/'memory_planner').glob('*.cc'))
sources+=[MICRO/'kernels'/ (n+'.cc') for n in ['conv_common','fully_connected_common','logistic_common','pooling_common','reduce_common','kernel_util','expand_dims','reshape']]
sources+=[MICRO/'kernels/esp_nn'/(n+'.cc') for n in ['conv','fully_connected','logistic','pooling','reduce']]
sources+=[MICRO/'kernels/internal'/(n+'.cc') for n in ['common','portable_tensor_utils','quantization_util','runtime_shape','tensor_ctypes']]
sources+=[PROJECT/'tests/full_chain_host.cpp']
sources+=[MICRO/'kernels/reshape_common.cc']
results=[]
reference=json.loads((PROJECT/'debug/python_operator_reference.json').read_text())
for mode in (0,2):
    folder=PROJECT/f'debug/host_mode{mode}';folder.mkdir(parents=True,exist_ok=True)
    flags=['g++','-std=c++17','-O2','-DNDEBUG','-DECG_HOST_TEST=1','-DTF_LITE_STATIC_MEMORY','-DTFLITE_SINGLE_ROUNDING=0',f'-DECG_CONV_SINGLE_ROUNDING={int(mode==2)}',
           '-I'+str(PROJECT/'tests/host_stubs'),'-I'+str(PROJECT/'main'),'-I'+str(COMPONENT),
           '-I'+str(COMPONENT/'third_party/flatbuffers/include'),'-ffunction-sections','-fdata-sections']
    def compile_source(pair):
        i,source=pair;obj=folder/f'{i}.o'
        p=subprocess.run(flags+['-c',str(source),'-o',str(obj)],capture_output=True,text=True)
        if p.returncode:raise RuntimeError(str(source)+'\n'+p.stderr)
        return obj
    mode_sources=sources+([PROJECT/'main/single_round_conv.cpp',PROJECT/'main/single_round_fc.cpp'] if mode==2 else [])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        objects=list(pool.map(compile_source,enumerate(mode_sources)))
    exe=folder/'full_chain.exe'
    subprocess.run(['g++',*[str(o) for o in objects],'-Wl,--gc-sections','-o',str(exe)],check=True)
    p=subprocess.run([str(exe),str(PROJECT/'main/model/ecg_cnn_int8.tflite'),str(PROJECT/'main/test_data/ecg_test_samples_int8.bin'),str(folder)],capture_output=True,text=True)
    print(p.stdout,end='');print(p.stderr)
    if p.returncode:raise RuntimeError(f'Host mode{mode} failed, code={p.returncode}')
    rows=[]
    for e in reference['operators']:
        actual=(folder/f'op{e["op"]}.bin').read_bytes();expected=bytes.fromhex(e['hex'])
        if len(actual)!=len(expected):raise ValueError('Tensor size mismatch')
        rows.append({'op':e['op'],'tag':e['tag'],'mismatches':sum(a!=b for a,b in zip(actual,expected))})
    if mode==2 and any(r['mismatches'] for r in rows):raise ValueError('Conv-only single rounding full chain not exact')
    results.append({'mode':mode,'host_output':p.stdout,'sample5_operators':rows,'scope':'HOST, not ESP32 hardware'})
(PROJECT/'debug/full_host_results.json').write_text(json.dumps(results,indent=2))
