"""Compile actual bundled TFLM reference kernel under both rounding modes."""
import json
from pathlib import Path
import subprocess
PROJECT=Path(__file__).resolve().parent.parent
component=PROJECT/'managed_components/espressif__esp-tflite-micro'
common=component/'tensorflow/lite/micro/kernels/internal/common.cc'
results=[]
for mode in (0,1):
    exe=PROJECT/f'tests/conv_kernel_mode{mode}.exe'
    command=['g++','-std=c++17','-O2','-DNDEBUG','-DTF_LITE_STATIC_MEMORY',f'-DTFLITE_SINGLE_ROUNDING={mode}',
             '-I'+str(component),'-I'+str(component/'third_party/flatbuffers/include'),
             str(PROJECT/'tests/conv_kernel_test.cpp'),str(common),'-o',str(exe)]
    subprocess.run(command,check=True)
    result=subprocess.run([str(exe)],check=True,text=True,capture_output=True)
    print(result.stdout,end='');results.append({'mode':mode,'exit_code':result.returncode,'output':result.stdout})
(PROJECT/'debug/conv_host_results.json').write_text(json.dumps(results,indent=2))
