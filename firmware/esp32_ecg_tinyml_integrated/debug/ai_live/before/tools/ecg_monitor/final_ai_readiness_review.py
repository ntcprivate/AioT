"""Analysis only: cached errors, Train controls, paired centering/ADC counterfactuals.
Never trains, tunes, reads Test signals/predictions, changes firmware or opens COM.
"""
from collections import Counter,defaultdict
import csv,hashlib,json,subprocess
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly
from audit_r_peaks import assignment,rows_from,BEATS
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';BASE=FW/'debug/r_peak_phase2b';FIXED=BASE/'fixed_validation';OUT=FW/'debug/final_ai_readiness'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def features(raw):
    a=np.asarray(raw,dtype=float);std=a.std(axis=1);z=(a-a.mean(axis=1,keepdims=True))/np.maximum(std[:,None],1e-8)
    baseline=np.median(np.concatenate((a[:,:32],a[:,-32:]),axis=1),axis=1)
    central=a[:,103:154]-baseline[:,None];amplitude=np.max(abs(central),axis=1)
    location=np.argmax(abs(central),axis=1);signed=central[np.arange(len(a)),location]
    return dict(ptp=np.ptp(a,axis=1),std=std,width_proxy_ms=np.sum(abs(central)>=amplitude[:,None]*.5,axis=1)*4,
        polarity=np.where(signed>=0,1,-1),strongest_offset_ms=(np.argmax(abs(z),axis=1)-128)*4,
        center_energy_fraction=np.sum(z[:,103:154]**2,axis=1)/np.sum(z*z,axis=1),z_ptp=np.ptp(z,axis=1))
def summ(rows):
    if not rows:return dict(n=0)
    out=dict(n=len(rows),records=dict(Counter(r['record'] for r in rows)))
    for key in ('ptp','std','width_proxy_ms','strongest_offset_ms','center_energy_fraction','z_ptp','center_error_ms','p_pvc'):
        values=np.array([r[key] for r in rows],dtype=float);out[key]=dict(p10=float(np.percentile(values,10)),median=float(np.median(values)),p90=float(np.percentile(values,90)))
    out.update(negative_polarity=sum(r['polarity']<0 for r in rows),neighbor_pvc=sum(r['neighbor_pvc']>0 for r in rows),neighbor_beats=dict(Counter(r['neighbor_beats'] for r in rows)),
        zero_center_error=sum(r['center_error_ms']==0 for r in rows),center_error_bins=dict(Counter('0ms' if r['center_error_ms']==0 else '4..16ms' if abs(r['center_error_ms'])<=16 else '20..48ms' for r in rows)))
    return out
