"""Add verified TEST_ONLY assets; never alter original model or golden reference."""
import hashlib,json,re,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/esp32_ai_test_only';ASSETS=FW/'main/test_only'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ASSETS.mkdir(exist_ok=True)
    source=(FW/'main/test_data/ecg_test_metadata.h').read_text();gold=re.findall(r'\{(\d+), "(\d+)", (\d+), (-?\d+), [^,]+, (\d+)\}',source);assert len(gold)==12
    with np.load(ROOT/'data/processed/mitbih_nv_250hz.npz') as d,np.load(ROOT/'data/processed/mitbih_split_indices.npz') as s:
        indices=[int(g[0]) for g in gold];assert np.isin(indices,s['validation_indices']).all();raw=[d['X'][i,:,0].astype('<f4') for i in indices]
    original=(FW/'main/test_data/ecg_test_samples_int8.bin').read_bytes();assert len(original)==3072
    cases=[dict(id=f'golden{i}',record=g[1],label=int(g[2]),symbol='V' if int(g[2]) else 'N',code=int(g[3]),dataset_index=int(g[0])) for i,g in enumerate(gold)]
    diagnosis=FW/'debug/r_peak_phase2b/int8_diagnosis';expanded=np.fromfile(FW/'debug/r_peak_phase2b/fixed_validation/2b_all_raw.bin',dtype='<f4').reshape(-1,256)
    q=[]
    for c in json.loads((diagnosis/'operator_comparison.json').read_text()):
        raw.append(expanded[c['index']]);q.append((diagnosis/c['id']/'input.bin').read_bytes())
        cases.append(dict(id='fc14_'+c['id'],record=c['record'],label=0 if c['symbol']=='N' else 1 if c['symbol']=='V' else -1,symbol=c['symbol'],code=c['tensorflow'],center=c['center']))
    raw_path=ASSETS/'ai_test_raw.bin';np.stack(raw).astype('<f4').tofile(raw_path);ext=ASSETS/'ai_test_extended_int8.bin';ext.write_bytes(b''.join(q))
    prepared=OUT/'generated_input_int8.bin';subprocess.run([str(FW/'debug/r_peak_phase2b/preprocess_host.exe'),str(raw_path),str(prepared)],check=True)
    assert prepared.read_bytes()==original+ext.read_bytes(),'Preprocessing must reproduce references exactly; do not repair fixtures'
    tfcodes=OUT/'fixture_tf_codes.bin';run=subprocess.run([str(ROOT/'tools/ecg_monitor/.venv_reference/Scripts/python.exe'),str(ROOT/'tools/ecg_monitor/validate_reference.py'),str(FW/'main/model/ecg_cnn_int8.tflite'),str(prepared),str(tfcodes)],capture_output=True,check=True);(OUT/'fixture_tf.log').write_bytes(run.stdout+run.stderr)
    assert np.array_equal(np.fromfile(tfcodes,dtype=np.int8),[c['code'] for c in cases])
    h=['// TEST_ONLY fixtures from preserved real Validation assets; not live ECG.','#pragma once','#include <cstddef>',f'constexpr size_t kAiTestCount={len(cases)};',f'constexpr char kAiTestRawSha[]="{sha(raw_path)}";',f'constexpr char kAiTestExtendedSha[]="{sha(ext)}";','struct AiTestCase {const char* id;const char* record;int label;char symbol;int code;};','constexpr AiTestCase kAiTestCases[kAiTestCount]={']
    h += [f'  {{"{c["id"]}","{c["record"]}",{c["label"]},\'{c["symbol"]}\',{c["code"]}}},' for c in cases];h+=['};'];(ASSETS/'ai_test_metadata.h').write_text('\n'.join(h)+'\n')
    manifest=dict(cases=cases,raw_sha256=sha(raw_path),extended_sha256=sha(ext),model_sha256=sha(FW/'main/model/ecg_cnn_int8.tflite'),original_golden_sha256=sha(FW/'main/test_data/ecg_test_samples_int8.bin'),preprocessing_exact=True,tensorflow_cases=20)
    (OUT/'fixture_manifest.json').write_text(json.dumps(manifest,indent=2));print('20 verified fixtures:12 preserved golden +8 unique FC14 cases; preprocessing/TF EXACT')
if __name__=='__main__':main()
