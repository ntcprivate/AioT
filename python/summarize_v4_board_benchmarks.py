"""Summarize two validated real V4 UART runs; no model execution or Serial access."""
import argparse,csv,hashlib,json,math,statistics
from pathlib import Path
def distribution(v):
 v=sorted(v);k=.95*(len(v)-1);lo=int(k);hi=min(lo+1,len(v)-1)
 return {'n':len(v),'mean_us':statistics.mean(v),'median_us':statistics.median(v),'min_us':min(v),'max_us':max(v),'p95_us':v[lo]+(v[hi]-v[lo])*(k-lo),'sample_SD_us':statistics.stdev(v)}
def main():
 p=argparse.ArgumentParser();p.add_argument('experiment',type=Path);a=p.parse_args();root=a.experiment
 if (root/'metrics.json').exists():raise SystemExit('Refuse overwrite')
 config=json.loads((root/'config.json').read_text());metrics={};all_fixture={}
 for name in ['FP32','INT8']:
  folder=root/name;validated=json.loads((folder/'validated_samples.json').read_text());assert validated['status']=='PASS'
  rows=validated['samples'];measured=[s for s in rows if int(s['run'])>=0];assert len(measured)==660
  with (folder/'all_runs.csv').open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
  mem=validated['memory'];build=json.loads((folder/'build_verification.json').read_text())
  stats={k:distribution([int(s[k]) for s in measured]) for k in ['norm_us','quant_copy_us','invoke_us','total_us']}
  fixtures=[]
  for i in range(22):
   m=[s for s in measured if int(s['i'])==i];scores=[float(s['score']) for s in m];preds={int(s['predicted']) for s in m};assert len(preds)==1,'Unstable classification'
   assert max(scores)-min(scores)<=1e-7,'Unstable repeated score'
   fixtures.append({'fixture':i,'score_mean':statistics.mean(scores),'score_min':min(scores),'score_max':max(scores),'prediction':next(iter(preds)),
    'code':int(m[0]['code']) if name=='INT8' else None,'invoke_mean_us':statistics.mean(int(s['invoke_us']) for s in m),'total_mean_us':statistics.mean(int(s['total_us']) for s in m)})
  all_fixture[name]=fixtures
  metrics[name]={'status':'PASS_REAL_ESP32','model_bytes':config['model_bytes'][name],'application_bytes':build['application_bytes'],
   'static_DRAM_bytes':build['static_dram_bytes'],'static_IRAM_bytes':build['static_iram_bytes'],
   'arena_used_bytes':int(mem['arena_used']),'arena_allocated_bytes':int(mem['arena_allocated']),'minimum_free_heap_bytes':int(mem['heap_min']),
   'main_stack_high_water_free_bytes':int(mem['stack_free']),'main_stack_reserved_bytes':config['main_stack_bytes'],
   'main_stack_peak_used_estimate_bytes':config['main_stack_bytes']-int(mem['stack_free']),
   'measured_runs':660,'warmup_runs':66,'statistics':stats,
   'first_warmup_per_fixture_invoke':distribution([int(s['invoke_us']) for s in rows if int(s['run'])==-3]),
   'first_Invoke_after_boot_us':int(next(s for s in rows if s['i']=='0' and s['run']=='-3')['invoke_us']),
   'uart_sha256':hashlib.sha256((folder/'uart_raw.log').read_bytes()).hexdigest(),'application_sha256':build['application_sha256']}
 comparisons=[]
 for f,q in zip(all_fixture['FP32'],all_fixture['INT8']):comparisons.append({'fixture':f['fixture'],'FP32_score':f['score_mean'],'INT8_score':q['score_mean'],'INT8_code':q['code'],'score_INT8_minus_FP32':q['score_mean']-f['score_mean'],
   'FP32_prediction':f['prediction'],'INT8_prediction':q['prediction'],'decision_matches':f['prediction']==q['prediction'],'FP32_invoke_mean_us':f['invoke_mean_us'],'INT8_invoke_mean_us':q['invoke_mean_us']})
 with (root/'fixture_comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
 fp=metrics['FP32'];qi=metrics['INT8'];mean_fp=fp['statistics']['invoke_us']['mean_us'];mean_q=qi['statistics']['invoke_us']['mean_us']
 result={'config':config,'models':metrics,'comparison':{'INT8_speedup_FP32_over_INT8':mean_fp/mean_q,'INT8_latency_ratio_INT8_over_FP32':mean_q/mean_fp,
 'INT8_latency_percent_change':100*(mean_q/mean_fp-1),'INT8_total_latency_percent_change':100*(qi['statistics']['total_us']['mean_us']/fp['statistics']['total_us']['mean_us']-1),
 'model_reduction_bytes':fp['model_bytes']-qi['model_bytes'],'model_reduction_percent':100*(1-qi['model_bytes']/fp['model_bytes']),
 'application_reduction_bytes':fp['application_bytes']-qi['application_bytes'],'application_reduction_percent':100*(1-qi['application_bytes']/fp['application_bytes']),
 'arena_used_reduction_percent':100*(1-qi['arena_used_bytes']/fp['arena_used_bytes']),
 'predictions_matching':sum(c['decision_matches'] for c in comparisons),'predictions_different':sum(not c['decision_matches'] for c in comparisons),
 'max_abs_score_difference':max(abs(c['score_INT8_minus_FP32']) for c in comparisons),'mean_abs_score_difference':statistics.mean(abs(c['score_INT8_minus_FP32']) for c in comparisons)},
 'fixtures':comparisons,'publication_limit':'single board, single boot per backend, repeated runs not independent board sessions; validation golden set selected for numerical edge cases, not classification accuracy or R-to-result/ADC latency'}
 (root/'metrics.json').write_text(json.dumps(result,indent=2));print(json.dumps({'models':metrics,'comparison':result['comparison']},indent=2))
if __name__=='__main__':main()
