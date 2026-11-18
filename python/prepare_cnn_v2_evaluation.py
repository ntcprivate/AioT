"""Reuse frozen Phase2B windows/events and matching, no detector rerun or Test."""
from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools/ecg_monitor'))
from audit_r_peaks import assignment,rows_from
from cnn_v2_common import metrics
FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';BASE=FW/'debug/r_peak_phase2b/fixed_validation';OUT=ROOT/'results/cnn_v2'
def main():
    report=json.loads((BASE/'evaluation.json').read_text());old=report['2b']['end_to_end']['safe_mirror']
    oldcodes=np.fromfile(BASE/'2b_all_codes.bin',dtype=np.int8);offset=0;xx=[];yy=[];hh=[];rr=[];cc=[];meta=[]
    for rid in report['records']:
        z=np.load(FW/f'debug/r_peak_audit/{rid}_detections.npz');refs=z['reference'];symbols=z['symbols']
        events=rows_from((BASE/f'2b_{rid}_events.csv').read_text());candidate=[r for r in events if r[0]=='peak'];safe=[r for r in events if r[0]=='safe_peak']
        centers=np.array([int(r[1]) for r in safe]);arrivals=np.array([int(r[2]) for r in safe]);offset+=len(candidate)
        codes=oldcodes[offset:offset+len(safe)];offset+=len(safe)
        raw=np.fromfile(BASE/f'2b_{rid}_safe_windows.bin',dtype='<f4').reshape(-1,256)
        a=raw.astype(np.float64);norm=((a-a.mean(axis=1,keepdims=True))/np.maximum(a.std(axis=1,keepdims=True),1e-8)).astype(np.float32)
        matches,fp=assignment(refs,centers);labels=np.full(len(raw),-2,dtype=np.int32);hard=np.zeros(len(raw),dtype=bool)
        for j,k in enumerate(matches):
            if k<0:continue
            labels[k]=0 if symbols[j]=='N' else 1 if symbols[j]=='V' else -1
            hard[k]=symbols[j]=='N' and np.any((refs>=centers[k]-128)&(refs<centers[k]+128)&(symbols=='V'))
        xx.append(norm[:,:,None]);yy.append(labels);hh.append(hard);rr.extend([rid]*len(raw));cc.append(codes)
        meta.append(dict(record=rid,reference_N=int(sum(symbols=='N')),reference_V=int(sum(symbols=='V')),windows=len(raw),miss_N=int(sum((symbols=='N')&(matches<0))),miss_V=int(sum((symbols=='V')&(matches<0))),ready_delay_median_ms=float(np.median((arrivals-centers)*4))))
    X=np.concatenate(xx);y=np.concatenate(yy);hard=np.concatenate(hh);codes=np.concatenate(cc);p=(codes.astype(float)+128)/256;keep=y>=0
    assert metrics(y[keep],p[keep])['confusion_rows_N_V']==old['conditional_confusion_rows_N_V']
    assert sum(r['miss_N'] for r in meta)==66 and sum(r['miss_V'] for r in meta)==24
    assert int(sum((y==-2)&(p>=.52)))==21
    np.savez_compressed(OUT/'cached_validation_windows.npz',X=X,y=y,hard=hard,ids=np.array(rr),v1_int8_scores=p)
    (OUT/'cached_validation_metadata.json').write_text(json.dumps(dict(records=meta,baseline=old,scope='Historical reused Validation; no tuning. Exact original greedy tolerance12, safety-admitted windows; excluded labels explicitly retained.'),indent=2))
    print('Cached windows',len(X),'matched N/V',sum(keep),'baseline exact',metrics(y[keep],p[keep]),flush=True)
if __name__=='__main__':main()
