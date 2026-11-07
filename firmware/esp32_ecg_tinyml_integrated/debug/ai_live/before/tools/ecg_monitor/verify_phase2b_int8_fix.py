"""Actual fixed adapter regression:12golden,9425fixed,33586extended and all8 operator traces."""
import hashlib,json,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';BASE=FW/'debug/r_peak_phase2b';OUT=BASE/'int8_fixed_checks'
def main():
    OUT.mkdir(exist_ok=True);exe=BASE/'int8_fixed_host/full_chain.exe';model=FW/'main/model/ecg_cnn_int8.tflite'
    gold=OUT/'golden';gold.mkdir(exist_ok=True)
    p=subprocess.run([str(exe),str(model),str(FW/'main/test_data/ecg_test_samples_int8.bin'),str(gold)],capture_output=True,check=True)
    (OUT/'golden.log').write_bytes(p.stdout+p.stderr);assert p.stdout.count(b'exact=1 repeats=33 stable=1')==12 and b'failed=0' in p.stdout
    result=dict(golden_samples=12,repeats=33,model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
        adapter_sha256=hashlib.sha256((FW/'main/single_round_fc.cpp').read_bytes()).hexdigest(),native_exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    for tag,q,ref in [('fixed9425',BASE/'parity/input_int8.bin',BASE/'parity/reference_codes.bin'),('extended33586',BASE/'2b_all_q.bin',BASE/'2b_tf_codes.bin')]:
        native=OUT/f'{tag}_codes.bin';subprocess.run([str(exe),str(model),str(q),str(native),'--batch'],check=True,capture_output=True)
        a=np.fromfile(native,dtype=np.int8);b=np.fromfile(ref,dtype=np.int8);assert a.shape==b.shape
        result[tag]=dict(windows=len(a),mismatched_codes=int(np.sum(a!=b)),classification_disagreements=int(np.sum((a>=6)!=(b>=6))),input_sha256=hashlib.sha256(q.read_bytes()).hexdigest())
        assert result[tag]['mismatched_codes']==0
    traces=[]
    for case in json.loads((BASE/'int8_diagnosis/operator_comparison.json').read_text()):
        folder=BASE/'int8_diagnosis'/case['id'];fixed=folder/'fixed';fixed.mkdir(exist_ok=True)
        subprocess.run([str(exe),str(model),str(folder/'input.bin'),str(fixed),'--inspect'],check=True,capture_output=True)
        counts=[int(np.sum(np.fromfile(fixed/f'op{o}.bin',dtype=np.int8)!=np.fromfile(folder/f'tf_op{o}.bin',dtype=np.int8))) for o in range(16)]
        assert not any(counts);traces.append(dict(id=case['id'],operator_mismatches=counts))
    result['traces']=traces;result['status']='PASS_EXACT';(OUT/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='traces'},indent=2))
if __name__=='__main__':main()
