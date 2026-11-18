import json,subprocess,hashlib
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=ROOT/'results/cnn_v11/paper_rpeak_verification'
BEATS=set('NLRBAaJSVrFejnE/fQ?')
def match(ref,peaks,tol):
 used=set();errors=[];counts={};miss={}
 for t,c in ref:
  at=int(np.searchsorted(peaks,t));cand=[j for j in (at-1,at) if 0<=j<len(peaks) and j not in used and abs(peaks[j]-t)<=tol]
  if not cand:miss[c]=miss.get(c,0)+1;continue
  j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);errors.append(int(peaks[j]-t));counts[c]=counts.get(c,0)+1
 return dict(TP=len(used),FP=len(peaks)-len(used),FN=len(ref)-len(used),matched_symbols=counts,missed_symbols=miss,median_abs_error_samples=float(np.median(abs(np.array(errors)))),duplicates=int(len(peaks)-len(set(peaks))))
def main():
 OUT.mkdir(parents=True,exist_ok=True);source=(FW/'main/signal.cpp').read_text();rows=[]
 for hold in [50,58]:
  src=OUT/f'hold{hold}.cpp'
  # Emit experiment source through apply_patch, never modify production source.
  content=source.replace('sample-candidate_start_>=50',f'sample-candidate_start_>={hold}')
  patch='*** Begin Patch\n*** Add File: '+str(src)+'\n'+''.join('+'+line+'\n' for line in content.splitlines())+'*** End Patch\n'
  if not src.exists():raise RuntimeError('Prepare reconstructed source with apply_patch before running')
  assert src.read_text().replace('\r\n','\n').strip()==content.strip()
  exe=OUT/f'hold{hold}.exe';subprocess.run(['g++','-std=c++17','-O2','-I',str(FW/'main'),'-I',str(FW/'tests'),str(src),str(FW/'tests/detector_phase2b_replay.cpp'),'-o',str(exe)],check=True)
  for rec in ['115','118','121','210','214','233','234']:
   base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rec;h=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr');ch=[s.strip().upper() for s in h.sig_name].index('MLII')
   sig=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],25,36);raw=np.clip(np.rint(2048+200*sig),0,4095).astype('<i2');raw.tofile(OUT/'input.bin')
   log=OUT/f'{rec}_hold{hold}.csv'
   with log.open('w') as f:subprocess.run([str(exe),str(OUT/'input.bin'),str(OUT/'windows.bin'),str(OUT/'safe.bin')],stdout=f,check=True)
   peaks=np.array([int(v[1]) for line in log.read_text().splitlines() if (v:=line.split(','))[0]=='peak']);ref=[((int(s)*25+18)//36,c) for s,c in zip(ann.sample,ann.symbol) if c in BEATS]
   rows.append(dict(record=rec,hold=hold,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),original_sha256={ext:hashlib.sha256(base.with_suffix(ext).read_bytes()).hexdigest() for ext in ['.hea','.dat','.atr']},tol12=match(ref,peaks,12),tol38=match(ref,peaks,38)))
 result={'scope':'original Validation data replay; hold58 reconstructed from current V11 source, paper source unavailable','records':rows,'totals':{}}
 for hold in [50,58]:
  for tol in [12,38]:
   a=[r[f'tol{tol}'] for r in rows if r['hold']==hold];v={k:sum(r[k] for r in a) for k in ['TP','FP','FN']};v['sensitivity']=v['TP']/(v['TP']+v['FN']);v['ppv']=v['TP']/(v['TP']+v['FP']);result['totals'][f'hold{hold}_tol{tol}']=v
 (OUT/'evaluation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['totals'],indent=2))
if __name__=='__main__':main()
