"""Create a Python TFLite operator reference, or compare a real serial trace.

Create (project .venv with TensorFlow):
  python tests/compare_operator_trace.py --generate --sample 5
Compare (stdlib only):
  python tests/compare_operator_trace.py --log debug/serial_trace.log
Uses embedded golden Validation bytes only, never ADC/dataset/Test inference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PROJECT=Path(__file__).resolve().parent.parent


def fnv(data):
    value=2166136261
    for byte in data:
        value=((value^byte)*16777619)&0xffffffff
    return f'{value:08x}'


def generate(sample,destination):
    import numpy as np
    import tensorflow as tf
    from tensorflow.lite.python import schema_py_generated as schema
    model=PROJECT/'main/model/ecg_cnn_int8.tflite'
    data=(PROJECT/'main/test_data/ecg_test_samples_int8.bin').read_bytes()
    metadata=(PROJECT/'main/test_data/ecg_test_metadata.h').read_text()
    expected_model=re.search(r'kModelSha\[\].*?"([0-9a-f]+)"',metadata).group(1)
    expected_samples=re.search(r'kSamplesSha\[\].*?"([0-9a-f]+)"',metadata).group(1)
    if hashlib.sha256(model.read_bytes()).hexdigest()!=expected_model or hashlib.sha256(data).hexdigest()!=expected_samples:
        raise ValueError('Embedded assets differ from original golden metadata')
    source=data[sample*256:(sample+1)*256]
    if len(source)!=256: raise ValueError('Invalid golden sample index')
    interpreter=tf.lite.Interpreter(model_path=str(model),experimental_preserve_all_tensors=True,
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES,num_threads=1)
    interpreter.allocate_tensors()
    inp=interpreter.get_input_details()[0];out=interpreter.get_output_details()[0]
    if inp['dtype']!=np.int8 or tuple(inp['shape'])!=(1,256,1): raise ValueError('Unexpected input')
    interpreter.set_tensor(inp['index'],np.frombuffer(source,dtype=np.int8).reshape(1,256,1))
    interpreter.invoke()
    code=int(interpreter.get_tensor(out['index'])[0,0])
    # Read original refs, do not regenerate or loosen them.
    golden_rows=re.findall(r'\{\s*\d+,\s*"\d+",\s*\d+,\s*(-?\d+),\s*[0-9.]+f,\s*\d+\s*\}',metadata)
    if code!=int(golden_rows[sample]): raise ValueError(f'Python backend code={code} differs from unchanged golden={golden_rows[sample]}; stop and review versions')
    flat=schema.Model.GetRootAsModel(model.read_bytes(),0);graph=flat.Subgraphs(0)
    names={v:k for k,v in vars(schema.BuiltinOperator).items() if isinstance(v,int)}
    tensors={t['index']:t for t in interpreter.get_tensor_details()}
    rows=[]
    for index in range(graph.OperatorsLength()):
        op=graph.Operators(index);opcode=flat.OperatorCodes(op.OpcodeIndex())
        if op.OutputsLength()!=1: raise ValueError('Expected single-output operator')
        tensor_index=op.Outputs(0);t=tensors[tensor_index]
        value=interpreter.get_tensor(tensor_index)
        # Output tensors of this model are all signed INT8; no endian ambiguity.
        if value.dtype!=np.int8: raise ValueError('Trace comparison currently expects INT8 node outputs')
        raw=value.tobytes(order='C')
        rows.append({'op':index,'tag':names[max(opcode.BuiltinCode(),opcode.DeprecatedBuiltinCode())],
            'version':opcode.Version(),'tensor':tensor_index,'shape':value.shape,'bytes':len(raw),
            'fnv':fnv(raw),'hex':raw.hex(),'scale':float(t['quantization'][0]),'zero':int(t['quantization'][1])})
    report={'model_sha256':expected_model,'samples_sha256':expected_samples,'sample':sample,
        'input_fnv':fnv(source),'final_code':code,'tensorflow_version':tf.__version__,
        'backend':'TFLite CPU builtin, no delegates, preserve tensors',
        'operators':rows,'scope':'Real golden Validation fixture only; not clinical evaluation'}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2))
    print(f'Saved Python reference: {destination}; sample={sample} code={code}')


def fields(line):
    return dict(re.findall(r'([a-zA-Z0-9_]+)=([^\s]+)',line))


def compare(reference,log,destination):
    expected=json.loads(reference.read_text());sample=expected['sample']
    text=log.read_text(encoding='utf-8-sig',errors='strict')
    starts=[];ends=[];results=[];headers={};chunks={};assets=[];order=[]
    for line_number,line in enumerate(text.splitlines(),1):
        f=fields(line)
        if 'ECG_ASSETS ' in line: assets.append(f)
        if 'ECG_TRACE_' not in line: continue
        if f.get('sample')!=str(sample):
            raise ValueError(f'Line {line_number}: unexpected/missing trace sample ID')
        # Protocol2 checks the entire line BEFORE trusting op/offset/length fields.
        match=re.search(r'(ECG_TRACE_[A-Z]+ .*?) line_fnv=([0-9a-f]{8})$',line)
        if not match:
            raise ValueError(f'Line {line_number}: missing protocol2 line checksum; legacy/damaged trace cannot be compared')
        body,wire_hash=match.groups()
        if fnv(body.encode('ascii'))!=wire_hash:
            raise ValueError(f'Line {line_number}: line checksum mismatch (lost/changed character); no data repair')
        pairs=re.findall(r'([a-zA-Z0-9_]+)=([^\s]+)',body)
        if len(dict(pairs))!=len(pairs): raise ValueError(f'Line {line_number}: duplicate field')
        f=dict(pairs);kind=body.split(' ',1)[0];order.append(kind)
        if kind=='ECG_TRACE_BEGIN':
            starts.append(f)
            if len(starts)!=1 or len(order)!=1: raise ValueError('Duplicate/out-of-order BEGIN')
            if f.get('protocol')!='2' or f.get('chunk_bytes')!='16' or f.get('status')!='CAPTURED':
                raise ValueError('Unsupported/failed trace BEGIN')
        elif kind=='ECG_TRACE_END':
            if not starts or ends or results: raise ValueError('Missing/duplicate/out-of-order END')
            ends.append(f)
        elif kind=='ECG_TRACE_RESULT':
            if not ends or results: raise ValueError('Missing/duplicate/out-of-order RESULT')
            results.append(f)
        elif kind in ('ECG_TRACE_TENSOR','ECG_TRACE_DATA'):
            if not starts or ends: raise ValueError('Tensor/chunk outside BEGIN/END')
            key=int(f['op'])
            if kind=='ECG_TRACE_TENSOR':
                if key in headers or key!=len(headers): raise ValueError('Duplicate/out-of-order operator header')
                headers[key]=f
            else:
                if key not in headers or key!=len(headers)-1: raise ValueError('Chunk belongs to wrong operator')
                offset=int(f['offset']);n=int(f['nbytes']);h=f['hex']
                if not 1<=n<=16 or int(f['hex_chars'])!=2*n or len(h)!=2*n or not re.fullmatch('[0-9a-f]+',h):
                    raise ValueError(f'Line {line_number}: HEX length/alphabet invalid for {n} bytes')
                raw=bytes.fromhex(h)
                if fnv(raw)!=f['chunk_fnv']: raise ValueError(f'Line {line_number}: chunk checksum mismatch')
                chunk_key=(key,offset)
                if chunk_key in chunks: raise ValueError('Duplicate chunk offset')
                previous_bytes=sum(len(v) for (op,_),v in chunks.items() if op==key)
                if offset!=previous_bytes: raise ValueError('Missing/out-of-order chunk')
                if int(f['tensor'])!=int(headers[key]['tensor']): raise ValueError('Wrong chunk tensor ID')
                chunks[chunk_key]=raw
        else:
            raise ValueError(f'Line {line_number}: unknown trace record {kind}')
    if len(starts)!=1 or len(ends)!=1 or len(results)!=1:
        raise ValueError('Require exactly one valid BEGIN, END and RESULT; no divergence conclusion possible')
    begin,end,result=starts[0],ends[0],results[0]
    if end.get('status')!='COMPLETE' or end.get('generation_errors')!='0' or end.get('write_errors')!='0':
        raise ValueError('Firmware reported generation/transport failure')
    if result.get('invoke_ok')!='1' or result.get('trace_ok')!='1' or result.get('write_errors')!='0':
        raise ValueError('Unsuccessful trace/inference RESULT')
    if begin['input_fnv']!=expected['input_fnv']: raise ValueError('Different golden input bytes')
    if not any(a.get('model_sha256')==expected['model_sha256'] and a.get('samples_sha256')==expected['samples_sha256'] and a.get('verified')=='1' for a in assets):
        raise ValueError('Missing matching verified asset hashes')
    if len(headers)!=len(expected['operators']) or int(begin['nodes'])!=len(headers) or int(end['nodes'])!=len(headers):
        raise ValueError('Operator count mismatch')
    actual={};stream=bytearray()
    for e in expected['operators']:
        h=headers[e['op']]
        if h['tag']!=e['tag'] or int(h['tensor'])!=e['tensor'] or int(h['version'])!=e['version']:
            raise ValueError('Operator order/version/tensor mapping differs')
        if int(h['bytes'])!=e['bytes']: raise ValueError('Tensor byte count differs')
        raw=b''.join(v for (op,_),v in chunks.items() if op==e['op'])
        if len(raw)!=e['bytes'] or fnv(raw)!=h['fnv']: raise ValueError('Incomplete/corrupt tensor')
        actual[e['op']]=raw;stream.extend(raw)
    if int(begin['bytes_total'])!=len(stream) or int(end['bytes_total'])!=len(stream) or int(end['chunks_total'])!=len(chunks) or fnv(stream)!=end['stream_fnv']:
        raise ValueError('Whole trace byte/chunk count or stream checksum mismatch')
    final_raw=actual[expected['operators'][-1]['op']]
    if len(final_raw)!=1: raise ValueError('Expected one INT8 final output')
    final_code=final_raw[0] if final_raw[0]<128 else final_raw[0]-256
    if int(result['code'])!=final_code: raise ValueError('RESULT code differs from captured final tensor')
    # Only compare numerical tensors AFTER the complete transport is verified.
    rows=[]
    for e in expected['operators']:
        h=headers[e['op']];raw=actual[e['op']]
        source=bytes.fromhex(e['hex']);differences=[]
        if len(source)!=e['bytes']: raise ValueError('Invalid Python reference byte count')
        for index,(a,b) in enumerate(zip(source,raw)):
            if a!=b:
                python=a if a<128 else a-256;esp=b if b<128 else b-256
                differences.append({'index':index,'python':python,'esp32':esp,'delta':esp-python})
        q_match=abs(float(h['scale'])-e['scale'])<max(1e-10,abs(e['scale'])*1e-9) and int(h['zero'])==e['zero']
        rows.append({'op':e['op'],'tag':e['tag'],'version':e['version'],'tensor':e['tensor'],
            'quantization_match':q_match,'exact_bytes':not differences,'mismatch_count':len(differences),
            'max_abs_lsb':max((abs(d['delta']) for d in differences),default=0),'first_differences':differences[:16]})
    first=next((r for r in rows if not r['exact_bytes'] or not r['quantization_match']),None)
    report={'status':'FIRST_DIVERGENCE_LOCATED' if first else 'ALL_TRACED_TENSORS_EXACT',
        'protocol':2,'transport_verified':True,'sample':sample,'first_divergence':first,'operators':rows,
        'reference':str(reference),'hardware_log':str(log),'hardware_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),
        'note':'Verified transport only. First differing node is a boundary, not automatic proof of a kernel bug. No golden criteria changed.'}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate',action='store_true');parser.add_argument('--sample',type=int,choices=range(12),default=5)
    parser.add_argument('--reference',type=Path,default=PROJECT/'debug/python_operator_reference.json')
    parser.add_argument('--log',type=Path);parser.add_argument('--output',type=Path,default=PROJECT/'debug/operator_comparison.json')
    args=parser.parse_args()
    try:
        if args.generate: generate(args.sample,args.reference)
        if args.log: compare(args.reference,args.log,args.output)
        if not args.generate and not args.log: parser.error('Use --generate and/or --log')
    except (OSError,ValueError,KeyError,ImportError) as error:
        if args.log:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps({'status':'TRACE_REJECTED','transport_verified':False,
                'hardware_log':str(args.log),'error':str(error),'first_divergence':None,
                'note':'No repair or numerical conclusion. Old PASS results must not be reused for this capture.'},indent=2))
        raise SystemExit(f'ERROR: {error}; no PASS inferred')
