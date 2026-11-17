"""Strictly verify a future board log; incomplete logs never imply PASS."""
import argparse,json,re
from pathlib import Path
def verify(text,meta):
 def fields(line):return dict(re.findall(r'(\w+)=([^\s]+)',line))
 assert text.count('V4_GOLDEN_BEGIN ')==1,'Require exactly one complete boot/test session'
 assert text.count('V4_GOLDEN_END')==1,'Missing END'
 models=[fields(s) for s in text.splitlines() if 'V4_GOLDEN_MODEL ' in s];assert len(models)==1 and models[0]['sha256']==meta['model_sha256'],'Model hash'
 samples=[fields(s) for s in text.splitlines() if 'V4_GOLDEN_SAMPLE ' in s];assert len(samples)==meta['count'],'Missing/duplicate samples'
 ids=[int(s['i']) for s in samples];assert sorted(ids)==list(range(meta['count'])),'Fixture IDs'
 for s in samples:
  f=meta['fixtures'][int(s['i'])];c=int(s['code']);assert c==int(s['reference'])==f['reference_code'],'Output code differs'
  assert int(s['delta'])==0 and s['status']=='EXACT' and int(s['prep_exact'])==1,'Arithmetic/preprocessing failed'
  assert int(s['predicted'])==int(s['expected_predicted'])==int(c>=98),'Threshold mismatch'
  assert abs(float(s['probability'])-(c+128)/256)<1e-8,'Dequantization mismatch'
  assert int(s['inference_us'])>=0,'Invalid timing'
 results=[fields(s) for s in text.splitlines() if 'V4_GOLDEN_RESULT ' in s];assert len(results)==1,'Missing/duplicate RESULT';r=results[0]
 assert r['status']=='PASS' and int(r['exact'])==int(r['total'])==int(r['prep_exact'])==meta['count'] and int(r['max_code_delta'])==0,'Summary failed'
 assert r['model_sha256']==meta['model_sha256'],'Summary model hash'
 mem=[fields(s) for s in text.splitlines() if 'V4_GOLDEN_MEMORY ' in s];assert len(mem)==1,'Missing measured memory'
 return {'status':'PASS','exact':len(samples),'model_sha256':meta['model_sha256'],'result':r,'memory':mem[0],'allocation':models[0],'claim':'static golden arithmetic only, not ECG classification accuracy'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('log',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();meta=json.loads((Path(__file__).parent/'fixtures.json').read_text())
 try:r=verify(a.log.read_text(errors='replace'),meta)
 except (AssertionError,KeyError,ValueError) as e:raise SystemExit('NOT VERIFIED: '+str(e))
 if a.output:
  if a.output.exists():raise SystemExit('Refusing overwrite')
  a.output.write_text(json.dumps(r,indent=2))
 print(json.dumps(r,indent=2))
