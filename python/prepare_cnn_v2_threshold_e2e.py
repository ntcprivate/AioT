"""Frozen detector2B replay on only the six Train-development records."""
from pathlib import Path
import sys,json,subprocess,hashlib
import numpy as np
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/ecg_monitor'))
from audit_r_peaks import assignment,rows_from,BEATS
BASE=ROOT/'results/cnn_v2';OUT=BASE/'threshold_review';FW=ROOT/'firmware/esp32_ecg_tinyml_integrated'
def main():
    selection=json.loads((OUT/'selection.json').read_text());cfg=json.loads((BASE/'config.json').read_text())
    exe=FW/'debug/r_peak_phase2b/replay.exe';xx=[];yy=[];ids=[];records=[]
    assert selection['records']==cfg['development_records'] and not set(cfg['development_records'])&set(cfg['fit_records'])
    for rid in cfg['development_records']:
        path=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid;header=wfdb.rdheader(str(path));ch=[s.strip().upper() for s in header.sig_name].index('MLII')
        adc=np.clip(np.rint(2048+200*resample_poly(wfdb.rdrecord(str(path),channels=[ch]).p_signal[:,0],25,36)),0,4095).astype('<i2')
        adc_path=OUT/f'{rid}_adc.bin';adc.tofile(adc_path)
        p=subprocess.run([str(exe),str(adc_path),str(OUT/f'{rid}_candidates.bin'),str(OUT/f'{rid}_safe.bin')],capture_output=True,check=True)
        (OUT/f'{rid}_events.csv').write_bytes(p.stdout);rows=rows_from(p.stdout.decode())
        centers=np.array([int(r[1]) for r in rows if r[0]=='safe_peak'],dtype=np.int64)
        a=wfdb.rdann(str(path),'atr');mask=np.array([s in BEATS for s in a.symbol]);refs=(a.sample[mask]*25+18)//36;symbols=np.array(a.symbol)[mask]
        matches,fp=assignment(refs,centers);raw=np.fromfile(OUT/f'{rid}_safe.bin',dtype='<f4').reshape(-1,256);assert len(raw)==len(centers)
        labels=np.full(len(raw),-2,dtype=np.int32)
        for j,k in enumerate(matches):
            if k>=0:labels[k]=0 if symbols[j]=='N' else 1 if symbols[j]=='V' else -1
        norm=raw.astype(float);norm=((norm-norm.mean(axis=1,keepdims=True))/np.maximum(norm.std(axis=1,keepdims=True),1e-8)).astype(np.float32)
        xx.append(norm[:,:,None]);yy.append(labels);ids.extend([rid]*len(raw))
        row=dict(record=rid,reference_N=int(sum(symbols=='N')),reference_V=int(sum(symbols=='V')),miss_N=int(sum((symbols=='N')&(matches<0))),miss_V=int(sum((symbols=='V')&(matches<0))),windows=len(raw),unmatched=len(fp))
        records.append(row);print(row,flush=True)
    np.savez_compressed(OUT/'development_e2e_windows.npz',X=np.concatenate(xx),y=np.concatenate(yy),ids=np.array(ids))
    (OUT/'development_e2e_metadata.json').write_text(json.dumps(dict(records=records,threshold_frozen_before_replay=selection['selected_threshold'],replay_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),protocol='Same Phase2B safe replay, MLII,25/36 resampling,ADC2048+200*mV,round-half-up annotation,greedy tolerance12,same V1 input clipping preflight; host mirror not RTOS/hardware'),indent=2))
if __name__=='__main__':main()
