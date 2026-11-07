"""Syntax-only cross-compiler check using known Step 8 include paths/config.

This does not configure/link/build this firmware or certify its sdkconfig.
Run from any directory with host Python. No old project files are written.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import re

project=Path(__file__).resolve().parent.parent
reference=project.parent/'esp32_tinyml_step8/build/compile_commands.json'
entries=json.loads(reference.read_text())
entry=next(e for e in entries if e['file'].replace('\\','/').endswith('/main/main.cpp'))
command=entry['command'].split(' -o ',1)[0]
adc_entries=json.loads((project.parent/'esp32_ad8232_adc_test/build/compile_commands.json').read_text())
adc_entry=next(e for e in adc_entries if e['file'].replace('\\','/').endswith('/main/main.cpp'))
# ADC drivers are not dependencies of Step 8; add their known cached include paths.
command+=' '+' '.join(re.findall(r'-I"[^"]+"|-I[^\s"]+',adc_entry['command']))
config=(project/'tests/sdkconfig.h').read_text()
results=[]
with tempfile.TemporaryDirectory(prefix='ecg_syntax_') as temp:
    header=Path(temp)/'integration_config.h'
    for mode in (0,1):
        header.write_text(config+f'\n#define CONFIG_ECG_ENABLE_EXPERIMENTAL_LIVE {mode}\n#define CONFIG_ECG_GOLDEN_ALERT_DEMO {mode}\n#define CONFIG_ECG_HARDWARE_SELF_TEST {mode}\n#define ECG_REFERENCE_KERNELS_ACTIVE 1\n#define TFLITE_SINGLE_ROUNDING 0\n#define ECG_CONV_SINGLE_ROUNDING 1\n')
        for source in ('main.cpp','pipeline.cpp','model.cpp','signal.cpp','single_round_conv.cpp'):
            invocation=(command+f' -I"{project / "main"}" -include "{header}" -fsyntax-only "{project / "main" / source}"')
            result=subprocess.run(invocation,cwd=entry['directory'],capture_output=True,text=True)
            results.append({'file':source,'experimental_live':mode,'exit_code':result.returncode,'output':result.stdout+result.stderr})
            print(source,mode,result.returncode,result.stdout+result.stderr)
(project/'tests/xtensa_syntax_results.json').write_text(json.dumps(results,indent=2))
raise SystemExit(0 if all(r['exit_code']==0 for r in results) else 1)
