import csv
import json
import math
import time
from collections import deque,Counter
from datetime import datetime,timezone
from pathlib import Path


def valid_classification(status,source,now_us,invalid_since=None,min_result_us=None):
    from .ai import classification
    return classification(status,source,now_us,invalid_since,min_result_us)


class Session:
    def __init__(self):
        self.times=deque(maxlen=5000);self.values=deque(maxlen=5000);self.flags=deque(maxlen=5000);self.received_times=deque(maxlen=5000)
        self.status={};self.boot=None;self.source='DEMO';self.last_received=0
        self.csv=None;self.writer=None;self.path=None;self.total=0;self.adc_errors=0;self.missed_flags=0
        self.last_status_us=None;self.rows=0;self.last_samples_received=0
        self.local_invalid_reason=None;self.local_invalid_t=None;self.last_invalid_t=None
        self.record_states=Counter();self.record_classes=Counter();self.record_first_t=None;self.record_last_t=None
        self.record_error=None
        self.transport_stats={}
        self.arrivals=deque(maxlen=256)
        self.origin_us=None
        self.prediction_epoch_us=None

    def disconnect(self):
        self.status={};self.last_received=0;self.last_samples_received=0;self.last_status_us=None;self.boot=None
        self.times.clear();self.values.clear();self.flags.clear();self.received_times.clear()
        self.local_invalid_reason=None;self.local_invalid_t=None;self.last_invalid_t=None
        self.arrivals=deque(maxlen=256)
        self.origin_us=None
        self.prediction_epoch_us=None

    def consume(self,p,source):
        if p['type']=='samples':
            rows=p.get('samples',[])
            if not rows or len(rows)>32:raise ValueError('invalid decoded batch length')
            previous=self.received_times[-1] if self.received_times and self.boot==p['boot'] and self.source==source else None
            for t,raw,flags in rows:
                if type(t) is not int or not 0<=t<2**63 or (previous is not None and t<=previous):raise ValueError('invalid session timestamp')
                if type(flags) is not int or flags&~15:raise ValueError('invalid session flags')
                if type(raw) is not int or not (0<=raw<=4095 or (raw==65535 and flags&4)):raise ValueError('invalid session ADC')
                previous=t
        if self.boot!=p['boot'] or self.source!=source:
            self.times.clear();self.values.clear();self.flags.clear();self.received_times.clear();self.status={};self.last_status_us=None
            self.local_invalid_reason=None;self.local_invalid_t=None;self.last_invalid_t=None
            self.arrivals.clear();self.total=0;self.adc_errors=0;self.missed_flags=0
            self.origin_us=None
            self.prediction_epoch_us=None
        self.boot=p['boot'];self.source=source;self.last_received=time.monotonic()
        if self.prediction_epoch_us is None:
            self.prediction_epoch_us=p['t_us'] if p['type']=='status' else p['samples'][0][0]
        if p['type']=='status':
            self.status=p;self.last_status_us=p['t_us']
            if self.local_invalid_t is not None and p.get('quality_valid') is True and p.get('quality_t_us',-1)>self.local_invalid_t:
                self.local_invalid_reason=None;self.local_invalid_t=None
            return
        self.last_samples_received=time.monotonic()
        self.arrivals.append((p.get('_received_monotonic',self.last_samples_received),len(p['samples'])))
        if self.last_status_us is not None and p['samples'][-1][0]-self.last_status_us>2_000_000:self.status={}
        for index,(t,raw,flags) in enumerate(p['samples']):
            if self.origin_us is None:self.origin_us=t
            self.received_times.append(t)
            gap=bool(self.times and (t-self.times[-1]>6000 or t-self.times[-1]<2000))
            margin=self.status.get('rail_margin',16)
            reason='LEADS_OFF' if flags&3 else 'ADC_READ_ERROR' if flags&4 else 'SAMPLE_GAP' if flags&8 or gap else 'ADC_SATURATION' if raw<=margin or raw>=4095-margin else None
            if reason:self.local_invalid_reason=reason;self.local_invalid_t=t;self.last_invalid_t=t
            if self.times and (t-self.times[-1]>6000 or t-self.times[-1]<2000):
                self.times.append(t-1);self.values.append(float('nan'));self.flags.append(0)
            self.times.append(t);self.values.append(raw if raw<=4095 else float('nan'));self.flags.append(flags)
            self.total+=1;self.adc_errors+=bool(flags&4);self.missed_flags+=bool(flags&8)
            if self.writer:
                label,prob=valid_classification(self.status,source,t,self.last_invalid_t,self.prediction_epoch_us)
                if self.local_invalid_reason:label,prob='UNKNOWN',None
                try:
                    self.writer.writerow([source,self.boot,p['seq'],p['first']+index,t,raw,flags&1,(flags>>1)&1,bool(flags&4),bool(flags&8),
                        self.status.get('t_us',''),'SIGNAL_INVALID' if self.local_invalid_reason else self.status.get('state','UNKNOWN'),
                        self.local_invalid_reason or self.status.get('reason',''),self.status.get('model','UNKNOWN'),label,'' if prob is None else prob])
                except OSError as error:
                    self._record_failed(error);continue
                self.rows+=1
                self.record_states['SIGNAL_INVALID' if self.local_invalid_reason else self.status.get('state','UNKNOWN')]+=1
                self.record_classes[label]+=1
                if self.record_first_t is None:self.record_first_t=t
                self.record_last_t=t
        if self.csv:
            try:self.csv.flush()
            except OSError as error:self._record_failed(error)

    def ai_display(self,now=None,connected=True):
        from .ai import display
        return display(self,time.monotonic() if now is None else now,connected)

    def received_wall_rate(self,now=None):
        now=time.monotonic() if now is None else now
        rows=[r for r in getattr(self,'arrivals',[]) if now-r[0]<=5]
        if len(rows)<2 or rows[-1][0]<=rows[0][0] or now-rows[-1][0]>2:return None
        return sum(n for _,n in rows[1:])/(rows[-1][0]-rows[0][0])

    def _record_failed(self,error):
        self.record_error=str(error)
        if self.csv:
            try:self.csv.close()
            except OSError:pass
        self.csv=None;self.writer=None

    def start_recording(self,path):
        self.stop_recording();self.path=Path(path)
        self.csv=self.path.open('x',newline='',encoding='utf-8')
        self.writer=csv.writer(self.csv);self.rows=0
        self.record_error=None
        self.record_states.clear();self.record_classes.clear();self.record_first_t=None;self.record_last_t=None
        self.record_started=datetime.now(timezone.utc).isoformat()
        try:
            self.writer.writerow(['source','boot','packet_seq','sample_index','timestamp_us','raw_adc','lo_plus','lo_minus','adc_error','missed',
                'status_timestamp_us','state','reason','model','classification','p_pvc'])
        except OSError as error:self._record_failed(error);raise

    def stop_recording(self):
        if self.csv:
            try:self.csv.close()
            except OSError as error:self._record_failed(error);return
            try:
                self._save_report()
            except OSError as error:self._record_failed(error);return
        self.csv=None;self.writer=None

    def _save_report(self):
        self.path.with_suffix('.report.json').write_text(json.dumps(dict(source=self.source,rows=self.rows,
            started_utc=self.record_started,ended_utc=datetime.now(timezone.utc).isoformat(),
            first_device_timestamp_us=self.record_first_t,last_device_timestamp_us=self.record_last_t,
            state_rows=dict(self.record_states),classification_rows=dict(self.record_classes),
            transport_counters=self.transport_stats,
            firmware_counters={k:self.status.get(k) for k in ['adc_errors','missed_est','late','snapshot_errors','tx_dropped','write_errors']},
            units='ADC counts, uncalibrated',classification_scope='Bench research only; not a medical report',
            source_modes='DEMO is synthetic, HARDWARE is ADC telemetry',adc_errors_observed_session=self.adc_errors,missed_flags_observed_session=self.missed_flags),indent=2))


def demo_packet(first,seq):
    from .protocol import samples_packet
    # Deterministic synthesized P-QRS-T morphology, explicitly DEMO, no inference.
    values=[]
    for i in range(first,first+32):
        phase=(i/250)%1
        value=2048+sum(a*math.exp(-((phase-c)/w)**2) for a,c,w in [(30,.18,.04),(-65,.36,.014),(360,.4,.015),(-110,.44,.02),(65,.65,.07)])
        values.append(round(value))
    return samples_packet(values,first=first,t0=first*4000,seq=seq,boot='DEMO-SYNTHETIC')
