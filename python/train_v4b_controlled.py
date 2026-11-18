import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,random,math,hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
from run_v10_step0_step1 import build_v4_baseline,CheckpointAPSelector,compute_metrics,select_threshold_on_cal_fold
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v4/v4b_hard_example_training';STEP=ROOT/'results/v10_research/step1_5fold_cv';CACHE=ROOT/'results/cnn_v4/qrs_verification_v4a'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else x))
def assign(ref,p):
 used=set();match=np.full(len(ref),-1,int)
 for ri,t in enumerate(ref):
  cand=[int(j) for j in np.flatnonzero(abs(p-t)<=38) if int(j) not in used]
  if cand:j=min(cand,key=lambda j:abs(p[j]-t));match[ri]=j;used.add(j)
 return match,used
class Weighted(tf.keras.utils.Sequence):
 def __init__(self,x,y,w,seed):
  super().__init__();self.x=x;self.y=y;self.w=w;self.seed=seed;self.epoch=0;self.on_epoch_end()
 def __len__(self):return math.ceil(len(self.y)/128)
 def on_epoch_end(self):self.epoch+=1;self.order=np.random.default_rng(self.seed+self.epoch).permutation(len(self.y))
 def __getitem__(self,k):
  j=self.order[k*128:(k+1)*128];return self.x[j],self.y[j],self.w[j]
def load():
 mit=np.load(ROOT/'data/processed/mitbih_nv_250hz.npz');sp=np.load(ROOT/'data/processed/mitbih_split_indices.npz');inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz')
 mi=np.concatenate([sp['train_indices'],sp['validation_indices']]);ii=np.flatnonzero(np.isin(inc['split'],['train','validation']))
 return np.concatenate([mit['X'][mi],inc['X'][ii]]),np.concatenate([mit['y'][mi],inc['y'][ii]]),np.concatenate([mit['record_ids'][mi].astype(str),inc['patient_ids'][ii].astype(str)]),np.array(['MITBIH']*len(mi)+['INCART']*len(ii))
def masks(spec,g,d):
 return {role:((d=='MITBIH')&np.isin(g,spec[f'{key}_MITBIH_records']))|((d=='INCART')&np.isin(g,spec[f'{key}_INCART_patients'])) for role,key in [('Fit','fit'),('Checkpoint','checkpoint'),('Calibration','threshold'),('Evaluation','outer')]}
def evaluate_e2e(model,threshold,spec):
 rows=[]
 for p in sorted(CACHE.glob('*_features.npz')):
  ds,rec=p.stem.replace('_features','').split('_',1)
  # authoritative record-to-group map from retained Train+Development header metadata
  group=rec if ds=='MITBIH' else GROUPS[rec]
  if group not in spec['outer_MITBIH_records' if ds=='MITBIH' else 'outer_INCART_patients']:continue
  cache=OUT/f'fold{spec["fold_index"]}_{model.name}_{ds}_{rec}_prediction.npz'
  z=np.load(p);peaks=z['peaks'];ref=z['ref'];symbols=z['symbols'];rawfile=OUT/'detector_windows'/f'{ds}_{rec}.npy'
  if not rawfile.exists():raise RuntimeError('Missing prepared detector windows')
  x=np.load(rawfile,mmap_mode='r')
  if cache.exists():scores=np.load(cache)['scores']
  else:scores=model.predict(x,batch_size=512,verbose=0).ravel();np.savez_compressed(cache,peaks=peaks,scores=scores)
  pred=scores>=threshold;match,used=assign(ref,peaks);tp=fp=fn=tn=mn=mv=0
  for i,c in enumerate(symbols):
   if c not in {'N','V'}:continue
   if match[i]<0:fn+=int(c=='V');mn+=int(c=='N');mv+=int(c=='V');continue
   pr=pred[match[i]];tp+=int(c=='V' and pr);fp+=int(c=='N' and pr);fn+=int(c=='V' and not pr);tn+=int(c=='N' and not pr)
  fpn=fp;fpx=sum(int(pred[j]) for j in range(len(peaks)) if j not in used);fp+=fpx
  rows.append(dict(dataset=ds,record=rec,group=group,TP=tp,FP=fp,FN=fn,TN=tn,N=int(sum(symbols=='N')),V=int(sum(symbols=='V')),missingN=mn,missingV=mv,extra_peaks=len(peaks)-len(used),FP_matched_N=fpn,FP_unmatched_alarm=fpx))
 return rows
