"""Compare actual Conv adapter math to bundled TFLM single-round helper."""
from pathlib import Path
import subprocess
PROJECT=Path(__file__).resolve().parent.parent
c=PROJECT/'managed_components/espressif__esp-tflite-micro'
exe=PROJECT/'tests/requantization_test.exe'
subprocess.run(['g++','-std=c++17','-O2','-DNDEBUG','-DTFLITE_SINGLE_ROUNDING=1','-DTF_LITE_STATIC_MEMORY',
    '-I'+str(c),'-I'+str(c/'third_party/flatbuffers/include'),str(PROJECT/'tests/requantization_test.cpp'),
    str(c/'tensorflow/lite/micro/kernels/internal/common.cc'),'-o',str(exe)],check=True)
p=subprocess.run([str(exe)],check=True,text=True,capture_output=True)
print(p.stdout,end='')
(PROJECT/'debug/requantization_host_result.txt').write_text(p.stdout)
