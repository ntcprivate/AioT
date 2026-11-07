"""Isolate real first CONV_2D with original FlatBuffer tensors; no TensorFlow needed.

Does not repair partial trace. Only individual checksum-verified chunks are used
as partial hardware evidence, never as a full-chain/golden PASS.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from flat_reader import Flat
from compare_operator_trace import fnv

PROJECT=Path(__file__).resolve().parent.parent


def trunc_div(a,b):
    return -(abs(a)//b) if a<0 else a//b


def double_round(x,m,shift):
    left=max(shift,0);right=max(-shift,0)
    value=x*(1<<left)
    product=value*m
    nudge=(1<<30) if product>=0 else 1-(1<<30)
    high=trunc_div(product+nudge,1<<31)
    mask=(1<<right)-1; remainder=high&mask
    threshold=(mask>>1)+(1 if high<0 else 0)
    return (high>>right)+(1 if remainder>threshold else 0),high


def single_round(x,m,shift):
    total=31-shift
    return (x*m+(1<<(total-1)))>>total


def multiplier(real):
    q,shift=math.frexp(real)
    m=math.floor(q*(1<<31)+0.5)
    if m==(1<<31):m//=2;shift+=1
    if shift < -31:return 0,0
    return m,shift


def load_model():
    path=PROJECT/'main/model/ecg_cnn_int8.tflite';data=path.read_bytes();f=Flat(data)
    root=f.read('<I',0);graph=f.vector(root,2,tables=True)[0]
    assert f.scalar(root,0)==3
    tables=f.vector(graph,0,tables=True);buffers=f.vector(root,4,tables=True)
    def tensor(index):
        t=tables[index];q=f.ref(t,4);buf=buffers[f.scalar(t,2)]
        raw=bytes(f.vector(buf,0,'<B'))
        return {'index':index,'shape':f.vector(t,0),'type':f.scalar(t,1,'<b'),
                'scales':f.vector(q,2,'<f'),'zeros':f.vector(q,3,'<q'),
                'axis':f.scalar(q,6,'<i'),'raw':raw}
    ops=f.vector(graph,3,tables=True);op=ops[1];inputs=f.vector(op,1);outputs=f.vector(op,2)
    opcode=f.vector(root,1,tables=True)[f.scalar(op,0)]
    assert max(f.scalar(opcode,0,'<b'),f.scalar(opcode,3,'<i'))==3 and f.scalar(opcode,2,'<i',1)==3
    options=f.ref(op,4)
    opts={'padding':f.scalar(options,0,'<b'),'stride_w':f.scalar(options,1,'<i'),
          'stride_h':f.scalar(options,2,'<i'),'activation':f.scalar(options,3,'<b'),
          'dilation_w':f.scalar(options,4,'<i',1),'dilation_h':f.scalar(options,5,'<i',1)}
    inp,weight,bias,out=map(tensor,[*inputs,outputs[0]])
    # Fixed architecture contract, checked from model rather than assumed.
    assert inp['shape']==[1,1,256,1] and weight['shape']==[8,1,5,1] and out['shape']==[1,1,252,8]
    assert opts=={'padding':1,'stride_w':1,'stride_h':1,'activation':1,'dilation_w':1,'dilation_h':1},opts
    assert weight['axis']==0 and len(weight['scales'])==8 and all(z==0 for z in weight['zeros'])
    assert bias['type']==2 and bias['shape']==[8]
    assert all(z==0 for z in bias['zeros'])
    assert all(math.isclose(bs,inp['scales'][0]*ws,rel_tol=1e-6) for bs,ws in zip(bias['scales'],weight['scales']))
    weights=list(struct.unpack('<40b',weight['raw']));biases=list(struct.unpack('<8i',bias['raw']))
    return path,inp,weight,bias,out,opts,weights,biases


def verified_trace_chunks(log):
    records={};rejected=[]
    for number,line in enumerate(log.read_text(encoding='utf-8-sig',errors='replace').splitlines(),1):
        if 'ECG_TRACE_DATA ' not in line:continue
        try:
            body,received=line[line.index('ECG_TRACE_DATA '):].rsplit(' line_fnv=',1)
            if fnv(body.encode('ascii'))!=received:raise ValueError('line checksum')
            f=dict(re.findall(r'(\w+)=([^\s]+)',body))
            if f['sample']!='5' or f['op']!='1':continue
            raw=bytes.fromhex(f['hex']);n=int(f['nbytes']);offset=int(f['offset'])
            if len(raw)!=n or len(f['hex'])!=int(f['hex_chars']) or fnv(raw)!=f['chunk_fnv']:raise ValueError('chunk length/checksum')
            for i,b in enumerate(raw):
                key=offset+i
                if key in records and records[key]!=b:raise ValueError('conflicting verified byte')
                records[key]=b
        except (ValueError,KeyError):rejected.append(number)
    return records,rejected


def run():
    path,inp,weight,bias,out,opts,weights,biases=load_model()
    reference=json.loads((PROJECT/'debug/python_operator_reference.json').read_text())
    assert reference['model_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert reference['sample']==5
    raw=(PROJECT/'main/test_data/ecg_test_samples_int8.bin').read_bytes()[5*256:6*256]
    assert fnv(raw)==reference['input_fnv']=='54868f67'
    x=list(struct.unpack('<256b',raw))
    expected=bytes.fromhex(next(t for t in reference['operators'] if t['op']==1)['hex'])
    single=[];double=[];details=[];max_acc=0
    for time in range(252):
        for channel in range(8):
            window=x[time:time+5];w=weights[channel*5:channel*5+5]
            acc=biases[channel]+sum((v-inp['zeros'][0])*k for v,k in zip(window,w))
            max_acc=max(max_acc,abs(acc));assert -(1<<31)<=acc<(1<<31)
            real=inp['scales'][0]*weight['scales'][channel]/out['scales'][0]
            m,shift=multiplier(real)
            s=single_round(acc,m,shift);d,high=double_round(acc,m,shift)
            sv=max(-128,min(127,s+out['zeros'][0]));dv=max(-128,min(127,d+out['zeros'][0])) # fused ReLU at zero_point=-128
            single.append(sv&255);double.append(dv&255)
            index=time*8+channel
            if index in [292,820,1455]:
                details.append({'index':index,'timestep':time,'channel':channel,'input':window,'weights':w,
                 'bias_int32':biases[channel],'input_zero':inp['zeros'][0],
                 'input_scale':inp['scales'][0],'weight_scale':weight['scales'][channel],
                 'bias_scale':bias['scales'][channel],'bias_scale_product':inp['scales'][0]*weight['scales'][channel],
                 'accumulator':acc,'real_multiplier':real,'multiplier':m,'shift':shift,
                 'exact_scaled_accumulator':acc*m/(2**(31-shift)),
                 'single_round_add':2**(30-shift),'single_shift_bits':31-shift,
                 'double_divisor':2**(-shift),
                 'double_high_mul':high,'double_requantized':d,'single_requantized':s,
                 'output_zero':out['zeros'][0],'activation_min':-128,'activation_max':127,
                 'python_int8':struct.unpack('b',expected[index:index+1])[0],'single_int8':sv,'double_int8':dv})
    observed,rejected=verified_trace_chunks(PROJECT/'debug/serial_trace_v2.log')
    for d in details:d['verified_esp32_int8']=observed.get(d['index']);d['verified_esp32_int8']=None if d['verified_esp32_int8'] is None else struct.unpack('b',bytes([d['verified_esp32_int8']]))[0]
    result={'scope':'Full mathematical convolution over original tensors; partial checksum-verified hardware bytes only, not repaired stream',
      'model_sha256':reference['model_sha256'],'options':opts,'input_shape':inp['shape'],'weight_shape':weight['shape'],
      'weight_axis':weight['axis'],'output_shape':out['shape'],'max_abs_accumulator':max_acc,
      'python_fnv':fnv(expected),'single_fnv':fnv(bytes(single)),'double_fnv':fnv(bytes(double)),
      'single_vs_python_mismatches':sum(a!=b for a,b in zip(single,expected)),
      'double_vs_python_mismatches':sum(a!=b for a,b in zip(double,expected)),
      'verified_hardware_bytes':len(observed),'rejected_trace_lines':rejected,
      'single_vs_verified_hardware_mismatches':sum(single[i]!=v for i,v in observed.items()),
      'double_vs_verified_hardware_mismatches':sum(double[i]!=v for i,v in observed.items()),'positions':details}
    (PROJECT/'debug/isolated_conv_arithmetic.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    # Fixtures for actual bundled TFLM C++ reference kernel host testing.
    def arr(name,values,ctype):return f'const {ctype} {name}[]={{'+','.join(map(str,values))+'};\n'
    h='#pragma once\n#include <cstdint>\n'+arr('kInput',x,'int8_t')+arr('kWeights',weights,'int8_t')+arr('kBias',biases,'int32_t')
    ms=[multiplier(inp['scales'][0]*s/out['scales'][0]) for s in weight['scales']]
    h+=arr('kMultiplier',[v[0] for v in ms],'int32_t')+arr('kShift',[v[1] for v in ms],'int32_t')
    h+=arr('kExpected',[struct.unpack('b',bytes([v]))[0] for v in expected],'int8_t')
    h+=f'constexpr int kInputOffset={-inp["zeros"][0]};\nconstexpr int kOutputOffset={out["zeros"][0]};\n'
    (PROJECT/'tests/conv_fixture.h').write_text(h)
    return result


if __name__=='__main__':run()