def agg(a):
 v={k:sum(int(x[k]) for x in a) for k in ['TP','FP','FN','TN','N','V','missingN','missingV','extra_peaks','FP_matched_N','FP_unmatched_alarm']};p=v['TP']/(v['TP']+v['FP']) if v['TP']+v['FP'] else 0;r=v['TP']/(v['TP']+v['FN']) if v['TP']+v['FN'] else 0
 v.update(precision=p,recall=r,f1=2*p*r/(p+r) if p+r else 0,fp_per_1000_N=v['FP']*1000/v['N'] if v['N'] else 0);return v
def prepare_windows():
 import wfdb
 from scipy.signal import resample_poly
 dest=OUT/'detector_windows';dest.mkdir(exist_ok=True)
 for p in sorted(CACHE.glob('*_features.npz')):
  ds,rec=p.stem.replace('_features','').split('_',1);out=dest/f'{ds}_{rec}.npy'
  if out.exists():continue
  base=ROOT/('files' if ds=='INCART' else 'mit-bih-arrhythmia-database-1.0.0')/rec;h=wfdb.rdheader(str(base));ch=[s.strip().upper() for s in h.sig_name].index('II' if ds=='INCART' else 'MLII');sig=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],250 if ds=='INCART' else 25,257 if ds=='INCART' else 36);raw=np.clip(np.rint(2048+200*sig),0,4095);peaks=np.load(p)['peaks'];w=np.stack([raw[j-128:j+128] for j in peaks]).astype(np.float32);assert np.isfinite(w).all() and np.all(w.std(1)>1e-8);np.save(out,((w-w.mean(1,keepdims=True))/np.maximum(w.std(1,keepdims=True),1e-8))[:,:,None])
