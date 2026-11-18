"""Read-only analysis of saved predictions; no model loading/inference."""
import json,hashlib
from pathlib import Path
import numpy as np
import wfdb
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v11/pre_esp32_audit';SRC=ROOT/'results/cnn_v11/final_test'
BEATS=set('NLRBAaJSVrFejnE/fQ?')
def main():
 OUT.mkdir(exist_ok=True,parents=True);saved=json.loads((SRC/'evaluation.json').read_text());rows=[]
 for recrow in saved['records']:
  ds=recrow['dataset'];rec=recrow['record'];z=np.load(SRC/f'{ds}_{rec}_detector.npz');peaks=z['peaks'];pred=z['scores']>=.8
  base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));a=wfdb.rdann(str(base),'atr')
  refs=[(int(np.floor(s*250/h.fs+.5)),c) for s,c in zip(a.sample,a.symbol) if c in BEATS];used=set();pairs={};errs=[]
  for ri,(t,c) in enumerate(refs):
   cand=[int(j) for j in np.flatnonzero(abs(peaks-t)<=38) if int(j) not in used]
   if cand:j=min(cand,key=lambda j:abs(peaks[j]-t));used.add(j);pairs[ri]=j;errs.append(int(peaks[j]-t))
  nfp=[j for ri,j in pairs.items() if refs[ri][1]=='N' and pred[j]];extras=[j for j in range(len(peaks)) if j not in used];xfp=[j for j in extras if pred[j]]
  other=[j for ri,j in pairs.items() if refs[ri][1] not in {'N','V'}];dist=np.array([min(abs(t-peaks[j]) for t,c in refs) for j in xfp])
  off=np.load(SRC/f'{ds}_{rec}_offline.npz');refnv=[(t,c) for t,c in refs if c in {'N','V'} and t>=128 and t+128<=int(np.ceil(h.sig_len*250/h.fs))];offline_map={}
  if len(refnv)==len(off['y']):
   assert np.array_equal([int(c=='V') for t,c in refnv],off['y'])
   offline_map={t:float(s) for (t,c),s in zip(refnv,off['scores'])}
  flips=sum(refs[ri][0] in offline_map and offline_map[refs[ri][0]]<.8 for ri,j in pairs.items() if refs[ri][1]=='N' and pred[j])
  rr=np.diff(peaks)/250.;row={'dataset':ds,'record':rec,'FP':recrow['detector']['FP'],'FP_matched_N':len(nfp),'FP_unmatched_alarm':len(xfp),'extra_peaks':len(extras),'unmatched_alarm_within_75_samples':int(sum(dist<=75)),'matched_OTHER':len(other),'OTHER_predicted_PVC_excluded':int(sum(pred[j] for j in other)),'N_FP_offline_correct_detector_wrong':int(flips),'timing_abs_p95_samples':float(np.percentile(abs(np.array(errs)),95)),'duplicate_centers':len(peaks)-len(set(peaks)),'rr_under_300ms':int(sum(rr<.3)),'rr_over_2seconds':int(sum(rr>2))}
  assert row['FP']==row['FP_matched_N']+row['FP_unmatched_alarm'];rows.append(row)
 result={'records':rows,'totals':{}}
 for ds in ['MITBIH','INCART']:
  a=[r for r in rows if r['dataset']==ds];result['totals'][ds]={k:sum(r[k] for r in a) for k in ['FP','FP_matched_N','FP_unmatched_alarm','extra_peaks','unmatched_alarm_within_75_samples','matched_OTHER','OTHER_predicted_PVC_excluded','N_FP_offline_correct_detector_wrong','duplicate_centers']}
 parse=lambda p:np.array([int(v[1]) for s in p.read_text().splitlines() if (v:=s.split(','))[0]=='peak'])
 result['validation_trace_agreement']={rec:bool(np.array_equal(parse(ROOT/f'results/cnn_v11/rr_detector_validation/MITBIH_{rec}.csv'),parse(ROOT/f'results/cnn_v11/paper_rpeak_verification/{rec}_hold50.csv'))) for rec in ['115','118','121','210','214','233','234']}
 lock=saved['locked'];part=lock['partition']
 result['fit_development_overlap']={ds:sorted(set(lock['fit_groups'][ds])&set(part['MITBIH_checkpoint_records']+part['MITBIH_threshold_records'] if ds=='MITBIH' else part['INCART_checkpoint_patients']+part['INCART_threshold_patients'])) for ds in ['MITBIH','INCART']}
 inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
 result['incart_record_patients']={r['record']:str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==r['record'])[0]]) for r in rows if r['dataset']=='INCART'}
 (OUT/'analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['totals'],indent=2));print(json.dumps({k:result[k] for k in ['validation_trace_agreement','fit_development_overlap','incart_record_patients']},indent=2))
 for ds in ['MITBIH','INCART']:
  print(ds,'TOP',json.dumps(sorted([r for r in rows if r['dataset']==ds],key=lambda r:r['FP'],reverse=True)[:4]))
if __name__=='__main__':main()
