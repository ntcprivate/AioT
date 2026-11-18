import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,subprocess,hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
import wfdb
from scipy.signal import resample_poly
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/model_improvement/next_direction_analysis';BEATS=set('NLRBAaJSVrFejnE/fQ?');CACHE=ROOT/'results/cnn_v4/qrs_verification_v4a'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else x))
def match(ref,p):
 used=set();m=np.full(len(ref),-1,int)
 for ri,t in enumerate(ref):
  a=[int(j) for j in np.flatnonzero(abs(p-t)<=38) if int(j) not in used]
  if a:j=min(a,key=lambda j:abs(p[j]-t));m[ri]=j;used.add(j)
 return m,used
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if (OUT/'evaluation.json').exists():raise RuntimeError('Complete artifacts exist')
 plan=json.loads((CACHE/'design.json').read_text());config={'groups':plan['groups'],'partition':'Reuse frozen V4-A Fit/Calibration/Evaluation; no new parameter selection. Older research exposed these records; many Evaluation groups were in CNN Fit, so not independent model validation.','hypotheses':['A: center morphology/window-neighbor contrast differs between rescued PVC and newly false-positive N','B: missed PVC examples can define Train-only candidates, with hard-negative N protection','C: fixed diagnostic OR at unchanged thresholds .88/.87/.80 quantifies real rescue/FP tradeoff; not an oracle or chosen cascade'],'thresholds':{'V4':.88,'V6':.87,'V11':.80},'feature_definitions':'central128 half-amplitude support, not clinical QRS duration; PTP; current detector RR; window correlation with previous detector window; central/context energy ratio; fixed scores','no_Test':True}
 write(OUT/'plan_locked.json',config)
 fw=ROOT/'firmware/esp32_ecg_tinyml_integrated';exe=OUT/'stage_probe.exe';subprocess.run(['g++','-std=c++17','-O2','-I',str(fw/'main'),'-I',str(fw/'tests'),str(fw/'main/signal.cpp'),str(ROOT/'python/rr_recall_stage_probe.cpp'),'-o',str(exe)],check=True)
 lock=json.loads((ROOT/'results/cnn_v11/final_test/locked.json').read_text());mean=np.asarray(lock['rr_fit_mean']);sd=np.asarray(lock['rr_fit_std'])
 tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2)
 m6=tf.keras.models.load_model(ROOT/'models/v6/ecg_cnn_v6_best.keras',compile=False);m11=tf.keras.models.load_model(ROOT/'models/v11/v11_final_best.keras',compile=False)
 inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');rows=[];beats=[]
 for role in ['Fit','Calibration','Evaluation']:
  for file in sorted(CACHE.glob('*_features.npz')):
   ds,rec=file.stem.replace('_features','').split('_',1);group=rec if ds=='MITBIH' else str(inc['patient_ids'][np.flatnonzero(inc['record_ids']==rec)[0]])
   if group not in config['groups'][role][ds]:continue
   out=OUT/f'{ds}_{rec}_paired.npz';z=np.load(file);peaks=z['peaks'];s4=z['scores'];ref=z['ref'];symbols=z['symbols']
   base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ch=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII');sig=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*sig),0,4095).astype('<i2')
   stage=OUT/f'{ds}_{rec}_stage.csv'
   if not stage.exists():
    raw.tofile(OUT/'input.bin')
    with stage.open('w') as f:subprocess.run([str(exe),str(OUT/'input.bin')],stdout=f,check=True)
   ev=[s.split(',') for s in stage.read_text().splitlines()];accepted=np.asarray([int(v[1]) for v in ev if v[0]=='candidate']);emitted=np.asarray([int(v[1]) for v in ev if v[0]=='window']);np.testing.assert_array_equal(peaks,emitted)
   w=np.stack([raw[p-128:p+128] for p in peaks]).astype(np.float32);std=w.std(1,keepdims=True);valid=np.isfinite(w).all(1)&(std[:,0]>1e-8);assert valid.all();x=((w-w.mean(1,keepdims=True))/np.maximum(std,1e-8))[:,:,None]
   dRR=np.r_[1.,np.diff(peaks)/250.];rr=[]
   for j in range(len(peaks)):
    history=np.diff(peaks[max(0,j-8):j+1])/250.;current=history[-1] if len(history) else 1.;prior=history[:-1];median=float(np.median(prior)) if len(prior) else 1.;rr.append([current,median,current/max(median,1e-8),min(len(history),8)/8])
   if out.exists():q=np.load(out);np.testing.assert_array_equal(q['peaks'],peaks);s6=q['s6'];s11=q['s11']
   else:
    s6=m6.predict(x,batch_size=512,verbose=0).ravel();s11=m11.predict({'ecg_256':x,'rr_features':(np.asarray(rr)-mean)/sd},batch_size=512,verbose=0).ravel();np.savez_compressed(out,peaks=peaks,s4=s4,s6=s6,s11=s11)
   p4=s4>=.88;p6=s6>=.87;p11=s11>=.80;ma,used=match(ref,peaks);mc,_=match(ref,accepted)
   row=dict(dataset=ds,record=rec,group=group,role=role,reference_V=int(sum(symbols=='V')),v4_FN_detector=0,v4_FN_window=0,v4_FN_CNN=0,v4_FN_other=0,PVC_matched=0,PVC_v4miss_v6rescue=0,PVC_v4miss_v11rescue=0,PVC_v4miss_bothrescue=0,N_v4correct_v6FP=0,N_v4correct_v11FP=0,PVC_all_wrong=0,N_all_wrong=0,or11_extra_FP=0,or6_extra_FP=0)
   for ri,c in enumerate(symbols):
    if c not in {'N','V'}:continue
    j=ma[ri]
    if j<0:
     if c=='V':
      key='v4_FN_detector' if mc[ri]<0 else ('v4_FN_window' if accepted[mc[ri]] not in set(peaks) else 'v4_FN_other');row[key]+=1
     continue
    if c=='V':
     row['PVC_matched']+=1;row['v4_FN_CNN']+=int(not p4[j]);row['PVC_v4miss_v6rescue']+=int(not p4[j] and p6[j]);row['PVC_v4miss_v11rescue']+=int(not p4[j] and p11[j]);row['PVC_v4miss_bothrescue']+=int(not p4[j] and p6[j] and p11[j]);row['PVC_all_wrong']+=int(not(p4[j] or p6[j] or p11[j]))
    else:
     row['N_v4correct_v6FP']+=int(not p4[j] and p6[j]);row['N_v4correct_v11FP']+=int(not p4[j] and p11[j]);row['N_all_wrong']+=int(p4[j] and p6[j] and p11[j])
    central=x[j,64:192,0];a=abs(central-np.median(central));width=float(sum(a>=.5*max(a))*4);corr=float(np.corrcoef(x[j,:,0],x[j-1,:,0])[0,1]) if j and std[j-1,0]>1e-8 else 0.
    tag='other'
    if c=='V' and not p4[j] and p11[j]:tag='V4_missed_PVC_V11_rescued'
    elif c=='N' and not p4[j] and p11[j]:tag='V4_correct_N_V11_false_positive'
    elif c=='V' and not p4[j] and p6[j]:tag='V4_missed_PVC_V6_rescued'
    elif c=='N' and not p4[j] and p6[j]:tag='V4_correct_N_V6_false_positive'
    elif c=='V' and not(p4[j] or p6[j] or p11[j]):tag='PVC_all_wrong'
    beats.append(dict(dataset=ds,record=rec,group=group,role=role,symbol=c,center=int(peaks[j]),tag=tag,central_ptp_z=float(np.ptp(central)),half_support_ms=width,RR=float(dRR[j]),previous_window_correlation=corr,central_energy_ratio=float(z['ratio'][j]),center_offset=int(peaks[j]-ref[ri]),s4=float(s4[j]),s6=float(s6[j]),s11=float(s11[j])))
   extra=[j for j in range(len(peaks)) if j not in used];row['or11_extra_FP']=row['N_v4correct_v11FP']+sum(not p4[j] and p11[j] for j in extra);row['or6_extra_FP']=row['N_v4correct_v6FP']+sum(not p4[j] and p6[j] for j in extra);rows.append(row);print(role,ds,rec,'done',flush=True)
 result={'plan':config,'records':rows,'summary':{},'feature_summary':{}}
 for role in config['groups']:
  result['summary'][role]={}
  for ds in ['MITBIH','INCART']:
   a=[r for r in rows if r['role']==role and r['dataset']==ds];result['summary'][role][ds]={k:sum(int(r[k]) for r in a) for k in a[0] if k not in ['dataset','record','group','role']}
  result['feature_summary'][role]={}
  for ds in ['MITBIH','INCART']:
   result['feature_summary'][role][ds]={}
   for tag in sorted(set(b['tag'] for b in beats)):
    a=[b for b in beats if b['role']==role and b['dataset']==ds and b['tag']==tag]
    if a:result['feature_summary'][role][ds][tag]={'n':len(a),**{k:{'q25':float(np.percentile([v[k] for v in a],25)),'median':float(np.median([v[k] for v in a])),'q75':float(np.percentile([v[k] for v in a],75))} for k in ['central_ptp_z','half_support_ms','RR','previous_window_correlation','central_energy_ratio','center_offset','s4','s6','s11']}}
 write(OUT/'evaluation.json',result);write(OUT/'beat_diagnostics.json',beats);print(json.dumps(result['summary']['Evaluation'],indent=2))
if __name__=='__main__':main()
