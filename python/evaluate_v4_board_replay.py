"""Score one real device replay log only; no Serial access or model inference."""
import argparse,hashlib,json,re
from pathlib import Path

def fields(line):return dict(re.findall(r'(\w+)=([^\s]+)',line))
def match(refs,peaks,tolerance=38):
    used=set();pairs={}
    for i,r in enumerate(refs):
        candidates=[j for j,p in enumerate(peaks) if j not in used and abs(p-r['sample'])<=tolerance]
        if candidates:
            j=min(candidates,key=lambda j:(abs(peaks[j]-r['sample']),j));used.add(j);pairs[i]=j
    return pairs,used
def evaluate(text,protocol,record,refs):
    def rows(tag):return [fields(line) for line in text.splitlines() if line.startswith(tag+' ')]
    begin=rows('V4_REPLAY_BEGIN');end=rows('V4_REPLAY_END');summary=rows('V4_PIPELINE_SUMMARY')
    assert len(begin)==len(end)==len(summary)==1,'Incomplete/duplicate replay session'
    assert begin[0]['record']==end[0]['record']==record['dataset']+'_'+record['record'],'Wrong record'
    assert begin[0]['sha256']==record['sha256'],'Stream hash'
    assert end[0]['stream_complete']=='1' and end[0]['missed']=='0','Incomplete/dropped replay'
    assert 'ECG_GOLDEN_DONE samples=22 failed=0 status=PASSED' in text,'Integrated golden missing/failed'
    assert 'a7ce1ed87e781597d6bbe09901602c801c08863e3ad0c3313f3a234f86719b0e' in text,'Model identity missing'
    peakrows=rows('V4_PEAK');peaks=[int(r['r_index']) for r in peakrows]
    assert all(a<b for a,b in zip(peaks,peaks[1:])),'Duplicate/out-of-order peak'
    assert len(peaks)==int(summary[0]['detected']),'Lost peak log'
    assert int(summary[0]['queue_drops'])==int(summary[0]['block_drops'])==0,'Dropped queue/block'
    beatrows=rows('V4_BEAT');pred={};seen=set()
    for b in beatrows:
        p=int(b['r_index']);assert p in peaks and p not in seen,'Unknown/duplicate beat window';seen.add(p)
        if b['rejected']=='0':
            code=int(b['code']);assert -128<=code<=127
            assert abs(float(b['p_pvc'])-(code+128)/256)<1e-8,'Corrupt score'
            assert int(b['predicted'])==int(code>=98),'Threshold mismatch'
            pred[p]=int(b['predicted'])
        else:assert int(b['predicted'])==-1
    assert len(pred)==int(summary[0]['classified']),'Missing classified-beat log'
    beatrefs=[r for r in refs if r['symbol'] in protocol['matching']['beat_symbols']]
    pairs,used=match(beatrefs,peaks);tp=fp=fn=tn=missing_n=missing_v=window_v=cnn_v=0
    for i,r in enumerate(beatrefs):
        c=r['symbol']
        if c not in {'N','V'}:continue
        if i not in pairs:
            missing_v+=c=='V';missing_n+=c=='N';fn+=c=='V';continue
        p=peaks[pairs[i]]
        if p not in pred:window_v+=c=='V';missing_n+=c=='N';fn+=c=='V';continue
        value=pred[p];tp+=c=='V' and value;tn+=c=='N' and not value;fp+=c=='N' and value
        fn+=c=='V' and not value;cnn_v+=c=='V' and not value
    unmatched_fp=sum(pred.get(p,0) for j,p in enumerate(peaks) if j not in used);fp+=unmatched_fp
    precision=tp/(tp+fp) if tp+fp else 0;recall=tp/(tp+fn) if tp+fn else 0
    return {'TP':tp,'FP':fp,'FN':fn,'TN':tn,'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0,
        'peakTP':len(pairs),'peakFP':len(peaks)-len(used),'peakFN':len(beatrefs)-len(pairs),
        'PVC_detector_missed':missing_v,'PVC_window_or_gate_missing':window_v,'PVC_classifier_FN':cnn_v,
        'missing_N_abstentions':missing_n,'unmatched_PVC_alarms':unmatched_fp,
        'matched_OTHER':sum(r['symbol'] not in {'N','V'} for i,r in enumerate(beatrefs) if i in pairs),
        'caveat':'Development engineering replay, not independent or analog validation; unmatched does not establish noise'}
def main():
    p=argparse.ArgumentParser();p.add_argument('log',type=Path);p.add_argument('--record',required=True,choices=['MITBIH_100','INCART_I08','INCART_PVC_V1']);p.add_argument('--protocol',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=root/'results/cnn_v4/esp32_end_to_end'
    if a.output.exists():raise SystemExit('Refuse overwrite')
    if a.record=='INCART_PVC_V1':
        assert a.protocol,'PVC pilot requires explicit frozen --protocol'
        protocol=json.loads(a.protocol.read_text());assert protocol['segment_id']==a.record
        assert hashlib.sha256(a.protocol.read_bytes()).hexdigest()==a.protocol.with_suffix('.sha256').read_text().strip(),'Protocol hash'
        assert protocol['matching']['tolerance_samples']==38 and protocol['threshold_code']==98 and protocol['threshold']==.88
        record={'dataset':'INCART','record':'PVC_V1','sha256':protocol['stream_sha256']}
        refpath=root/protocol['annotation_list'];expected=protocol['annotation_sha256']
    else:
        assert a.protocol is None,'Original smoke records use original locked protocol'
        protocol=json.loads((out/'replay_protocol.json').read_text());record=next(r for r in protocol['records'] if r['dataset']+'_'+r['record']==a.record)
        refpath=root/record['reference_path'];expected=record['reference_sha256']
    assert hashlib.sha256(refpath.read_bytes()).hexdigest()==expected
    rawlog=a.log.read_bytes()
    text=rawlog.decode('utf-16') if rawlog.startswith((b'\xff\xfe',b'\xfe\xff')) else rawlog.decode('utf-8-sig',errors='replace')
    result=evaluate(text,protocol,record,json.loads(refpath.read_text()))
    result['log_sha256']=hashlib.sha256(a.log.read_bytes()).hexdigest();a.output.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
