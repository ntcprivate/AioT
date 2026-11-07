"""Resume2B: inspect existing mismatches, using identical INT8 input at both runtimes."""
import argparse, hashlib, json, subprocess, math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];FW=ROOT/'firmware/esp32_ecg_tinyml_integrated';OUT=FW/'debug/r_peak_phase2b/int8_diagnosis'
def main():
    p=argparse.ArgumentParser();p.add_argument('--tensorflow',action='store_true');args=p.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.tensorflow:
        import tensorflow as tf
        instance=tf.lite.Interpreter(model_path=str(FW/'main/model/ecg_cnn_int8.tflite'),num_threads=1,experimental_preserve_all_tensors=True,
            experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
        instance.allocate_tensors();inp=instance.get_input_details()[0]
        metadata={t['index']:t for t in instance.get_tensor_details()};ops=instance._get_ops_details()
        for case in json.loads((OUT/'cases.json').read_text()):
            folder=OUT/case['id'];q=np.fromfile(folder/'input.bin',dtype=np.int8).reshape(1,256,1)
            instance.set_tensor(inp['index'],q);instance.invoke()
            assert np.array_equal(instance.get_tensor(inp['index']),q)
            report=[]
            for i,op in enumerate(ops):
                tensor=int(op['outputs'][0]);value=instance.get_tensor(tensor);value.tofile(folder/f'tf_op{i}.bin')
                detail=metadata[tensor]
                report.append(dict(op=i,tag=op['op_name'],tensor=tensor,shape=value.shape,scale=detail['quantization'][0],zero=detail['quantization'][1]))
            (folder/'tf_ops.json').write_text(json.dumps(report,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else int(x)))
            fc=ops[14];ids=[int(x) for x in fc['inputs']];o=int(fc['outputs'][0])
            arithmetic=dict(input=instance.get_tensor(ids[0]).reshape(-1).tolist(),weights=instance.get_tensor(ids[1]).reshape(-1).tolist(),
                bias=int(instance.get_tensor(ids[2]).reshape(-1)[0]),input_scale=float(metadata[ids[0]]['quantization'][0]),input_zero=int(metadata[ids[0]]['quantization'][1]),
                weight_scale=float(metadata[ids[1]]['quantization'][0]),weight_zero=int(metadata[ids[1]]['quantization'][1]),output_scale=float(metadata[o]['quantization'][0]),output_zero=int(metadata[o]['quantization'][1]))
            (folder/'fc14_arithmetic.json').write_text(json.dumps(arithmetic,indent=2))
        return
    original=json.loads((FW/'debug/r_peak_phase2b/new_window_parity.json').read_text());q=np.fromfile(FW/'debug/r_peak_phase2b/2b_all_q.bin',dtype=np.int8).reshape(-1,256)
    unique={}
    for d in original['details']:unique.setdefault((d['record'],d['center']),d)
    cases=[]
    for (record,center),d in unique.items():
        case=dict(d,id=f'{record}_{center}');folder=OUT/case['id'];folder.mkdir(exist_ok=True);q[d['index']].tofile(folder/'input.bin');case['input_sha256']=hashlib.sha256((folder/'input.bin').read_bytes()).hexdigest()
        subprocess.run([str(FW/'debug/host_mode2/full_chain.exe'),str(FW/'main/model/ecg_cnn_int8.tflite'),str(folder/'input.bin'),str(folder),'--inspect'],check=True,capture_output=True)
        cases.append(case)
    (OUT/'cases.json').write_text(json.dumps(cases,indent=2))
    run=subprocess.run([str(ROOT/'tools/ecg_monitor/.venv_reference/Scripts/python.exe'),str(Path(__file__).resolve()),'--tensorflow'],capture_output=True,check=True)
    (OUT/'tensorflow.log').write_bytes(run.stdout+run.stderr)
    for case in cases:
        folder=OUT/case['id'];rows=[]
        for op in json.loads((folder/'tf_ops.json').read_text()):
            native=np.fromfile(folder/f'op{op["op"]}.bin',dtype=np.int8);tf=np.fromfile(folder/f'tf_op{op["op"]}.bin',dtype=np.int8)
            assert native.shape==tf.shape
            bad=np.flatnonzero(native!=tf)
            rows.append(dict(**op,mismatches=len(bad),maximum_lsb=int(np.max(abs(native.astype(int)-tf.astype(int)))) if len(native) else 0,
                first_bad_index=int(bad[0]) if len(bad) else None,native_first=int(native[bad[0]]) if len(bad) else None,tf_first=int(tf[bad[0]]) if len(bad) else None))
        case['operators']=rows;case['first_differing_operator']=next((r for r in rows if r['mismatches']),None)
        fc=json.loads((folder/'fc14_arithmetic.json').read_text())
        acc=fc['bias']+sum((x-fc['input_zero'])*(w-fc['weight_zero']) for x,w in zip(fc['input'],fc['weights']))
        fraction,shift=math.frexp(fc['input_scale']*fc['weight_scale']/fc['output_scale']);mult=int(math.floor(fraction*(1<<31)+.5))
        if mult==1<<31:mult//=2;shift+=1
        total=31-shift;single=(acc*mult+(1<<(total-1)))>>total
        left=max(shift,0);right=max(-shift,0);product=(acc*(1<<left))*mult;nudge=(1<<30) if product>=0 else 1-(1<<30)
        value=product+nudge;high=(abs(value)//(1<<31))*(1 if value>=0 else -1)
        mask=(1<<right)-1;remainder=high&mask;threshold=(mask>>1)+(1 if high<0 else 0)
        double=(high>>right)+(1 if remainder>threshold else 0)
        clamp=lambda x:max(-128,min(127,x+fc['output_zero']))
        case['requantization']=dict(accumulator=acc,multiplier=mult,shift=shift,output_zero=fc['output_zero'],single_code=clamp(single),double_code=clamp(double),
            accumulator_fits_int32=-(1<<31)<=acc<(1<<31),saturated=not(-128<clamp(single)<127 and -128<clamp(double)<127))
        assert case['first_differing_operator']['op']==14
        assert clamp(single)==rows[14]['tf_first'] and clamp(double)==rows[14]['native_first']
        print(case['id'],case['first_differing_operator'],flush=True)
    (OUT/'operator_comparison.json').write_text(json.dumps(cases,indent=2))
if __name__=='__main__':main()
