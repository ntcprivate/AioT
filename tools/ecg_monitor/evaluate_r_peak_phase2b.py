"""Frozen Validation rules; actual C++ raw windows -> actual preprocessing/native CNN.
Reports matched classification separately from missed beats and unmatched alarms.
"""
from collections import Counter
import hashlib,json,subprocess,time
from pathlib import Path
import numpy as np
from audit_r_peaks import score,assignment,rows_from,summary_metrics
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';BASE=FW/'debug/r_peak_phase2b';OUT=BASE/'fixed_validation'
def run(args,log):
    t=time.perf_counter();p=subprocess.run([str(x) for x in args],capture_output=True,check=True);log.write_bytes(p.stdout+p.stderr)
    return p.stdout.decode(errors='replace'),time.perf_counter()-t
def class_metrics(cm):
    result={}
    for label in (0,1):
        tp=int(cm[label,label]);fp=int(cm[:,label].sum()-tp);fn=int(cm[label,:].sum()-tp)
        result['N' if label==0 else 'V']=dict(precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
            f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,tp=tp,fp=fp,fn=fn)
    return result
def main():
    OUT.mkdir(exist_ok=True)
    previous=json.loads((FW/'debug/r_peak_phase2a_results.json').read_text(encoding='utf-8'));records=previous['records'];report={}
    for stage,exe in [('2a',BASE/'baseline_replay.exe'),('2b',BASE/'replay.exe')]:
        info=[];all_raw=[];offset=0;per_record=[]
        for rid in records:
            z=np.load(FW/f'debug/r_peak_audit/{rid}_detections.npz');path=FW/f'debug/r_peak_audit/{rid}_adc.bin'
            assert hashlib.sha256(path.read_bytes()).hexdigest()==next(r['adc_sha256'] for r in previous['per_record'] if r['record']==rid)
            text,_=run([exe,path,OUT/f'{stage}_{rid}_windows.bin',OUT/f'{stage}_{rid}_safe_windows.bin'],OUT/f'{stage}_{rid}_events.csv')
            rows=rows_from(text);det=np.array([int(r[1]) for r in rows if r[0]=='peak'],dtype=np.int64)
            m=score(z['reference'],det,z['symbols']);per_record.append(dict(record=rid,**m,issues=dict(Counter(r[2] for r in rows if r[0]=='issue')),
                stats=[int(v) for r in rows if r[0]=='stats' for v in r[1:]],quality=dict(Counter(r[2] for r in rows if r[0]=='quality'))))
            if stage=='2a':assert m==next(r['after'] for r in previous['per_record'] if r['record']==rid)
            for mode,tag,suffix in [('candidate','peak','windows'),('safe_mirror','safe_peak','safe_windows')]:
                raw=np.fromfile(OUT/f'{stage}_{rid}_{suffix}.bin',dtype='<f4').reshape(-1,256)
                emitted=[r for r in rows if r[0]==tag];assert len(raw)==len(emitted)
                centers=np.array([int(r[1]) for r in emitted]);arrivals=np.array([int(r[2]) for r in emitted]);assert np.all(np.diff(centers)>0)
                preflight_abstained=sum(r[0]=='safe_abstain' for r in rows) if mode=='safe_mirror' else 0
                info.append(dict(record=rid,mode=mode,offset=offset,n=len(raw),preflight_abstained=preflight_abstained,reference=z['reference'],symbols=z['symbols'],centers=centers,arrivals=arrivals));all_raw.append(raw);offset+=len(raw)
        raw=np.concatenate(all_raw);raw_path=OUT/f'{stage}_all_raw.bin';raw.tofile(raw_path)
        q=OUT/f'{stage}_all_q.bin';run([BASE/'preprocess_host.exe',raw_path,q],OUT/f'{stage}_preprocessing.log')
        double=raw.astype(np.float64);std=double.std(axis=1,keepdims=True);assert np.all(std>=1e-8)
        norm=((double-double.mean(axis=1,keepdims=True))/std).astype(np.float32)
        unclipped=np.rint(norm.astype(float)/np.float32(.053921569138765335))-27;clipped=np.any((unclipped<-128)|(unclipped>127),axis=1)
        expected=np.clip(unclipped,-128,127).astype(np.int8)
        np.testing.assert_array_equal(np.fromfile(q,dtype=np.int8).reshape(-1,256),expected)
        codes_path=OUT/f'{stage}_all_codes.bin'
        _,cnn_wall=run([BASE/'int8_fixed_host/full_chain.exe',FW/'main/model/ecg_cnn_int8.tflite',q,codes_path,'--batch'],OUT/f'{stage}_native_cnn.log')
        codes=np.fromfile(codes_path,dtype=np.int8);assert len(codes)==len(raw)
        modes={}
        for mode in ('candidate','safe_mirror'):
            cm=np.zeros((2,2),dtype=np.int64);refs=Counter();miss=Counter();other=Counter();other_predictions=Counter();unmatched_pred=Counter();classified=0;windows=0;blocked=0;delay=[];false_rows=[];per=[]
            for row in (i for i in info if i['mode']==mode):
                start=row['offset'];end=start+row['n'];pred=((codes[start:end].astype(float)+128)/256>=.52).astype(int);valid=~clipped[start:end]
                centers=row['centers'];matches,fp=assignment(row['reference'],centers);local_cm=np.zeros((2,2),dtype=int)
                for j,(center,sym) in enumerate(zip(row['reference'],row['symbols'])):
                    index=int(matches[j])
                    if sym in ('N','V'):
                        refs[str(sym)]+=1
                        if index<0 or not valid[index]:miss[str(sym)]+=1;continue
                        label=int(sym=='V');local_cm[label,pred[index]]+=1
                        if pred[index]!=label:false_rows.append(dict(record=row['record'],annotation_sample=int(center),detected_sample=int(centers[index]),true=str(sym),predicted='V' if pred[index] else 'N',code=int(codes[start+index])))
                    elif index>=0 and valid[index]:
                        other[str(sym)]+=1;other_predictions[str(sym)+'->'+('V' if pred[index] else 'N')]+=1
                for k in fp:
                    if valid[k]:unmatched_pred['V' if pred[k] else 'N']+=1
                cm+=local_cm;windows+=row['n']+row['preflight_abstained'];classified+=int(np.sum(valid));blocked+=int(np.sum(~valid))+row['preflight_abstained']
                delay.extend(((row['arrivals']-centers)*4).tolist())
                per.append(dict(record=row['record'],detector=score(row['reference'],centers,row['symbols']),windows=row['n'],classified=int(np.sum(valid)),conditional_confusion=local_cm.tolist()))
            conditional=class_metrics(cm);strict={}
            for label,name in enumerate(('N','V')):
                tp=int(cm[label,label]);fp=int(cm[:,label].sum()-tp)+unmatched_pred[name];fn=int(cm[label,:].sum()-tp)+miss[name]
                strict[name]=dict(precision=tp/(tp+fp) if tp+fp else None,recall=tp/refs[name],f1=2*tp/(2*tp+fp+fn),tp=tp,fp=fp,fn=fn)
            modes[mode]=dict(reference_all=sum(r['tp']+r['fn'] for r in per_record),reference_NV=dict(refs),windows=windows,classified=classified,
                quantization_abstained=blocked,missed_before_CNN_NV=dict(miss),conditional_confusion_rows_N_V=cm.tolist(),conditional_metrics=conditional,
                false_classification_NV=int(cm[0,1]+cm[1,0]),conditional_accuracy=float(np.trace(cm)/cm.sum()),
                end_to_end_metrics_with_misses_and_unmatched=strict,unmatched_predictions=dict(unmatched_pred),matched_other_annotation=dict(other),matched_other_predictions=dict(other_predictions),
                localization_to_window_ready_ms=dict(minimum=min(delay),median=float(np.median(delay)),p95=float(np.percentile(delay,95)),maximum=max(delay)),
                per_record=per,false_classifications=false_rows,
                metric_scope='Conditional confusion only matched N/V eligible windows; strict recall includes all reference N/V misses; strict precision additionally penalizes unmatched detections; other beat types are excluded and enumerated, never relabeled N')
        report[stage]=dict(detector=summary_metrics(per_record),per_record=per_record,end_to_end=modes,
            host_native_batch_wall_seconds=cnn_wall,host_native_batch_windows=len(raw),host_batch_ms_per_window_including_process_io=cnn_wall*1000/len(raw))
        print(stage,report[stage]['detector'],flush=True)
    criteria=previous['criteria'];cur=report['2b'];cur['record_pass']={r['record']:r['sensitivity']>=.99 and r['ppv']>=.99 and r['timing_p95_abs_ms']<=40 for r in cur['per_record']}
    controls={}
    for name in ('no_peaks','pure50Hz'):
        path=FW/f'debug/r_peak_audit/{name}.bin';text,_=run([BASE/'replay.exe',path,OUT/f'{name}_windows.bin',OUT/f'{name}_safe.bin'],OUT/f'{name}_events.csv');rows=rows_from(text)
        controls[name]=dict(candidate_peaks=sum(r[0]=='peak' for r in rows),safe_windows=sum(r[0]=='safe_peak' for r in rows),issues=dict(Counter(r[2] for r in rows if r[0]=='issue')))
    report.update(criteria=criteria,records=records,controls=controls,detector_pass=all(cur['record_pass'].values()) and all(c['candidate_peaks']==0 for c in controls.values()),
        ai_live_unlocked=False,com_opened=False,flashed=False,limitations=['Validation reused and inspected in prior rounds; exploratory, not independent final evaluation',
            'Safe host mirror rejects quality blocks, resets on detector issue and quantization abstention; not full worker/generation/FSM/RTOS simulation',
            'Actual raw C++ emitted windows, C++ preprocessing and native INT8 kernels; other annotation types and unmatched windows explicitly counted',
            'Host batch wall time is not board inference latency; no board scheduler, CPU or simulator validation'])
    (OUT/'evaluation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(pass_detector=report['detector_pass'],records=cur['record_pass'],controls=controls,
        safe_confusion=cur['end_to_end']['safe_mirror']['conditional_confusion_rows_N_V'],strict=cur['end_to_end']['safe_mirror']['end_to_end_metrics_with_misses_and_unmatched']),indent=2))
if __name__=='__main__':main()
