import os
os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
import json,hashlib
from pathlib import Path
import numpy as np
import tensorflow as tf
from tensorflow.lite.python import schema_py_generated as schema
root=Path(__file__).resolve().parents[1]/'results/cnn_v11/int8_conversion'
r=json.loads((root/'conversion.json').read_text());p=root/'ecg_cnn_v11_int8.tflite';assert hashlib.sha256(p.read_bytes()).hexdigest()==r['int8_sha256']
g=np.load(root/'golden_fixtures.npz');lite=tf.lite.Interpreter(model_path=str(p),num_threads=1,experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES);lite.allocate_tensors()
details=lite.get_input_details();e=next(t for t in details if tuple(t['shape'])==(1,256,1));rr=next(t for t in details if tuple(t['shape'])==(1,4));out=lite.get_output_details()[0]
for t,values,q in [(e,g['ecg'],g['ecg_int8']),(rr,g['rr_normalized'],g['rr_int8'])]:
 s,z=t['quantization'];np.testing.assert_array_equal(np.clip(np.rint(values.astype(np.float64)/s)+z,-128,127).astype(np.int8),q)
for j in range(len(g['output_int8'])):
 lite.set_tensor(e['index'],g['ecg_int8'][j:j+1]);lite.set_tensor(rr['index'],g['rr_int8'][j:j+1]);lite.invoke();assert int(lite.get_tensor(out['index']).ravel()[0])==int(g['output_int8'][j])
assert np.array_equal(g['prediction'],g['output_int8'].astype(int)>=77)
m=schema.Model.GetRootAsModel(p.read_bytes(),0);types={v:k for k,v in vars(schema.BuiltinOperator).items() if isinstance(v,int)};versions=[]
for j in range(m.OperatorCodesLength()):
 o=m.OperatorCodes(j);versions.append({'operator':types.get(o.BuiltinCode(),str(o.BuiltinCode())),'version':o.Version()})
result={'fixtures':len(g['output_int8']),'requantization_exact':True,'tflite_host_replay_exact':True,'threshold_decisions_exact':True,'TFLM_ESP32_exact_parity':'PENDING','operator_versions':versions}
(root/'golden_verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
