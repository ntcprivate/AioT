"""Frozen Development-only continuous replay + unquantized V4 export; no fitting."""
import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0'
os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import hashlib,json,math,sys
from pathlib import Path
import numpy as np
import wfdb
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parents[1]
FW=ROOT/'firmware/esp32_ecg_v4_experiment'
OUT=ROOT/'results/cnn_v4/esp32_end_to_end'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if "--export-only" not in sys.argv:
        lock=OUT/'replay_protocol.json'
        if lock.exists():raise RuntimeError('Protocol/assets already frozen; refuse overwrite')
        protocol={'version':1,'purpose':'Development engineering replay, not independent accuracy evaluation',
          'fs':250,'samples_per_record':15360,'range':'[0,15360), no padding or looping',
          'mapping':'clip(rint(2048+200*physical_mV),0,4095), ties-to-even; full resample before crop',
          'detector':{'source':'copied signal.cpp','confirmation_samples':50,'refractory_samples':75,'status':'NOT_READY_FOR_ACCURACY_CLAIMS'},
          'matching':{'tolerance_samples':38,'algorithm':'chronological reference, nearest unused detection, ties lower detection index',
              'beat_symbols':'NLRBAaJSVrFejnE/fQ?','OTHER':'beat TP for detector; excluded N/V classifier, never Normal',
              'missed_V':'FN','missed_N':'abstention, not TN','unmatched_PVC':'FP alarm; not automatically noise',
              'scope':'all beat annotations within supplied stream; boundaries/warmup/rejections reported, not silently removed'},
          'threshold':0.88,'threshold_code':98,'records':[]}
        for dataset,record,folder,lead,split in [('MITBIH','100','mit-bih-arrhythmia-database-1.0.0','MLII','Train'),('INCART','I08','files','II','Validation')]:
            base=ROOT/folder/record;h=wfdb.rdheader(str(base));index=[s.strip().upper() for s in h.sig_name].index(lead)
            raw=wfdb.rdrecord(str(base),channels=[index],physical=True).p_signal[:,0]
            div=math.gcd(int(h.fs),250);signal=resample_poly(raw,250//div,int(h.fs)//div)[:15360]
            assert len(signal)==15360 and np.isfinite(signal).all()
            counts=np.clip(np.rint(2048+200*signal),0,4095).astype('<u2')
            key=dataset+'_'+record;asset=FW/'main/assets'/f'{key}.bin';asset.write_bytes(counts.tobytes())
            ann=wfdb.rdann(str(base),'atr');refs=[{'sample':int(np.floor(int(s)*250/h.fs+.5)),'symbol':c} for s,c in zip(ann.sample,ann.symbol) if 0<=int(np.floor(int(s)*250/h.fs+.5))<15360]
            refpath=OUT/f'{key}_annotations.json';refpath.write_text(json.dumps(refs,indent=2))
            protocol['records'].append({'dataset':dataset,'record':record,'split':split,'lead':lead,'source_hz':h.fs,
              'asset':str(asset.relative_to(ROOT)),'sha256':sha(asset),'reference_path':str(refpath.relative_to(ROOT)),
              'reference_sha256':sha(refpath),'source_hashes':{ext:sha(base.with_suffix('.'+ext)) for ext in ['hea','dat','atr']},
              'rail_samples':int(((counts<=16)|(counts>=4079)).sum())})
        lock.write_text(json.dumps(protocol,indent=2))
        identity=['#pragma once','#if V4_REPLAY_INCART']
        for row in [protocol['records'][1],protocol['records'][0]]:
            identity += [f'constexpr char kReplayRecord[]="{row["dataset"]}_{row["record"]}";',
                         f'constexpr char kReplaySha[]="{row["sha256"]}";']
            identity.append('#else' if row==protocol['records'][1] else '#endif')
        (FW/'main/replay_identity.h').write_text('\n'.join(identity)+'\n')
        print('Frozen continuous replay assets, no annotation embedded',flush=True)
    import tensorflow as tf
    checkpoint=ROOT/'models/v4/ecg_cnn_v4_best.keras'
    assert sha(checkpoint)=='36caf719d11d0bb2d20d4de79fdfd0bed741b93bc48a7976df031b2a6ef8d4e1'
    out=FW/'main/model/ecg_cnn_v4_fp32.tflite'
    if out.exists():raise RuntimeError('Refuse FP32 overwrite')
    model=tf.keras.models.load_model(checkpoint,compile=False);assert model.count_params()==849
    converter=tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations=[]
    converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS]
    data=converter.convert();out=FW/'main/model/ecg_cnn_v4_fp32.tflite'
    if out.exists():raise RuntimeError('Refuse FP32 overwrite')
    out.write_bytes(data)
    (FW/'main/fp32_identity.h').write_text('#pragma once\nconstexpr char kFp32Sha[]="'+sha(out)+'";\n')
    interpreter=tf.lite.Interpreter(model_content=data);interpreter.allocate_tensors()
    assert all(t['dtype']==np.float32 for t in interpreter.get_input_details()+interpreter.get_output_details())
    # Existing golden normalized windows only, no Validation/Test rerun.
    f=np.load(ROOT/'results/cnn_v4/esp32_golden_test/golden_fixtures.npz');print('golden keys',f.files,flush=True)
    metadata={'source_checkpoint_sha256':sha(checkpoint),'sha256':sha(out),'bytes':len(data),'tensorflow':tf.__version__,
       'operators':[o['op_name'] for o in interpreter._get_ops_details()],
       'input_shape':interpreter.get_input_details()[0]['shape'].tolist(),
       'output_shape':interpreter.get_output_details()[0]['shape'].tolist(),
       'status':'EXPORT_ONLY; ESP32 float kernel allocation/inference PENDING; not retrained'}
    (OUT/'fp32_export.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata,indent=2))
if __name__=='__main__':main()
