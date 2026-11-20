"""Read recorded UART only; no inference or device access."""
from pathlib import Path
import json,re,zlib,struct
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
out=Path(__file__).resolve().parent
root=out.parents[3]
a=json.loads((out/'analysis.json').read_text())
fig,axes=plt.subplots(2,1,figsize=(12,6),constrained_layout=True)
extra=[]
for ax,rec in zip(axes,a['records'][:2]):
    sm={}
    for ln in (root/'tools/ecg_monitor/captures'/rec['file']).read_bytes().splitlines():
        m=re.fullmatch(rb'ECG1 ([0-9a-fA-F]{8}) (.*)',ln.strip())
        if not m or zlib.crc32(m[2])!=int(m[1],16):continue
        f=json.loads(m[2])
        if f['type']=='samples':
            for i,(dt,v,flag) in enumerate(struct.iter_unpack('<IHB',bytes.fromhex(f['data']))):
                sm[f['first']+i]=(f['t0']+dt,v,flag)
    bs=[b for b in a['beats'] if b['file']==rec['file'] and b['rejected']=='0']
    start=int(bs[0]['r_us'])-512000
    rows=[r for _,r in sorted(sm.items()) if start<=r[0]<=start+2500000]
    x=np.array([r[1] for r in rows],dtype=float)
    ax.plot([(r[0]-start)/1e6 for r in rows],x,lw=1)
    for b in bs:
        t=(int(b['r_us'])-start)/1e6
        if 0<=t<=2.5:ax.axvline(t,color='tab:red',alpha=.65,ls='--')
    ax.set(title=rec['file']+'; dashed = detector peaks (not ground truth)',xlabel='Seconds from excerpt start',ylabel='ADC raw')
    ax.grid(alpha=.2)
    # Descriptive autocorrelation, not a new quality or classification rule.
    extra.append(dict(file=rec['file'],autocorrelation_lag40_160ms=float(np.corrcoef(x[:-40],x[40:])[0,1]),
                      autocorrelation_lag80_320ms=float(np.corrcoef(x[:-80],x[80:])[0,1])))
fig.savefig(out/'recorded_windows.png',dpi=150)
(out/'periodicity.json').write_text(json.dumps(extra,indent=2))
print(json.dumps(extra,indent=2))
