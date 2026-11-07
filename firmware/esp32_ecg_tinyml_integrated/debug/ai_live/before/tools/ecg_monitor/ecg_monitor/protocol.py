"""ECG1 CRC32 JSON framing. Payload samples are LE <IHB> dt_us, raw, flags."""
import json
import struct
import zlib
import math
import re

MAX_LINE = 4096


def encode(packet):
    body = json.dumps(packet, separators=(',', ':'), allow_nan=False).encode('ascii')
    return b'ECG1 ' + f'{zlib.crc32(body):08x}'.encode() + b' ' + body + b'\n'


def samples_packet(values, *, first=0, t0=0, seq=0, boot='demo', flags=None):
    flags = flags if flags is not None else [0]*len(values)
    raw = b''.join(struct.pack('<IHB', i*4000, int(x), int(f)) for i, (x,f) in enumerate(zip(values,flags)))
    return dict(v=1,type='samples',boot=boot,seq=seq,first=first,t0=t0,fs=250,n=len(values),data=raw.hex(),dropped=0)


def _integer(p,key,lo,hi):
    value=p.get(key)
    if type(value) is not int or not lo<=value<=hi: raise ValueError(f'invalid {key}')
    return value


class FrameError(ValueError): pass
class CrcError(ValueError): pass
class PatternError(ValueError): pass


