"""Rerun fixed9425 Validation component corpus and golden12, without overwriting old artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/r_peak_phase2a/parity'
def run(args,log):
    p=subprocess.run([str(x) for x in args],capture_output=True,check=True)
    log.write_bytes(p.stdout+p.stderr)
    return p.stdout.decode(errors='replace')
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=ROOT/'tools/ecg_monitor/reports/offline/detected_windows_f32.bin'
    raw=np.fromfile(source,dtype='<f4').reshape(-1,256);assert raw.shape==(9425,256)
    model=FW/'main/model/ecg_cnn_int8.tflite';chain=FW/'debug/host_mode2/full_chain.exe'
    golden=run([chain,model,FW/'main/test_data/ecg_test_samples_int8.bin',OUT/'golden_operators'],OUT/'golden.log')
    assert golden.count('exact=1 repeats=33 stable=1')==12 and 'failed=0' in golden
    qpath=OUT/'input_int8.bin';run([OUT.parent/'preprocess_host.exe',source,qpath],OUT/'preprocessing.log')
    double=raw.astype(np.float64)
    z=((double-double.mean(axis=1,keepdims=True))/double.std(axis=1,keepdims=True)).astype(np.float32)
    expected=np.clip(np.rint(z.astype(np.float64)/np.float32(.053921569138765335))-27,-128,127).astype(np.int8)
    actual_q=np.fromfile(qpath,dtype=np.int8).reshape(-1,256);mismatch=int(np.count_nonzero(actual_q!=expected))
    run([chain,model,qpath,OUT/'native_codes.bin','--batch'],OUT/'native.log')
    run([ROOT/'tools/ecg_monitor/.venv_reference/Scripts/python.exe',ROOT/'tools/ecg_monitor/validate_reference.py',model,qpath,OUT/'reference_codes.bin'],OUT/'tensorflow.log')
    native=np.fromfile(OUT/'native_codes.bin',dtype=np.int8);reference=np.fromfile(OUT/'reference_codes.bin',dtype=np.int8)
    assert native.shape==reference.shape==(9425,)
    code_mismatch=int(np.count_nonzero(native!=reference));assert mismatch==code_mismatch==0
    report=dict(status='PASS',scope='Fixed9425 matched Validation windows from phase1; not detector end-to-end accuracy',
        golden_samples=12,repeats_each=33,golden_exact=True,parity_beats=9425,preprocessing_mismatched_bytes=mismatch,cnn_mismatched_codes=code_mismatch,
        corpus_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
    (OUT/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
