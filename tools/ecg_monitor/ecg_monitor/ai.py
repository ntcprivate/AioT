"""Single ADC CNN contract; legacy captures are decoded without a second runtime path."""
import math
import re

COUNTERS=('classified','rejected','queue_drops','block_drops','q_depth','q_high','detected','heap_free','heap_min','stack_free')
TIMES=('r_t_us','window_end_us','result_t_us','valid_until_us','latency_us','prep_us')

def prediction(status):
    if 'ai' in status and 'research' in status:raise ValueError('ambiguous AI payload')
    return status.get('ai',status.get('research'))

def validate_ai(p):
    r=prediction(p)
    if r is None:return
    if not isinstance(r,dict) or r.get('mode')!=('AI_LIVE' if 'ai' in p else 'RESEARCH_SHADOW') or r.get('source')!='ADC_CNN' or r.get('experimental') is not True:raise ValueError('invalid AI identity')
    if p.get('source')!='HARDWARE':raise ValueError('AI requires HARDWARE envelope')
    if r.get('state') not in ('NORMAL','PVC','UNKNOWN','INVALID'):raise ValueError('invalid AI state')
    if not isinstance(r.get('reason'),str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,95}',r['reason']):raise ValueError('invalid AI reason')
    for k in (*COUNTERS,*TIMES,'r_index'):
        if type(r.get(k)) is not int or not (-1 if k=='r_index' else 0)<=r[k]<2**63:raise ValueError('invalid AI '+k)
    if 'inference_calls' in r and (type(r['inference_calls']) is not int or not 0<=r['inference_calls']<2**32):raise ValueError('invalid AI inference count')
    prob=r.get('p_pvc')
    if r['state'] in ('NORMAL','PVC'):
        if type(prob) not in (int,float) or not math.isfinite(prob) or not 0<=prob<=1:raise ValueError('invalid AI probability')
        if r['r_index']<128 or not 0<r['r_t_us']<=r['window_end_us']<=r['result_t_us']<r['valid_until_us']<=r['result_t_us']+1_500_000:raise ValueError('invalid AI prediction times')
        if r['state']!=('PVC' if prob>=.52 else 'NORMAL'):raise ValueError('AI label/probability mismatch')
    elif prob is not None:raise ValueError('invalid AI state exposes probability')

def display(session,now,connected=True):
    out=dict(mode='DISABLED',prediction='UNKNOWN',state='UNKNOWN',probability=None,reason='WAITING_AI_TELEMETRY',age_us=None,ai={})
    if not connected or not session.last_received:
        out['reason']='STOPPED_OR_DISCONNECTED';return out
    s=session.status
    try:r=prediction(s)
    except ValueError:out['reason']='AI_SCHEMA_REJECTED';return out
    # Missing AI data must not hide a known signal fault, or restore an old score.
    if session.local_invalid_reason or s.get('state') in ('SIGNAL_INVALID','SYSTEM_FAULT'):
        out.update(state='INVALID',reason=session.local_invalid_reason or s['reason'])
        if r is None:return out
    if r is None:
        if session.source in ('DEMO','SYNTHETIC_TEST'):out['reason']=session.source+'_NO_INFERENCE'
        elif now-session.last_received>2:out['reason']='TELEMETRY_TIMEOUT'
        elif s:out['reason']='FIRMWARE_AI_TELEMETRY_UNAVAILABLE'
        elif session.last_status_us is not None:out['reason']='AI_STATUS_TIMEOUT'
        return out
    try:validate_ai(s)
    except (ValueError,TypeError):out['reason']='AI_SCHEMA_REJECTED';return out
    out.update(mode='AI_LIVE',ai=r,reason=r['reason'])
    if session.source!='HARDWARE' or s.get('source')!='HARDWARE':out['reason']='WRONG_SOURCE';return out
    if now-session.last_received>2 or now-session.last_samples_received>2:out['reason']='TELEMETRY_TIMEOUT';return out
    if session.local_invalid_reason or s.get('state') in ('SIGNAL_INVALID','SYSTEM_FAULT') or r['state']=='INVALID':
        reason=session.local_invalid_reason or (s.get('reason') if s.get('state') in ('SIGNAL_INVALID','SYSTEM_FAULT') else r['reason'])
        out.update(state='INVALID',reason=reason);return out
    # Official-live approval/model labels do not gate the separate CNN result.
    if s.get('golden') is not True or s.get('quality_valid') is not True or s.get('self_test') is True:
        out['reason']='MODEL_OR_QUALITY_NOT_READY';return out
    if r['state'] not in ('NORMAL','PVC'):return out
    if session.prediction_epoch_us is None or r['result_t_us']<=session.prediction_epoch_us:
        out['reason']='WAITING_NEW_PREDICTION_AFTER_CONNECT';return out
    device_now=max(s.get('t_us',0),session.received_times[-1] if session.received_times else 0)+int(max(0,now-session.last_received)*1e6)
    age=device_now-r['result_t_us'];out['age_us']=age
    if age<0 or device_now>r['valid_until_us']:out['reason']='PREDICTION_STALE';return out
    if session.last_invalid_t is not None and r['r_t_us']-512000<=session.last_invalid_t:out['reason']='WINDOW_OVERLAPS_INVALID_SIGNAL';return out
    label,score=classification(s,session.source,device_now,session.last_invalid_t,session.prediction_epoch_us)
    out.update(prediction=label,state=label,probability=score);return out


def classification(status,source,now_us,invalid_since=None,min_result_us=None):
    """The same score/source/quality/freshness policy used by GUI and CSV."""
    try:validate_ai(status)
    except (ValueError,TypeError):return 'UNKNOWN',None
    r=prediction(status)
    if not r or source!='HARDWARE' or status.get('source')!='HARDWARE':return 'UNKNOWN',None
    if status.get('golden') is not True or status.get('quality_valid') is not True or status.get('self_test') is True:return 'UNKNOWN',None
    if status.get('state') in ('SIGNAL_INVALID','SYSTEM_FAULT') or r['state'] not in ('NORMAL','PVC'):return 'UNKNOWN',None
    if not r['result_t_us']<=now_us<=r['valid_until_us']:return 'UNKNOWN',None
    if min_result_us is not None and r['result_t_us']<=min_result_us:return 'UNKNOWN',None
    if invalid_since is not None and r['r_t_us']-512000<=invalid_since:return 'UNKNOWN',None
    return r['state'],r['p_pvc']
