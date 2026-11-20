"""Development engineering check only: native detector/windows and TFLM host.
No RTOS, analog lead-off, generation timing or real ADC quality is simulated.
"""
import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import csv,hashlib,importlib.util,json,subprocess,time
from pathlib import Path
import numpy as np
import tensorflow as tf
from evaluate_v4_board_replay import match
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/cnn_v4/esp32_end_to_end'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    run=OUT/'host_replay_20261119';run.mkdir(exist_ok=False)
    protocol=json.loads((OUT/'replay_protocol.json').read_text());model=ROOT/'models/v4/ecg_cnn_v4_int8.tflite'
    assert sha(model)=='a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e'
    fp=ROOT/'firmware/esp32_ecg_v4_experiment/main/model/ecg_cnn_v4_fp32.tflite'
    interpreter=tf.lite.Interpreter(model_path=str(fp),experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    interpreter.allocate_tensors();ii=interpreter.get_input_details()[0]['index'];oi=interpreter.get_output_details()[0]['index']
    keras=tf.keras.models.load_model(ROOT/'models/v4/ecg_cnn_v4_best.keras',compile=False)
    golden=np.load(ROOT/'results/cnn_v4/esp32_golden_test/golden_fixtures.npz');x=golden['normalized_ecg'].reshape(-1,256,1)
    a=keras(x,training=False).numpy().ravel();b=[]
    for window in x:interpreter.set_tensor(ii,window[None].astype(np.float32));interpreter.invoke();b.append(float(interpreter.get_tensor(oi).ravel()[0]))
    comparison={'golden_count':len(a),'max_abs_keras_tflite_fp32':float(np.max(np.abs(a-b))),
      'prediction_disagreements':int(np.count_nonzero((a>=.88)!=(np.array(b)>=.88))),
      'checkpoint_sha256':sha(ROOT/'models/v4/ecg_cnn_v4_best.keras'),'fp32_sha256':sha(fp)}
    assert comparison['max_abs_keras_tflite_fp32']<1e-5 and comparison['prediction_disagreements']==0
    results=[]
    for record in protocol['records']:
        key=record['dataset']+'_'+record['record'];base=run/key;asset=ROOT/record['asset'];assert sha(asset)==record['sha256']
        subprocess.run([str(OUT/'replay_host.exe'),str(asset),str(base)+'.events.csv',str(base)+'.inputs.bin',str(base)+'.raw.bin'],check=True)
        subprocess.run([str(OUT/'tflm_replay_host.exe'),str(model),str(base)+'.inputs.bin',str(base)+'.codes.bin',str(base)+'.timings.csv'],check=True)
        lines=list(csv.reader(Path(str(base)+'.events.csv').read_text().splitlines()))
        peaks=[int(l[1]) for l in lines if l[0]=='peak'];windows=[l for l in lines if l[0]=='window'];ok=[l for l in windows if l[2]=='1' and l[3]=='0']
        codes=np.fromfile(str(base)+'.codes.bin',dtype=np.int8);assert len(codes)==len(ok)
        timing=list(csv.DictReader(Path(str(base)+'.timings.csv').open()));assert len(timing)==len(ok)
        raw=np.fromfile(str(base)+'.raw.bin',dtype=np.float32).reshape(-1,256);scores32=[]
        preds={int(l[1]):int(c>=98) for l,c in zip(ok,codes)};details=[]
        for l,c,t,w in zip(ok,codes,timing,raw):
            start=time.perf_counter_ns();z=((w.astype(np.float64)-w.astype(np.float64).mean())/w.astype(np.float64).std()).astype(np.float32)
            prep=(time.perf_counter_ns()-start)/1000;interpreter.set_tensor(ii,z.reshape(1,256,1));interpreter.invoke();s=float(interpreter.get_tensor(oi).ravel()[0]);scores32.append(s)
            details.append({'peak_index':int(l[1]),'code':int(c),'p_pvc':(int(c)+128)/256,'prediction':int(c>=98),'invoke_host_us':int(t['invoke_host_us']),'prep_python_host_us':prep,'fp32_score':s})
        refs=json.loads((ROOT/record['reference_path']).read_text());refs=[r for r in refs if r['symbol'] in protocol['matching']['beat_symbols']]
        pairs,used=match(refs,peaks);tp=fpn=fn=tn=missing_v=missing_n=window_v=cnn_v=0
        for ri,r in enumerate(refs):
            c=r['symbol']
            if c not in {'N','V'}:continue
            if ri not in pairs:missing_v+=c=='V';missing_n+=c=='N';fn+=c=='V';continue
            p=peaks[pairs[ri]]
            if p not in preds:window_v+=c=='V';missing_n+=c=='N';fn+=c=='V';continue
            v=preds[p];tp+=c=='V' and v;fpn+=c=='N' and v;fn+=c=='V' and not v;cnn_v+=c=='V' and not v;tn+=c=='N' and not v
        unmatched=sum(preds.get(p,0) for j,p in enumerate(peaks) if j not in used);fpn+=unmatched
        precision=tp/(tp+fpn) if tp+fpn else 0;recall=tp/(tp+fn) if tp+fn else 0
        reverse={peaks[j]:refs[i] for i,j in pairs.items()}
        with Path(str(base)+'.beats.csv').open('w',newline='') as f:
            names=['peak_index','reference_symbol','offset_samples','code','p_pvc','prediction','invoke_host_us','prep_python_host_us','fp32_score'];writer=csv.DictWriter(f,fieldnames=names);writer.writeheader()
            for d in details:
                ref=reverse.get(d['peak_index']);writer.writerow(dict(d,reference_symbol=ref['symbol'] if ref else 'UNMATCHED',offset_samples=d['peak_index']-ref['sample'] if ref else ''))
        result={'record':key,'samples':15360,'reference_N':sum(r['symbol']=='N' for r in refs),'reference_V':sum(r['symbol']=='V' for r in refs),'peaks':len(peaks),'windows':len(windows),'classified':len(codes),
          'rejected_windows':len(windows)-len(ok),'detector_issues':[l for l in lines if l[0]=='issue'],'peakTP':len(pairs),'peakFP':len(peaks)-len(used),'peakFN':len(refs)-len(pairs),
          'TP':tp,'FP':fpn,'FN':fn,'TN':tn,'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,
          'PVC_detector_missed':missing_v,'PVC_window_missing':window_v,'PVC_classifier_FN':cnn_v,'missing_N':missing_n,'unmatched_PVC_alarms':unmatched,
          'max_abs_FP32_INT8':float(np.max(abs(np.array(scores32)-(codes.astype(float)+128)/256))) if len(codes) else None,
          'FP32_INT8_prediction_disagreements':int(np.count_nonzero((np.array(scores32)>=.88)!=(codes>=98))),
          'dropped_samples':0,'drop_claim':'deterministic host file scan only, not device measurement'}
        results.append(result)
    report={'status':'HOST_COMPONENT_CHAIN_COMPLETE','scope':'ungated deterministic file replay; firmware RTOS/generation/recovery/lead-off gates not emulated; no board/analog accuracy claim',
      'golden_fp32_check':comparison,'records':results,'operators_fp32_no_delegates':[o['op_name'] for o in interpreter._get_ops_details()]}
    (run/'evaluation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
