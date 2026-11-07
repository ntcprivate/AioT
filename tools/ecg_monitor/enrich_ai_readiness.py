"""Additional focused evidence; reuses cached windows, no Test evaluation or tuning."""
from pathlib import Path
from collections import Counter
import csv,json,subprocess,hashlib
import numpy as np,wfdb
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/final_ai_readiness';FIXED=FW/'debug/r_peak_phase2b/fixed_validation'
def main():
    d=json.loads((OUT/'evidence.json').read_text());rows=list(csv.DictReader((OUT/'matched_cases.csv').open(encoding='utf-8')))
    all_raw=[]
    for rid in d['split']['validation']['records']:
        events=[r.split(',') for r in (FIXED/f'2b_{rid}_events.csv').read_text().splitlines()];centers=[int(r[1]) for r in events if r[0]=='safe_peak']
        index={c:i for i,c in enumerate(centers)};raw=np.fromfile(FIXED/f'2b_{rid}_safe_windows.bin',dtype='<f4').reshape(-1,256)
        for r in rows:
            if r['record']==rid:all_raw.append(raw[index[int(r['detected_sample'])]])
    raw=np.stack(all_raw).astype(float);assert len(raw)==len(rows)
    z=((raw-raw.mean(axis=1,keepdims=True))/raw.std(axis=1,keepdims=True)).astype('<f4');z.tofile(OUT/'matched_normalized_float32.bin')
    run=subprocess.run([str(ROOT/'tools/ecg_monitor/.venv_reference/Scripts/python.exe'),str(ROOT/'tools/ecg_monitor/readiness_float32_probe.py')],capture_output=True,check=True)
    (OUT/'keras_probe.log').write_bytes(run.stdout+run.stderr)
    scores=np.fromfile(OUT/'matched_keras_scores.bin',dtype='<f4');assert len(scores)==len(rows)
    float_comparison={}
    for label in ('N','V'):
        indices=[i for i,r in enumerate(rows) if r['label']==label];wrong=[i for i in indices if rows[i]['predicted']!=label]
        iswrong=lambda i:('V' if scores[i]>=.52 else 'N')!=label
        float_comparison[label]=dict(int8_errors=len(wrong),float32_errors=sum(iswrong(i) for i in indices),both_wrong=sum(iswrong(i) for i in wrong),
            int8_only_errors=sum(not iswrong(i) for i in wrong),float32_only_errors=sum(iswrong(i) for i in indices if i not in set(wrong)))
    d['same_window_float32_comparison']=float_comparison
    d['confidence_bins']={}
    for label in ('N','V'):
        wrong=[float(r['p_pvc']) for r in rows if r['label']==label and r['predicted']!=label]
        bins=Counter('p<0.1' if p<.1 else '0.1<=p<0.4' if p<.4 else '0.4<=p<0.52' if p<.52 else '0.52<=p<0.6' if p<.6 else '0.6<=p<0.9' if p<.9 else 'p>=0.9' for p in wrong)
        d['confidence_bins'][label]=dict(bins)
    # Annotation-only Train context audit, not additional training or model selection.
    context={label:Counter() for label in ('N','V')}
    for rid in d['split']['train']['records']:
        base=ROOT/'mit-bih-arrhythmia-database-1.0.0'/rid;head=wfdb.rdheader(str(base));ann=wfdb.rdann(str(base),'atr')
        centers=(ann.sample*25+18)//36;symbols=np.asarray(ann.symbol);v=centers[symbols=='V'];length=(head.sig_len*25+35)//36
        for c,label in zip(centers,symbols):
            if label not in ('N','V') or c<128 or c+128>length:continue
            count=int(np.searchsorted(v,c+128)-np.searchsorted(v,c-128))-int(label=='V')
            context[str(label)]['reference']+=1;context[str(label)]['neighbor_pvc']+=count>0
    d['train_annotation_context']={label:dict(v) for label,v in context.items()}
    assert context['N']['reference']==d['split']['train']['N'] and context['V']['reference']==d['split']['train']['V']
    N=[r for r in rows if r['label']=='N'];near=[r for r in N if int(r['neighbor_pvc'])>0];far=[r for r in N if int(r['neighbor_pvc'])==0]
    d['normal_neighbor_association']=dict(with_neighbor_V=dict(n=len(near),wrong=sum(r['predicted']=='V' for r in near)),without_neighbor_V=dict(n=len(far),wrong=sum(r['predicted']=='V' for r in far)))
    original=json.loads((FW/'debug/r_peak_phase2b_results.json').read_text(encoding='utf-8'));d['other_label_predictions']=original['2b']['end_to_end']['safe_mirror']['matched_other_predictions']
    d['other_label_pvc_predictions']=sum(n for key,n in d['other_label_predictions'].items() if key.endswith('->V'))
    metrics=json.loads((ROOT/'results/cnn_metrics.json').read_text());d['training_audit']=dict(parameters=metrics['parameters'],has_global_average_pooling=any(l['class_name']=='GlobalAveragePooling1D' for l in metrics['model_config']['layers']),
        class_weights=metrics['class_weights_train_only'],best_epoch=metrics['best_epoch'],split_seed=metrics['split_seed'],split_search=metrics['split_search'],
        previous_test_exposed=True,source_predict_test_line=220,test_evaluation_artifact_present=bool(metrics.get('evaluation')),executed_training_source_sha_recorded=False)
    conversion=json.loads((ROOT/'results/tinyml_conversion_report.json').read_text());d['calibration_train_only']=dict(source=conversion['representative_dataset']['source'],size=conversion['representative_dataset']['size'])
    d['protected_checks']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in json.loads((OUT/'before_sha256.json').read_text()).items()};assert all(d['protected_checks'].values())
    (OUT/'evidence.json').write_text(json.dumps(d,indent=2));print(json.dumps({k:d[k] for k in ('same_window_float32_comparison','normal_neighbor_association','train_annotation_context','confidence_bins','other_label_pvc_predictions')},indent=2))
if __name__=='__main__':main()