def main():
    OUT.mkdir(exist_ok=True)
    protected=list((FW/'main').rglob('*'))+[FW/'sdkconfig',FW/'debug/sdkconfig.synthetic_test',ROOT/'data/processed/mitbih_split_indices.npz',ROOT/'data/processed/mitbih_nv_250hz.npz',ROOT/'results/optimized_threshold.json',FW/'docs/r_peak_detector_phase2b.md',FW/'debug/r_peak_phase2b_results.json']
    before={str(p.relative_to(ROOT)):sha(p) for p in protected if p.is_file()};(OUT/'before_sha256.json').write_text(json.dumps(before,indent=2))
    previous=json.loads((FW/'debug/r_peak_phase2b_results.json').read_text(encoding='utf-8'))
    codes=np.fromfile(FIXED/'2b_all_codes.bin',dtype=np.int8);all_q=np.fromfile(FIXED/'2b_all_q.bin',dtype=np.int8).reshape(-1,256)
    offset=0;rows=[];misses=[];false_alarms=[];adc_gold=[];mv_gold=[];refs_by_record={}
    for rid in previous['records']:
        original=np.load(FW/f'debug/r_peak_audit/{rid}_detections.npz');refs=original['reference'];symbols=original['symbols'];refs_by_record[rid]=(refs,symbols)
        events=rows_from((FIXED/f'2b_{rid}_events.csv').read_text());cand=np.array([int(r[1]) for r in events if r[0]=='peak']);safe=np.array([int(r[1]) for r in events if r[0]=='safe_peak'])
        candidate_matches,_=assignment(refs,cand);matches,fp=assignment(refs,safe)
        candidate_arrivals={int(r[1]):int(r[2]) for r in events if r[0]=='peak'}
        abstain=np.array([int(r[1]) for r in events if r[0]=='safe_abstain']);abstain_match={}
        for center in abstain:
            j=int(np.argmin(abs(refs-center)))
            if abs(refs[j]-center)<=12:abstain_match[j]=int(center)
        offset+=len(cand);raw=np.fromfile(FIXED/f'2b_{rid}_safe_windows.bin',dtype='<f4').reshape(-1,256);p=(codes[offset:offset+len(safe)].astype(float)+128)/256
        q=all_q[offset:offset+len(safe)];offset+=len(safe)
        double=raw.astype(float);z=((double-double.mean(axis=1,keepdims=True))/double.std(axis=1,keepdims=True)).astype(np.float32)
        unclipped=np.rint(z.astype(float)/np.float32(.053921569138765335))-27
        np.testing.assert_array_equal(np.clip(unclipped,-128,127).astype(np.int8),q);assert not np.any((unclipped<-128)|(unclipped>127))
        f=features(raw);adc=np.fromfile(FW/f'debug/r_peak_audit/{rid}_adc.bin',dtype='<i2')
        base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid;header=wfdb.rdheader(str(base));ch=[s.strip().upper() for s in header.sig_name].index('MLII')
        mv=resample_poly(wfdb.rdrecord(str(base),channels=[ch]).p_signal[:,0],25,36)
        for j,(center,label) in enumerate(zip(refs,symbols)):
            if label not in ('N','V'):continue
            k=int(matches[j])
            if k<0:
                candk=int(candidate_matches[j]);candidate_center=int(cand[candk]) if candk>=0 else None
                if candk<0:reason='detector_miss'
                elif j in abstain_match:reason='quantization_clipping_direct'
                elif candidate_arrivals[candidate_center]>=len(adc)//256*256:reason='incomplete_final_quality_block'
                elif candidate_center<755:reason='initial_quality_admission_and_detector_warmup'
                else:reason='safety_reset_recovery_or_changed_history'
                misses.append(dict(record=rid,label=str(label),annotation_sample=int(center),reason=reason,candidate_center=candidate_center));continue
            assert center>=128 and center+128<=len(adc)
            row=dict(record=rid,label=str(label),annotation_sample=int(center),detected_sample=int(safe[k]),center_error_ms=int(safe[k]-center)*4,
                p_pvc=float(p[k]),predicted='V' if p[k]>=.52 else 'N',neighbor_beats=int(np.sum((refs>=safe[k]-128)&(refs<safe[k]+128)))-1,
                neighbor_pvc=int(np.sum((refs>=safe[k]-128)&(refs<safe[k]+128)&(symbols=='V')))-int(label=='V'))
            row.update({key:float(value[k]) if key not in ('polarity',) else int(value[k]) for key,value in f.items()});rows.append(row)
            adc_gold.append(adc[center-128:center+128].astype('<f4'));mv_gold.append(mv[center-128:center+128].astype('<f4'))
        for k in fp:
            if p[k]<.52:continue
            j=int(np.argmin(abs(refs-safe[k])))
            false_alarms.append(dict(record=rid,center=int(safe[k]),p_pvc=float(p[k]),nearest_label=str(symbols[j]),nearest_annotation=int(refs[j]),offset_ms=int(safe[k]-refs[j])*4,nearest_reference_missed=bool(matches[j]<0)))
    assert offset==len(codes);assert sum(r['label']=='N' and r['predicted']=='V' for r in rows)==428
    assert sum(r['label']=='V' and r['predicted']=='N' for r in rows)==136
    assert len(misses)==90 and len(false_alarms)==21
    # Paired diagnostic inference on all matched N/V, not just errors; no tuning/selection.
    raw_cf=np.concatenate((np.stack(adc_gold),np.stack(mv_gold)));raw_path=OUT/'annotation_counterfactual_raw.bin';raw_cf.tofile(raw_path)
    q_path=OUT/'annotation_counterfactual_q.bin';subprocess.run([str(BASE/'preprocess_host.exe'),str(raw_path),str(q_path)],check=True)
    code_path=OUT/'annotation_counterfactual_codes.bin';subprocess.run([str(BASE/'int8_fixed_host/full_chain.exe'),str(FW/'main/model/ecg_cnn_int8.tflite'),str(q_path),str(code_path),'--batch'],check=True)
    ref_path=OUT/'annotation_counterfactual_tf.bin';p=subprocess.run([str(ROOT/'tools/ecg_monitor/.venv_reference/Scripts/python.exe'),str(ROOT/'tools/ecg_monitor/validate_reference.py'),str(FW/'main/model/ecg_cnn_int8.tflite'),str(q_path),str(ref_path)],capture_output=True,check=True)
    (OUT/'counterfactual_reference.log').write_bytes(p.stdout+p.stderr)
    cf=np.fromfile(code_path,dtype=np.int8);tf=np.fromfile(ref_path,dtype=np.int8);assert np.array_equal(cf,tf)
    n=len(rows);assert len(cf)==2*n
    double=raw_cf.astype(float);zn=((double-double.mean(1,keepdims=True))/double.std(1,keepdims=True)).astype(np.float32)
    uq=np.rint(zn.astype(float)/np.float32(.053921569138765335))-27;cf_valid=~np.any((uq<-128)|(uq>127),axis=1)
    for i,r in enumerate(rows):
        r['p_annotation_adc']=float((int(cf[i])+128)/256);r['p_annotation_mv']=float((int(cf[n+i])+128)/256)
        r['annotation_adc_valid']=bool(cf_valid[i]);r['annotation_mv_valid']=bool(cf_valid[n+i])
        r['pred_annotation_adc']=('V' if r['p_annotation_adc']>=.52 else 'N') if cf_valid[i] else 'ABSTAIN'
        r['pred_annotation_mv']=('V' if r['p_annotation_mv']>=.52 else 'N') if cf_valid[n+i] else 'ABSTAIN'
    groups={}
    for label in ('N','V'):
        for wrong in (False,True):groups[label+('_wrong' if wrong else '_correct')]=summ([r for r in rows if r['label']==label and (r['predicted']!=label)==wrong])
    per_record=[]
    for rid in previous['records']:
        r=[x for x in rows if x['record']==rid];per_record.append(dict(record=rid,N=len([x for x in r if x['label']=='N']),V=len([x for x in r if x['label']=='V']),
            N_to_V=sum(x['label']=='N' and x['predicted']=='V' for x in r),V_to_N=sum(x['label']=='V' and x['predicted']=='N' for x in r),
            N_to_V_annotation_adc=sum(x['label']=='N' and x['pred_annotation_adc']=='V' for x in r),V_to_N_annotation_adc=sum(x['label']=='V' and x['pred_annotation_adc']=='N' for x in r)))
    cf_result={}
    for label in ('N','V'):
        subset=[r for r in rows if r['label']==label];wrong=[r for r in subset if r['predicted']!=label];correct=[r for r in subset if r['predicted']==label]
        cf_result[label]=dict(original_errors=len(wrong),recovered_by_annotation_center=sum(r['pred_annotation_adc']==label for r in wrong),
            persistent_at_annotation_center=sum(r['pred_annotation_adc'] not in (label,'ABSTAIN') for r in wrong),new_errors_from_annotation_center=sum(r['pred_annotation_adc'] not in (label,'ABSTAIN') for r in correct),
            annotation_adc_errors=sum(r['pred_annotation_adc'] not in (label,'ABSTAIN') for r in subset),annotation_mv_errors=sum(r['pred_annotation_mv'] not in (label,'ABSTAIN') for r in subset),
            annotation_adc_abstained=sum(r['pred_annotation_adc']=='ABSTAIN' for r in subset),annotation_mv_abstained=sum(r['pred_annotation_mv']=='ABSTAIN' for r in subset),
            adc_vs_mv_decision_differences=sum(r['pred_annotation_adc']!=r['pred_annotation_mv'] for r in subset if 'ABSTAIN' not in (r['pred_annotation_adc'],r['pred_annotation_mv'])),
            wrong_despite_exact_original_center=sum(r['center_error_ms']==0 for r in wrong),high_confidence_wrong=sum(r['p_pvc']>=.9 if label=='N' else r['p_pvc']<=.1 for r in wrong),
            near_threshold_wrong=sum(abs(r['p_pvc']-.52)<=.05 for r in wrong))
    # Train evidence: replay cached selected candidate without retuning, locate analogue failures.
    train_cases=[];train_reference=[];train_records=['105','106','114','119','208','219']
    for rid in train_records:
        path=BASE/f'development_{rid}.bin';adc=np.fromfile(path,dtype='<i2');ann=wfdb.rdann(str(ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid),'atr');mask=np.array([s in BEATS for s in ann.symbol]);refs=(ann.sample[mask]*25+18)//36;syms=np.asarray(ann.symbol)[mask]
        p=subprocess.run([str(BASE/'replay.exe'),str(path),str(OUT/f'train_{rid}_unused_windows.bin'),str(OUT/f'train_{rid}_unused_safe.bin')],capture_output=True,text=True,check=True)
        events=rows_from(p.stdout);det=np.array([int(r[1]) for r in events if r[0]=='peak']);matches,fp=assignment(refs,det)
        for k in fp:
            j=int(np.argmin(abs(refs-det[k])));train_cases.append(dict(record=rid,fp_sample=int(det[k]),nearest_reference=int(refs[j]),offset_ms=int(det[k]-refs[j])*4,nearest_missed=bool(matches[j]<0)))
        nv=[int(c) for c,s in zip(refs,syms) if s in ('N','V') and c>=128 and c+128<=len(adc)]
        f=features(np.stack([adc[c-128:c+128] for c in nv]));labels=[str(s) for c,s in zip(refs,syms) if s in ('N','V') and c>=128 and c+128<=len(adc)]
        for i,label in enumerate(labels):train_reference.append(dict(record=rid,label=label,**{key:float(v[i]) for key,v in f.items()}))
    with np.load(ROOT/'data/processed/mitbih_split_indices.npz',allow_pickle=False) as parts,np.load(ROOT/'data/processed/mitbih_nv_250hz.npz',allow_pickle=False) as dataset:
        y=dataset['y'];ids=dataset['record_ids'];split={}
        for name in ('train','validation','test'):
            idx=parts[name+'_indices'];split[name]=dict(samples=len(idx),N=int(np.sum(y[idx]==0)),V=int(np.sum(y[idx]==1)),records=sorted(set(ids[idx].tolist())))
        sets={k:set(parts[k+'_indices'].tolist()) for k in split};record_sets={k:set(v['records']) for k,v in split.items()}
        disjoint=all(not sets[a]&sets[b] and not record_sets[a]&record_sets[b] for a,b in [('train','validation'),('train','test'),('validation','test')]);assert disjoint
        idx=parts['train_indices'];X=dataset['X'][idx,:,0];f=features(X);train_shapes={}
        for label,value in [('N',0),('V',1)]:
            keep=y[idx]==value;train_shapes[label]={key:dict(p10=float(np.percentile(v[keep],10)),median=float(np.median(v[keep])),p90=float(np.percentile(v[keep],90))) for key,v in f.items() if key not in ('ptp','std')}
    train_amp={label:{key:float(np.median([r[key] for r in train_reference if r['label']==label])) for key in ('ptp','std','width_proxy_ms')} for label in ('N','V')}
    report=dict(scope='Analysis only; counterfactual diagnostic inference on matched Validation; no Test signal/inference, no training/tuning',
        matched_NV=n,per_record=per_record,groups=groups,counterfactual=cf_result,counterfactual_parity=dict(windows=len(cf),mismatches=0),
        misses_by_label_reason={label:dict(Counter(r['reason'] for r in misses if r['label']==label)) for label in ('N','V')},
        unmatched_pvc_by_record=dict(Counter(r['record'] for r in false_alarms)),train_error_pattern=dict(total_fp=len(train_cases),nearest_reference_missed=sum(r['nearest_missed'] for r in train_cases),
            preceding_within300ms=sum(r['nearest_missed'] and -300<=r['offset_ms']<0 for r in train_cases)),
        train_raw_six_record_medians=train_amp,train_normalized_shape=train_shapes,split=split,split_index_and_record_disjoint=disjoint,
        feature_limits='width_proxy is count of central samples above half residual amplitude, NOT clinical QRS width; polarity/neighbor/context associations are not causal; scores are uncalibrated',
        protected_checks={name:sha(ROOT/name)==value for name,value in before.items()},no_code_fix=True,ai_live_unlocked=False,test_inference=False)
    assert all(report['protected_checks'].values())
    dump(OUT/'matched_cases.csv',rows);dump(OUT/'pre_cnn_misses.csv',misses);dump(OUT/'unmatched_pvc_alerts.csv',false_alarms);dump(OUT/'train_false_peaks.csv',train_cases)
    (OUT/'evidence.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(per_record=per_record,counterfactual=cf_result,misses=report['misses_by_label_reason'],train_pattern=report['train_error_pattern']),indent=2))
if __name__=='__main__':main()
