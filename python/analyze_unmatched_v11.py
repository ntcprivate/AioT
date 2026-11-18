"""Evidence extraction on previously saved Train/Development traces only."""
import json,csv
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/unmatched_peak_analysis';BEATS=set('NLRBAaJSVrFejnE/fQ?')
def main():
 OUT.mkdir(parents=True,exist_ok=True);per=[];cases=[];examples=[]
 split=np.load(ROOT/'data/processed/mitbih_split_indices.npz');mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
 allowedmit=set(mit['record_ids'][np.concatenate([split['train_indices'],split['validation_indices']])]);allowedinc=set(inc['record_ids'][np.isin(inc['split'],['train','validation'])])
 diag=json.loads((ROOT/'results/cnn_v11/rpeak_optimization/diagnosis.json').read_text())
 selected=set((r['dataset'],r['record']) for r in sorted(diag['records'],key=lambda r:r['FP'],reverse=True)[:4])
 selected|=set((r['dataset'],r['record']) for r in sorted([r for r in diag['records'] if r['dataset']=='MITBIH'],key=lambda r:r['FP'],reverse=True)[:2])
 for log in sorted((ROOT/'results/cnn_v11/rr_detector_validation').glob('*.csv')):
  ds,rec=log.stem.split('_',1);assert rec in (allowedmit if ds=='MITBIH' else allowedinc)
  base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');ch=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII')
  sig=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*sig),0,4095)
  refs=np.array([int(np.floor(s*250/h.fs+.5)) for s,c in zip(ann.sample,ann.symbol) if c in BEATS]);syms=[c for c in ann.symbol if c in BEATS]
  events=[line.split(',') for line in log.read_text().splitlines()];peaks=np.array([int(v[1]) for v in events if v[0]=='peak']);used=set();ri_matched=set();other=0
  for ri,t in enumerate(refs):
   cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
   if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);ri_matched.add(ri);other+=int(syms[ri] not in {'N','V'})
  counts={};extra=[j for j in range(len(peaks)) if j not in used]
  for j in extra:
   p=int(peaks[j]);ri=int(np.argmin(abs(refs-p)));distance=int(abs(refs[ri]-p));w=raw[p-128:p+128]
   # Observation categories are not physiological diagnoses.
   if np.any((w<=16)|(w>=4079)):cat='ADC_mapping_rail_in_window'
   elif np.ptp(w)<20:cat='low_ADC_amplitude_window'
   elif distance<=75 and ri in ri_matched:cat='near_already_matched_beat_secondary_or_localization_unresolved'
   elif distance<=75:cat='near_unmatched_reference_timing_compatible_unconfirmed'
   else:cat='far_from_reference_T_P_noise_or_unannotated_unresolved'
   counts[cat]=counts.get(cat,0)+1
   cases.append(dict(dataset=ds,record=rec,center=p,nearest_ref=int(refs[ri]),nearest_symbol=syms[ri],distance_samples=distance,previous_RR_ms=float((p-peaks[j-1])*4) if j else None,next_RR_ms=float((peaks[j+1]-p)*4) if j+1<len(peaks) else None,category=cat,physical_peak_to_peak_mV=float(np.ptp(sig[p-128:p+128])),adc_ptp=float(np.ptp(w))))
  patient=rec if ds=='MITBIH' else str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==rec)[0]])
  quality={}
  for v in events:
   if v[0]=='quality':quality[v[2]]=quality.get(v[2],0)+1
  per.append(dict(dataset=ds,record=rec,patient=patient,reference=len(refs),matched=len(used),missed=len(refs)-len(used),unmatched=len(extra),matched_OTHER=other,duplicate_centers=len(peaks)-len(set(peaks)),categories=counts,logged_block_quality=quality))
  if (ds,rec) in selected and extra:
   j=extra[len(extra)//2];p=int(peaks[j]);start=max(0,p-200);end=min(len(sig),p+200)
   examples.append((ds,rec,p,start,sig[start:end].copy(),refs[(refs>=start)&(refs<end)].copy(),peaks[(peaks>=start)&(peaks<end)].copy()))
 (OUT/'analysis.json').write_text(json.dumps({'scope':'Train+Development only; original greedy matching tolerance38 unchanged; extra categories observational, not expert R/T/P/noise adjudication','records':per},indent=2))
 with (OUT/'peak_cases.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(cases[0]));writer.writeheader();writer.writerows(cases)
 fig,axs=plt.subplots(len(examples),1,figsize=(12,3*len(examples)),squeeze=False)
 for ax,(ds,rec,p,start,sig,refs,peaks) in zip(axs[:,0],examples):
  tt=(np.arange(len(sig))+start-p)/250;ax.plot(tt,sig,lw=.8);ax.axvline(0,color='r',label='unmatched detection')
  for i,t in enumerate(refs):ax.axvline((t-p)/250,color='g',ls='--',label='annotation beat' if i==0 else None)
  for i,t in enumerate(peaks):ax.plot((t-p)/250,sig[int(t-start)],'kx',label='detector' if i==0 else None)
  ax.set_title(f'{ds} {rec}, unmatched center {p}');ax.set_ylabel('mV');ax.legend(loc='upper right',fontsize=7);ax.grid(alpha=.2)
 axs[-1,0].set_xlabel('Seconds relative to unmatched peak');fig.tight_layout();fig.savefig(OUT/'waveform_examples.png',dpi=130);plt.close(fig)
 for ds in ['MITBIH','INCART']:
  a=[r for r in per if r['dataset']==ds];tot={}
  for r in a:
   for k,v in r['categories'].items():tot[k]=tot.get(k,0)+v
  print(ds,'records',len(a),'unmatched',sum(r['unmatched'] for r in a),'matched_OTHER',sum(r['matched_OTHER'] for r in a),tot)
if __name__=='__main__':main()