def decode(line):
    if len(line)>MAX_LINE: raise FrameError('oversized frame')
    try:prefix,crc,body=line.rstrip(b'\r\n').split(b' ',2)
    except ValueError as error:raise FrameError('missing frame fields') from error
    if prefix!=b'ECG1' or len(crc)!=8 or not re.fullmatch(b'[0-9a-fA-F]{8}',crc):raise FrameError('invalid prefix/CRC field')
    if int(crc,16)!=zlib.crc32(body):raise CrcError('CRC mismatch')
    p=json.loads(body,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if not isinstance(p,dict) or type(p.get('v')) is not int or p.get('v') not in (1,2) or p.get('type') not in ('samples','status'): raise ValueError('unsupported protocol/type')
    if p['v']==2 and p.get('source') not in ('HARDWARE','SYNTHETIC_TEST'):raise ValueError('protocol2 requires explicit source')
    if not isinstance(p.get('boot'),str) or not 1<=len(p['boot'])<=32: raise ValueError('invalid boot')
    _integer(p,'seq',0,0xffffffff)
    if p['type']=='samples':
        n=_integer(p,'n',1,32);_integer(p,'first',0,0xffffffff);_integer(p,'t0',0,2**63-1)
        if p.get('fs')!=250: raise ValueError('unsupported sample rate')
        if not isinstance(p.get('data'),str) or len(p['data'])!=n*14: raise ValueError('sample length')
        raw=bytes.fromhex(p['data']);rows=list(struct.iter_unpack('<IHB',raw))
        if rows[0][0]!=0 or any(rows[i][0]<=rows[i-1][0] for i in range(1,n)): raise ValueError('nonmonotonic sample timestamps')
        for dt,adc,flags in rows:
            if dt>10_000_000 or flags&~15 or (adc>4095 and not (adc==65535 and flags&4)): raise ValueError('invalid sample')
        p['samples']=[(p['t0']+dt,adc,flags) for dt,adc,flags in rows]
        if p.get('source') not in (None,'HARDWARE','SYNTHETIC_TEST'):raise ValueError('invalid sample source')
        if p.get('source')=='SYNTHETIC_TEST':
            if p.get('pattern')!='saw17-v1':raise PatternError('unknown synthetic pattern')
            for i,(_,adc,flags) in enumerate(rows):
                expected=512+((((p['first']+i)&0xffffffff)*17)%3072)
                if adc!=expected or flags&7:raise PatternError('synthetic sample differs from deterministic reference')
    else:
        _integer(p,'t_us',0,2**63-1)
        if p.get('state') not in ('SELF_TEST','WAITING','COLLECTING','SIGNAL_INVALID','NORMAL','PVC','SYSTEM_FAULT'): raise ValueError('invalid state')
        if not isinstance(p.get('reason'),str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,95}',p['reason']): raise ValueError('invalid reason code')
        for key in ('firmware','source','model','classification'):
            if key in p and (not isinstance(p[key],str) or len(p[key])>128):raise ValueError('invalid string '+key)
        for key in ('led','buzzer','self_test','quality_known','r_validated','golden','quality_valid','ai_validated'):
            if key in p and type(p[key]) is not bool:raise ValueError('invalid boolean '+key)
        for key in ('power50_ratio','baseline_delta','diff_percent','p_pvc','result_t_us'):
            if key in p and p[key] is not None and (type(p[key]) not in (int,float) or not math.isfinite(p[key])):raise ValueError('invalid numeric '+key)
        if p.get('quality_known') is True:
            _integer(p,'clip_count',0,256);_integer(p,'ptp',0,4095);_integer(p,'quality_t_us',0,2**63-1)
            for key in ('power50_ratio','baseline_delta','diff_percent'):
                if type(p.get(key)) not in (int,float):raise ValueError('missing quality metric '+key)
            if not 0<=p['power50_ratio']<=1 or not 0<=p['diff_percent']<=100:raise ValueError('quality metric out of range')
        if 'rail_margin' in p:_integer(p,'rail_margin',1,200)
        if 'diff_limit' in p:_integer(p,'diff_limit',1,100)
        if 'quality_t_us' in p:_integer(p,'quality_t_us',0,2**63-1)
        if p.get('result_t_us') is not None:_integer(p,'result_t_us',0,2**63-1)
        for key in ('adc_errors','missed_est','late','snapshot_errors','tx_dropped','write_errors','format_errors','uart_write_errors','uart_tx_timeouts'):
            if key in p:_integer(p,key,0,0xffffffff)
        for key in ('sample_attempts','tx_samples','tx_bytes','baud','uart_baud_actual','clock_last_us','dt_min_us','dt_max_us'):
            if key in p:_integer(p,key,0,2**63-1)
        for key in ('acq_hz','tx_hz','dt_mean_us'):
            if p.get(key) is not None and (type(p[key]) not in (int,float) or not math.isfinite(p[key]) or not 0<=p[key]<=1e10):raise ValueError('invalid timing '+key)
    if p['type']=='status':
        from .research import validate_research
        validate_research(p)
    p.pop('_received_monotonic',None) # Reserved for the local serial reader, not the device.
    return p


class StreamParser:
    def __init__(self,on_reject=None):
        self.on_reject=on_reject;self.connections=0;self.reconnects=0
        self._reset()

    def _reset(self):
        self.buffer=bytearray();self.discard=False;self.debug_lines=0
        self.crc_failures=0;self.framing_errors=0;self.schema_errors=0;self.sequence_errors=0
        self.lost_packets=0;self.lost_samples=0;self.timing_violations=0;self.synthetic_mismatches=0
        self.boot=None;self.seq=None;self.first=None;self.last_time=None;self.retired=set()

    @property
    def errors(self):return self.crc_failures+self.framing_errors+self.schema_errors+self.sequence_errors+self.synthetic_mismatches

    def reset_connection(self):
        self.connections+=1;self.reconnects=max(0,self.connections-1);self._reset()

    def reject(self,kind,error,line):
        setattr(self,kind,getattr(self,kind)+1)
        if self.on_reject:self.on_reject(dict(kind=kind,reason=str(error),line_hex=line.hex()))

    def feed(self,data):
        result=[]
        for byte in data:
            if byte==10:
                if self.discard:self.discard=False;self.buffer.clear();continue
                line=bytes(self.buffer);self.buffer.clear()
                if not line.startswith(b'ECG1 '):self.debug_lines+=1;continue
                try:p=decode(line)
                except CrcError as e:self.reject('crc_failures',e,line);continue
                except FrameError as e:self.reject('framing_errors',e,line);continue
                except PatternError as e:self.reject('synthetic_mismatches',e,line);continue
                except (ValueError,KeyError,TypeError,UnicodeError,OverflowError) as e:self.reject('schema_errors',e,line);continue
                changed=p['boot']!=self.boot
                seq=None if changed else self.seq;first=None if changed else self.first;last=None if changed else self.last_time
                try:
                    if changed and p['boot'] in self.retired:raise ValueError('retired boot replay')
                    delta=1 if seq is None else (p['seq']-seq)&0xffffffff
                    if delta==0 or delta>=0x80000000:raise ValueError('duplicate/out-of-order packet')
                    gap=0;timing=0
                    if p['type']=='samples':
                        if first is not None:
                            gap=(p['first']-first)&0xffffffff
                            if gap>=0x80000000:raise ValueError('sample sequence moved backwards')
                        if last is not None and p['samples'][0][0]<=last:raise ValueError('sample time moved backwards')
                        times=[r[0] for r in p['samples']]
                        if last is not None and gap==0:times.insert(0,last)
                        timing=sum(abs(b-a-4000)>500 for a,b in zip(times,times[1:]))
                except ValueError as e:self.reject('sequence_errors',e,line);continue
                if changed:
                    if self.boot is not None:
                        if len(self.retired)>=16:self.retired.clear()
                        self.retired.add(self.boot)
                    self.boot=p['boot'];self.first=None;self.last_time=None
                if p['type']=='samples':
                    self.lost_samples+=gap;self.timing_violations+=timing
                    self.first=(p['first']+p['n'])&0xffffffff;self.last_time=p['samples'][-1][0]
                self.lost_packets+=delta-1;self.seq=p['seq'];result.append(p)
            elif not self.discard:
                self.buffer.append(byte)
                if len(self.buffer)>MAX_LINE:
                    self.reject('framing_errors','oversized unterminated frame',bytes(self.buffer));self.buffer.clear();self.discard=True
        return result