def main():
 global GROUPS
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'checkpoints').mkdir(exist_ok=True)
 if (OUT/'evaluation.json').exists():raise RuntimeError('Completed experiment exists')
 folds=json.loads((STEP/'folds_split.json').read_text());prior=json.loads((STEP/'cv_evaluation.json').read_text())
 plan={'architecture':'V4 849 params, no RR; original V4 untouched','seed':42,'fold_seed':'42+1000*k','folds_sha256':sha(STEP/'folds_split.json'),'baseline':'Reuse exact Step1 V4 checkpoints trained on identical Fit/Checkpoint groups,seed,BCE,classweights,Adam.001,batch128,max20,patience5,no augmentation; source training metadata recorded, historical runtime environment incomplete','hard_mining':'baseline best model scores on Fit only, NOT OOF; within each class select top10% loss (positive1-score,negative score), deterministic stable ties','weighting':'2x for hard Fit examples then normalize within class; multiply original Fit class weight; equivalent weighted exposure ~18.18% hard per class','loss':'binary_crossentropy','augmentation':False,'epochs':20,'patience':5,'batch':128,'threshold':'same baseline grid .05.. .95 step.01 max combined Calibration PVC F1, tie precision then smaller threshold','single_factor':'class-balanced Fit hardness weighting; no independent attribution to positive vs negative arms','passing_rule':'both mean fold end-to-end F1 >= baseline; INC mean Recall increases; MIT mean Recall drop<=1pp; each mean FP/1000N increase <=max(1,10% baseline); worst fold F1 not worse on either dataset; >=60% patient/record groups with PVC have F1 drop<=2pp','evaluation_limit':'Previously examined Train+Development; no Test; folds separate Fit/Checkpoint/Calibration/outer for each run; exploratory adaptive validation'}
 if (OUT/'config.json').exists():assert json.loads((OUT/'config.json').read_text())==plan
 else:write(OUT/'config.json',plan)
 tf.config.threading.set_inter_op_parallelism_threads(1);tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.experimental.enable_op_determinism()
 x,y,g,d=load();inc=np.load(ROOT/'data/processed/incart_v4_250hz.npz');ix=np.flatnonzero(np.isin(inc['split'],['train','validation']));inc_records=inc['record_ids'];inc_patients=inc['patient_ids'];GROUPS={str(inc_records[j]):str(inc_patients[j]) for j in ix};prepare_windows();foldrows=[]
 for spec in folds:
  k=spec['fold_index'];completed=OUT/f'fold{k}.json';bp=STEP/f'checkpoints/v4_fold{k}_best.keras';priorrow=next(v for v in prior['models']['V4']['folds'] if v['fold_index']==k);assert sha(bp)==priorrow['checkpoint_sha256'];path=OUT/f'checkpoints/v4b_fold{k}_best.keras';meta=OUT/f'fold{k}_training.json'
  if completed.exists():row=json.loads(completed.read_text());assert row['v4b_sha256']==sha(path);foldrows.append(row);print('fold',k,'cached',flush=True);continue
  m=masks(spec,g,d);assert np.all(sum(v.astype(int) for v in m.values())==1)
  base=tf.keras.models.load_model(bp,compile=False);fit=m['Fit'];cp=m['Checkpoint'];cal=m['Calibration'];ev=m['Evaluation'];counts=np.bincount(y[fit],minlength=2);cw=len(y[fit])/(2*counts)
  if meta.exists():training=json.loads(meta.read_text());assert training['sha256']==sha(path)
  else:
   if path.exists():raise RuntimeError('Partial training checkpoint is not full resume state; do not silently restart')
   score=base.predict(x[fit],batch_size=512,verbose=0).ravel();labels=y[fit];hard=np.zeros(len(labels),bool);mining={};weights=cw[labels].astype(np.float32)
   for label in [0,1]:
    at=np.flatnonzero(labels==label);difficulty=1-score[at] if label else score[at];pick=at[np.argsort(-difficulty,kind='stable')[:int(np.ceil(.1*len(at)))]];hard[pick]=True;factor=np.where(hard[at],2.,1.);factor/=factor.mean();weights[at]*=factor;mining[str(label)]={'Fit_samples':len(at),'hard_samples':len(pick),'mean_hard_baseline_score':float(score[pick].mean())}
   np.savez_compressed(OUT/f'fold{k}_Fit_mining.npz',global_indices=np.flatnonzero(fit),hard=hard,baseline_scores=score,labels=labels,weights=weights)
   tf.keras.backend.clear_session();seed=42+k*1000;random.seed(seed);np.random.seed(seed);tf.keras.utils.set_random_seed(seed);model=build_v4_baseline(f'v4b_fold{k}');model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy');selector=CheckpointAPSelector(x[cp],y[cp],path)
   model.fit(Weighted(x[fit],y[fit],weights,seed),epochs=20,verbose=0,callbacks=[selector,tf.keras.callbacks.TerminateOnNaN()]);training={'sha256':sha(path),'best_epoch':selector.best_epoch,'epochs_run':len(selector.history),'history':selector.history,'mining':mining};write(meta,training)
  model=tf.keras.models.load_model(path,compile=False);row={'fold_index':k,'baseline_sha256':sha(bp),'v4b_sha256':sha(path),'training':training,'CNN_only':{},'end_to_end':{}}
  # Both Calibration thresholds frozen before evaluating outer groups.
  thresholds={}
  for name,network in [('V4',base),('V4-B',model)]:
   sc=network.predict(x[cal],batch_size=512,verbose=0).ravel();thresholds[name]=select_threshold_on_cal_fold(y[cal],sc)['threshold']
  assert abs(thresholds['V4']-priorrow['calibrated_threshold'])<1e-9,'Baseline calibration differs; stop rather than change protocol'
  row['thresholds']=thresholds;write(OUT/f'fold{k}_locked.json',{'sha256':sha(path),'thresholds':thresholds,'training':training})
  for name,network in [('V4',base),('V4-B',model)]:
   row['CNN_only'][name]={};scores=network.predict(x[ev],batch_size=512,verbose=0).ravel()
   for ds in ['MITBIH','INCART']:
    keep=d[ev]==ds;row['CNN_only'][name][ds]=compute_metrics(y[ev][keep],scores[keep],thresholds[name])
   row['end_to_end'][name]=evaluate_e2e(network,thresholds[name],spec)
  write(completed,row);foldrows.append(row);print('fold',k,'complete thresholds',thresholds,flush=True)
 result={'config':plan,'folds':foldrows,'summary':{}}
 for mode in ['CNN_only','end_to_end']:
  result['summary'][mode]={}
  for ds in ['MITBIH','INCART']:
   result['summary'][mode][ds]={}
   for name in ['V4','V4-B']:
    values=[v['CNN_only'][name][ds] if mode=='CNN_only' else agg([rr for rr in v['end_to_end'][name] if rr['dataset']==ds]) for v in foldrows]
    result['summary'][mode][ds][name]={'mean':{key:float(np.mean([a[key] for a in values])) for key in ['precision','recall','f1','fp_per_1000_N' if mode=='end_to_end' else 'fp_per_1000_normal']},'std_f1':float(np.std([a['f1'] for a in values])),'worst_fold_f1':min(a['f1'] for a in values),'per_fold':values}
 write(OUT/'evaluation.json',result);print(json.dumps(result['summary']['end_to_end'],indent=2))
if __name__=='__main__':main()
