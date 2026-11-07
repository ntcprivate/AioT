"""Run only with the isolated .venv_reference TensorFlow2.21 environment."""
import argparse
import numpy as np
import tensorflow as tf

p=argparse.ArgumentParser();p.add_argument('model');p.add_argument('input');p.add_argument('output');p.add_argument('--trace-output');a=p.parse_args()
instance=tf.lite.Interpreter(model_path=a.model,num_threads=1,experimental_preserve_all_tensors=True,
    experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
instance.allocate_tensors();inp=instance.get_input_details()[0];out=instance.get_output_details()[0]
data=np.fromfile(a.input,dtype=np.int8).reshape(-1,256,1);codes=[]
for beat in data:
    instance.set_tensor(inp['index'],beat[None]);instance.invoke();codes.append(instance.get_tensor(out['index']).reshape(-1)[0])
np.asarray(codes,dtype=np.int8).tofile(a.output)
if a.trace_output:
    import json
    from pathlib import Path
    folder=Path(a.trace_output);folder.mkdir(parents=True,exist_ok=True)
    reference=json.loads((Path(a.model).parents[2]/'debug/python_operator_reference.json').read_text())
    for entry in reference['operators']:(folder/f'op{entry["op"]}.bin').write_bytes(instance.get_tensor(entry['tensor']).tobytes())
print(f'TensorFlow{tf.__version__} CPU builtin reference: {len(codes)} original INT8 input beats; no delegate')
