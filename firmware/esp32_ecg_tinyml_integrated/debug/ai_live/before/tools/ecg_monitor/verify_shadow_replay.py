"""Frozen Train208 smoke replay; no tuning, Test set or serial access."""
import csv,json,subprocess,hashlib
from pathlib import Path
import numpy as np
import wfdb
from audit_r_peaks import assignment
from validate_offline import BEATS
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/research_shadow'
def main():
    assert '208' in json.loads((FW/'debug/r_peak_phase2b/development_plan.json').read_text())['records']
    raw=FW/'debug/r_peak_phase2b/development_208.bin';model=FW/'main/model/ecg_cnn_int8.tflite';base=OUT/'train208'
    commands=[[OUT/'replay.exe',raw,base,15000],
        [FW/'debug/r_peak_phase2b/int8_fixed_host/full_chain.exe',model,OUT/'train208.q.bin',OUT/'train208.native.bin','--batch'],
        [ROOT/'tools/ecg_monitor/.venv_reference/Scripts/python.exe',ROOT/'tools/ecg_monitor/validate_reference.py',model,OUT/'train208.q.bin',OUT/'train208.tf.bin']]
    for i,cmd in enumerate(commands):
        r=subprocess.run(list(map(str,cmd)),check=True,capture_output=True);(OUT/f'replay_stage{i}.log').write_bytes(r.stdout+r.stderr)
        if i==0:engine=json.loads(r.stdout)
    native=np.fromfile(OUT/'train208.native.bin',dtype=np.int8);tf=np.fromfile(OUT/'train208.tf.bin',dtype=np.int8)
    assert np.array_equal(native,tf)
    rows=list(csv.DictReader((OUT/'train208.csv').open()));centers=np.array([int(r['r_index']) for r in rows])
    a=wfdb.rdann(str(ROOT/'mit-bih-arrhythmia-database-1.0.0/208'),'atr')
    ref=(a.sample*25+18)//36;symbols=np.array(a.symbol);mask=(ref<15000)&np.isin(symbols,list(BEATS));ref=ref[mask];symbols=symbols[mask]
    matches,unmatched=assignment(ref,centers);cm=np.zeros((2,2),dtype=int);miss={'N':0,'V':0};errors=[]
    for r,j,label in zip(ref,matches,symbols):
        if label not in ('N','V'):continue
        if j<0:miss[label]+=1;continue
        pred=int(native[j]>=6);truth=int(label=='V');cm[truth,pred]+=1
        if pred!=truth:errors.append(dict(annotation_index=int(r),detected_index=int(centers[j]),true=label,predicted='PVC' if pred else 'NORMAL',code=int(native[j])))
    report=dict(**engine,record='208',native_tf_exact=int(sum(native==tf)),predicted_N=int(sum(native<6)),predicted_PVC=int(sum(native>=6)),physical_ESP32=False,
        input_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),annotation_rounding='(sample*25+18)//36',tolerance_samples=12,
        reference_NV=int(sum(np.isin(symbols,['N','V']))),matched_NV_confusion_rows_N_V=cm.tolist(),missed_NV_before_CNN=miss,
        unmatched_detected=len(unmatched),other_reference=int(sum(~np.isin(symbols,['N','V']))),classification_errors=errors,
        scope='HOST_REFERENCE_REPLAY first60seconds of frozen Train208; smoke checks, not independent accuracy or parameter selection')
    (OUT/'replay_results.json').write_text(json.dumps(report,indent=2));print('Replay:',len(native),'EXACT; confusion',cm.tolist(),'missed',miss)
if __name__=='__main__':main()
